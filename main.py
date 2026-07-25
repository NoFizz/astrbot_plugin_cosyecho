import asyncio
import os
import random
import tempfile
import unicodedata
import uuid
from pathlib import Path

import dashscope
import httpx
from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

MessageChain = None
Record = None

try:
    from astrbot.api.event import MessageChain
    from astrbot.api.message_components import Record
except ImportError:
    pass

if MessageChain is None:
    try:
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.message.components import Record  # noqa: F401
    except ImportError:
        pass

# 语言名称 → 语言代码（用于 API 调用）
_LANGUAGE_NAME_TO_CODE = {
    "中文": "zh",
    "英文": "en",
    "法语": "fr",
    "德语": "de",
    "日语": "ja",
    "韩语": "ko",
    "俄语": "ru",
    "葡萄牙语": "pt",
    "泰语": "th",
    "印尼语": "id",
    "越南语": "vi",
}

# instruction 长度限制：100 字符，汉字按 2 计算
_INSTRUCTION_MAX_CHARS = 100


def _count_instruction_length(text: str) -> int:
    """计算 instruction 字符长度，全角/宽字符按 2 计算。"""
    length = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            length += 2
        else:
            length += 1
    return length


def _safe_int(value, default: int) -> int:
    """安全转换为 int，失败时返回默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float) -> float:
    """安全转换为 float，失败时返回默认值。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class CosyVoiceTTSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._audio_files: set[str] = set()
        # 按 UMO 追踪待清理的音频文件。
        # 此实现依赖 AstrBot 核心按会话(UMO)串行处理消息事件的特性。
        # 同一 UMO 的 on_llm_response 和 after_message_sent 不会并发执行，
        # 因此无需对 _pending_audio 使用锁。若未来核心调度模型变更，需重新评估。
        self._pending_audio: dict[str, set[str]] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def terminate(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
        for path in self._audio_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self._audio_files.clear()
        self._pending_audio.clear()

    def _get_config_value(self, key: str, default=None):
        """从插件配置中读取指定 key 的值，失败时返回默认值。"""
        try:
            return self.config.get(key, default)
        except Exception:
            return default

    def _check_whitelist(self, config_key: str, umo: str) -> bool:
        """检查 UMO 是否在白名单中。白名单为空时允许所有。"""
        whitelist = self._get_config_value(config_key, [])
        if isinstance(whitelist, str):
            whitelist = [s.strip() for s in whitelist.split(",") if s.strip()]
        whitelist_str = [str(x) for x in whitelist]
        return not whitelist_str or umo in whitelist_str

    def _should_process_message(self, event: AstrMessageEvent) -> bool:
        """判断是否应该处理该消息（API Key、开关、白名单、触发概率）。"""
        api_key = self._get_config_value("api_key", "")
        if not api_key:
            return False

        umo = event.unified_msg_origin

        if event.is_private_chat():
            if not self._get_config_value("private_voice_enabled", True):
                return False
            if not self._check_whitelist("private_whitelist", umo):
                return False
            trigger_prob = self._get_config_value("private_trigger_probability", 0.2)
        else:
            if not self._get_config_value("group_voice_enabled", True):
                return False
            if not self._check_whitelist("group_whitelist", umo):
                return False
            trigger_prob = self._get_config_value("group_trigger_probability", 0.2)

        if trigger_prob < 1.0:
            if random.random() > trigger_prob:
                return False

        return True

    def _should_translate(self) -> bool:
        """判断是否需要翻译（开关、模型、提示词均已配置）。"""
        if not self._get_config_value("translation_enabled", False):
            return False
        if not self._get_config_value("translation_model", ""):
            return False
        if not self._get_config_value("system_prompt", ""):
            return False
        return True

    async def _translate_text(self, text: str) -> str:
        """通过 LLM 将文本翻译为目标语言，失败时返回原文。"""
        try:
            translation_model = self._get_config_value("translation_model", "")
            system_prompt = self._get_config_value("system_prompt", "")

            llm_resp = await self.context.llm_generate(
                chat_provider_id=translation_model,
                prompt=text,
                system_prompt=system_prompt,
            )
            if llm_resp and llm_resp.completion_text:
                return llm_resp.completion_text.strip()
            return text
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return text

    def _parse_language_hint(self, language_hint: str) -> str:
        """将语言中文名转换为 API 语言代码，未知语言原样返回。"""
        code = _LANGUAGE_NAME_TO_CODE.get(language_hint.strip())
        if code:
            return code
        return language_hint.strip()

    def _get_temp_dir(self) -> str:
        """获取临时文件目录，按优先级回退。"""
        try:
            return str(get_astrbot_temp_path())
        except Exception:
            pass
        try:
            return str(StarTools.get_data_dir(self.name))
        except Exception:
            pass
        return tempfile.gettempdir()

    def _cleanup_audio_file(self, path: str):
        """清理单个音频文件。"""
        self._audio_files.discard(path)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建复用的 HTTP 客户端。"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def _synthesize(self, text: str) -> str | None:
        """调用 CosyVoice API 合成语音，返回音频文件路径。通过 dashscope.api_key 设置密钥。"""
        api_key = self._get_config_value("api_key", "")
        if not api_key:
            return None

        dashscope.api_key = api_key

        model = self._get_config_value("model", "cosyvoice-v3.5-plus")
        voice = self._get_config_value("voice", "")
        if not voice:
            logger.error("音色 ID 为空，请在配置中填写音色 ID")
            return None

        volume = _safe_int(self._get_config_value("volume", 50), 50)
        rate = _safe_float(self._get_config_value("rate", 1.0), 1.0)
        pitch = _safe_float(self._get_config_value("pitch", 1.0), 1.0)
        instruction = str(self._get_config_value("instruction", "")).strip()
        language = self._parse_language_hint(
            self._get_config_value("language_hint", "中文")
        )
        timeout = _safe_int(self._get_config_value("timeout", 20), 20)

        # 运行时截断 instruction，防止超长导致 API 异常
        if instruction:
            max_len = _INSTRUCTION_MAX_CHARS
            while _count_instruction_length(instruction) > max_len:
                instruction = instruction[:-1]
            if instruction != str(self._get_config_value("instruction", "")).strip():
                logger.warning(
                    f"instruction 超过 {max_len} 字符限制，已截断为: {instruction}"
                )

        temp_dir = self._get_temp_dir()
        os.makedirs(temp_dir, exist_ok=True)

        call_kwargs = {
            "model": model,
            "text": text,
            "voice": voice,
            "format": "wav",
            "sample_rate": 24000,
            "volume": volume,
            "rate": rate,
            "pitch": pitch,
        }
        call_kwargs["language_hints"] = [language]
        if instruction:
            call_kwargs["instruction"] = instruction

        loop = asyncio.get_running_loop()

        try:
            result = await loop.run_in_executor(
                None,
                lambda: HttpSpeechSynthesizer.call(**call_kwargs),
            )
        except Exception as e:
            logger.error(f"HttpSpeechSynthesizer.call 异常: {e}")
            return None

        if not result or not result.audio_url:
            logger.error(f"TTS 返回空结果: {result}")
            return None

        try:
            resp = await self._download_audio(result.audio_url, timeout)
        except Exception as e:
            logger.error(f"下载音频失败: {e}")
            return None

        if not resp:
            logger.error("TTS 返回空数据")
            return None

        path = os.path.join(temp_dir, f"cosyvoice_tts_{uuid.uuid4()}.wav")
        await loop.run_in_executor(None, Path(path).write_bytes, resp)

        self._audio_files.add(path)
        logger.info(f"语音已保存: {path} ({len(resp)} bytes)")
        return path

    async def _download_audio(self, url: str, timeout: int) -> bytes | None:
        """下载音频文件内容。"""
        client = await self._get_http_client()
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """将 LLM 回复转为语音发送，支持翻译、白名单、触发概率控制"""
        if getattr(resp, "is_chunk", False):
            return

        if not self._should_process_message(event):
            return

        original_text = (resp.completion_text or "").strip()
        if not original_text:
            return

        text_to_speak = original_text
        if self._should_translate():
            translated_text = await self._translate_text(original_text)
            if translated_text != original_text:
                text_to_speak = translated_text

        audio_path = await self._synthesize(text_to_speak)

        if not audio_path:
            logger.error("语音合成失败，跳过发送")
            return

        umo = event.unified_msg_origin
        self._pending_audio.setdefault(umo, set()).add(audio_path)

        send_text = self._get_config_value("send_text_with_voice", False)

        try:
            if Record is not None and MessageChain is not None:
                if send_text:
                    chain = MessageChain(
                        [
                            Comp.Plain(original_text),
                            Comp.Record(file=audio_path, url=audio_path),
                        ]
                    )
                else:
                    chain = MessageChain(
                        [
                            Comp.Record(file=audio_path, url=audio_path),
                        ]
                    )
                resp.result_chain = chain
            elif hasattr(resp, "result_chain") and hasattr(resp.result_chain, "chain"):
                resp.result_chain.chain.append(
                    Comp.Record(file=audio_path, url=audio_path)
                )
            else:
                logger.error("无法构建消息链：MessageChain/Record 导入失败")
        except Exception as e:
            logger.error(f"发送语音失败: {e}")
            self._cleanup_audio_file(audio_path)

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        """消息发送后清理该消息对应的临时音频文件"""
        umo = event.unified_msg_origin
        paths = self._pending_audio.pop(umo, set())
        for path in paths:
            self._cleanup_audio_file(path)
