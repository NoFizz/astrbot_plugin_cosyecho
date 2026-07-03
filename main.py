import asyncio
import os
import random
import tempfile
import uuid
from pathlib import Path

import httpx
from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

MessageChain = None
Plain = None
Record = None

try:
    from astrbot.api.message import MessageChain, Plain, Record
except ImportError:
    pass

if MessageChain is None:
    try:
        from astrbot.core.message.components import Plain, Record  # noqa: F401
        from astrbot.core.message.message_event_result import MessageChain
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
    """计算 instruction 字符长度，汉字按 2 计算。"""
    length = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            length += 2
        else:
            length += 1
    return length


@register(
    "astrbot_plugin_cosyecho",
    "NoFizz",
    "基于阿里云百炼 CosyVoice 声音复刻的 TTS 插件。支持 v3.5/v3 四款模型，通过指令控制情感、方言、语速等效果，群聊/私聊独立白名单与触发概率，可选翻译后合成",
    "1.0.2",
)
class CosyVoiceTTSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._available_models: list[str] = []
        self._audio_files: list[str] = []
        self._scan_task = None
        self._http_client: httpx.AsyncClient | None = None

        try:
            loop = asyncio.get_running_loop()
            self._scan_task = loop.create_task(self._scan_models_with_delay())
        except RuntimeError:
            pass

    async def terminate(self):
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
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

    async def _scan_models_with_delay(self):
        await asyncio.sleep(8)
        await self._scan_available_models()

    async def _scan_available_models(self):
        try:
            providers = self.context.get_all_providers()

            self._available_models = []
            for p in providers:
                pid = p.provider_config.get("id", "")
                ptype = p.provider_config.get("type", "")
                if pid and "tts" not in ptype.lower():
                    self._available_models.append(pid)

            if hasattr(self.config, "schema") and self.config.schema:
                if "translation_model" in self.config.schema:
                    self.config.schema["translation_model"]["options"] = (
                        self._available_models
                    )

            logger.info(f"扫描到 {len(self._available_models)} 个可用 LLM 模型")
        except Exception as e:
            logger.error(f"扫描可用模型失败: {e}")

    def _get_config_value(self, key: str, default=None):
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
        api_key = self._get_config_value("api_key", "")
        if not api_key:
            return False

        umo = event.unified_msg_origin
        group_id = event.message_obj.group_id

        if group_id:
            if not self._get_config_value("group_voice_enabled", True):
                return False
            if not self._check_whitelist("group_whitelist", umo):
                return False
            trigger_prob = self._get_config_value("group_trigger_probability", 0.2)
        else:
            if not self._get_config_value("private_voice_enabled", True):
                return False
            if not self._check_whitelist("private_whitelist", umo):
                return False
            trigger_prob = self._get_config_value("private_trigger_probability", 0.2)

        if trigger_prob < 1.0:
            if random.random() > trigger_prob:
                return False

        return True

    def _should_translate(self) -> bool:
        if not self._get_config_value("translation_enabled", False):
            return False
        if not self._get_config_value("translation_model", ""):
            return False
        if not self._get_config_value("system_prompt", ""):
            return False
        return True

    async def _translate_text(self, text: str) -> str:
        try:
            translation_model = self._get_config_value("translation_model", "")
            system_prompt = self._get_config_value("system_prompt", "")

            provider = self.context.get_provider_by_id(translation_model)
            if provider:
                llm_resp = await provider.text_chat(
                    prompt=text, system_prompt=system_prompt
                )
                if llm_resp and llm_resp.completion_text:
                    return llm_resp.completion_text.strip()
            return text
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return text

    def _parse_language_hint(self, language_hint: str) -> str:
        code = _LANGUAGE_NAME_TO_CODE.get(language_hint.strip())
        if code:
            return code
        return language_hint.strip()

    def _get_temp_dir(self) -> str:
        try:
            return str(get_astrbot_temp_path())
        except Exception:
            pass
        try:
            return str(StarTools.get_data_dir("astrbot_plugin_cosyecho"))
        except Exception:
            pass
        return tempfile.gettempdir()

    def _cleanup_audio_file(self, path: str):
        """发送后立即清理音频文件。"""
        if path in self._audio_files:
            self._audio_files.remove(path)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def _synthesize(self, text: str) -> str | None:
        api_key = self._get_config_value("api_key", "")
        if not api_key:
            return None

        model = self._get_config_value("model", "cosyvoice-v3.5-plus")
        voice = self._get_config_value("voice", "")
        if not voice:
            logger.error("音色 ID 为空，请在配置中填写音色 ID")
            return None

        volume = int(self._get_config_value("volume", 50))
        rate = float(self._get_config_value("rate", 1.0))
        pitch = float(self._get_config_value("pitch", 1.0))
        instruction = str(self._get_config_value("instruction", "")).strip()
        language = self._parse_language_hint(
            self._get_config_value("language_hint", "中文")
        )
        timeout = int(self._get_config_value("timeout", 20))

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
            "api_key": api_key,
        }
        if language:
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

        self._audio_files.append(path)
        logger.info(f"语音已保存: {path} ({len(resp)} bytes)")
        return path

    async def _download_audio(self, url: str, timeout: int) -> bytes | None:
        client = await self._get_http_client()
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """将 LLM 回复转为语音发送，支持翻译、白名单、触发概率控制"""
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

        send_text = self._get_config_value("send_text_with_voice", False)

        try:
            if Record is not None and MessageChain is not None:
                if send_text:
                    chain = MessageChain(
                        [
                            Comp.Plain(original_text),
                            Comp.Record(file=audio_path),
                        ]
                    )
                else:
                    chain = MessageChain(
                        [
                            Comp.Record(file=audio_path),
                        ]
                    )
                resp.result_chain = chain
            elif hasattr(resp, "result_chain") and hasattr(resp.result_chain, "chain"):
                resp.result_chain.chain = [Comp.Record(file=audio_path)]
            else:
                logger.error("无法构建消息链：MessageChain/Record 导入失败")
        except Exception as e:
            logger.error(f"发送语音失败: {e}")
        finally:
            self._cleanup_audio_file(audio_path)
