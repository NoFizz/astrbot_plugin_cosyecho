"""CosyEcho - 基于阿里云百炼 CosyVoice 的 AstrBot TTS 插件。

支持两种音色模式：系统音色 / 自定义音色（复刻与设计合并）。
所有配置通过 AstrBot Dashboard 内嵌 WebUI 管理。
"""

import asyncio
import json
import os
import random
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import dashscope
import httpx
from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.web import error_response, json_response, request
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path

from .voices_data import (
    MODEL_CAPABILITIES,
    SUPPORTED_LANGUAGES,
    get_available_models,
    get_instruction_support,
    get_system_voices_for_model,
)

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

PLUGIN_NAME = "astrbot_plugin_cosyecho"

# instruction 长度限制
_INSTRUCTION_MAX_CHARS = 100
# TTS 文本最大字符数默认值（可在 WebUI 中自定义）
_DEFAULT_MAX_TEXT_CHARS = 1000
# _pending_audio 最大追踪路径数
_MAX_PENDING_AUDIO_PATHS = 100

# 默认设置
_DEFAULT_SETTINGS = {
    "mode": "system",
    "model": "cosyvoice-v3-flash",
    "voice": "longanyang",
    "format": "wav",
    "sample_rate": 24000,
    "volume": 50,
    "rate": 1.0,
    "pitch": 1.0,
    "instruction": "",
    "language_hint": "zh",
    "seed": 0,
    "max_text_chars": _DEFAULT_MAX_TEXT_CHARS,
    "enable_markdown_filter": False,
    "group_voice_enabled": True,
    "group_whitelist": [],
    "group_trigger_probability": 0.2,
    "private_voice_enabled": True,
    "private_whitelist": [],
    "private_trigger_probability": 0.2,
    "send_text_with_voice": False,
    "translation_enabled": False,
    "translation_model": "",
    "system_prompt": "把下面的文本翻译成日语，不要额外解释",
    "timeout": 20,
    "mode_presets": {},
}

# 旧版 language_hint 中文名 → 代码映射（用于 v1.x 配置迁移）
_LEGACY_LANG_NAME_TO_CODE = {
    "中文": "zh", "英文": "en", "法语": "fr", "德语": "de",
    "日语": "ja", "韩语": "ko", "俄语": "ru", "葡萄牙语": "pt",
    "泰语": "th", "印尼语": "id", "越南语": "vi",
}


def _count_instruction_length(text: str) -> int:
    """计算 instruction 字符长度，全角/宽字符按 2 计算。"""
    length = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            length += 2
        else:
            length += 1
    return length


def _truncate_instruction(text: str, max_len: int = _INSTRUCTION_MAX_CHARS) -> str:
    """截断 instruction 至指定长度（O(n) 单趟遍历）。"""
    if _count_instruction_length(text) <= max_len:
        return text
    length = 0
    for i, ch in enumerate(text):
        char_len = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if length + char_len > max_len:
            return text[:i]
        length += char_len
    return text


class CosyVoiceTTSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._audio_files: set[str] = set()
        self._pending_audio: dict[str, set[str]] = {}
        self._http_client: httpx.AsyncClient | None = None

        # 数据目录
        self._data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path = self._data_dir / "settings.json"
        self._voices_path = self._data_dir / "voices_data.json"

        # 加载设置和音色数据
        self._settings = self._load_settings()
        self._voices_data = self._load_voices_data()

        # 注册 Web API
        self._register_web_apis(context)

    # ========== 数据持久化 ==========

    def _load_settings(self) -> dict:
        """加载设置，缺失字段用默认值补全。首次升级时从旧版 _conf_schema 配置迁移。"""
        settings = dict(_DEFAULT_SETTINGS)
        # settings.json 不存在 → 可能是从 v1.x 升级，尝试一次性迁移旧配置
        if not self._settings_path.exists():
            self._migrate_legacy_config(settings)
        try:
            if self._settings_path.exists():
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                settings.update(saved)
        except Exception as e:
            logger.warning(f"加载设置失败，使用默认值: {e}")
        return settings

    def _migrate_legacy_config(self, settings: dict):
        """从 v1.x 经 _conf_schema 持久化的旧配置做一次性迁移（尽力而为）。"""
        try:
            legacy_keys = (
                "model", "voice", "volume", "rate", "pitch", "instruction", "timeout",
                "group_voice_enabled", "group_whitelist", "group_trigger_probability",
                "private_voice_enabled", "private_whitelist", "private_trigger_probability",
                "send_text_with_voice", "translation_enabled", "translation_model",
                "system_prompt",
            )
            migrated = False
            for k in legacy_keys:
                try:
                    v = self.config.get(k)
                except Exception:
                    v = None
                if v is not None:
                    settings[k] = v
                    migrated = True
            # language_hint 旧值为中文名，映射为代码
            try:
                old_lang = self.config.get("language_hint")
            except Exception:
                old_lang = None
            if old_lang:
                settings["language_hint"] = _LEGACY_LANG_NAME_TO_CODE.get(old_lang, old_lang)
                migrated = True
            if migrated:
                self._settings = settings
                self._save_settings()
                logger.info("已从旧版配置迁移插件设置")
        except Exception as e:
            logger.warning(f"迁移旧配置失败: {e}")

    def _save_settings(self):
        """保存设置到文件。"""
        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存设置失败: {e}")

    def _load_voices_data(self) -> dict:
        """加载音色元数据。"""
        default = {"custom_voices": [], "last_sync_at": None}
        try:
            if self._voices_path.exists():
                with open(self._voices_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                default.update(data)
        except Exception as e:
            logger.warning(f"加载音色数据失败: {e}")
        return default

    def _save_voices_data(self):
        """保存音色元数据到文件。"""
        try:
            with open(self._voices_path, "w", encoding="utf-8") as f:
                json.dump(self._voices_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存音色数据失败: {e}")

    def _get_setting(self, key: str, default=None):
        """获取设置值。"""
        return self._settings.get(key, default if default is not None else _DEFAULT_SETTINGS.get(key))

    # ========== Web API 注册 ==========

    def _register_web_apis(self, context: Context):
        apis = [
            (f"/{PLUGIN_NAME}/settings", self.api_get_settings, ["GET"], "获取设置"),
            (f"/{PLUGIN_NAME}/settings/save", self.api_save_settings, ["POST"], "保存设置"),
            (f"/{PLUGIN_NAME}/voices", self.api_get_voices, ["GET"], "获取音色列表"),
            (f"/{PLUGIN_NAME}/voices/sync", self.api_sync_voices, ["POST"], "同步音色"),
            (f"/{PLUGIN_NAME}/voices/note", self.api_update_note, ["POST"], "更新备注"),
            (f"/{PLUGIN_NAME}/voices/delete", self.api_delete_voice, ["POST"], "删除音色"),
            (f"/{PLUGIN_NAME}/models", self.api_get_models, ["GET"], "获取模型信息"),
            (f"/{PLUGIN_NAME}/info", self.api_get_info, ["GET"], "获取插件信息"),
            (f"/{PLUGIN_NAME}/providers", self.api_get_providers, ["GET"], "获取已配置的聊天模型"),
        ]
        for route, handler, methods, desc in apis:
            context.register_web_api(route, handler, methods, desc)

    # ========== Web API 处理函数 ==========

    async def api_get_settings(self):
        return json_response(self._settings)

    async def api_save_settings(self):
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("无效的设置数据")
        # 仅接受已知字段
        for key in _DEFAULT_SETTINGS:
            if key in payload:
                self._settings[key] = payload[key]
        self._save_settings()
        return json_response({"saved": True})

    async def api_get_voices(self):
        model = request.query.get("model", "")
        mode = request.query.get("mode", "")
        result = {"system_voices": [], "custom_voices": [], "languages": SUPPORTED_LANGUAGES}
        if mode == "system" and model:
            result["system_voices"] = get_system_voices_for_model(model)
        if mode == "custom" and model:
            result["custom_voices"] = [
                v for v in self._voices_data["custom_voices"]
                if v["model"] == model
            ]
        result["last_sync_at"] = self._voices_data.get("last_sync_at")
        return json_response(result)

    async def api_sync_voices(self):
        """从百炼 API 同步自定义音色列表。"""
        api_key = self._get_api_key()
        if not api_key:
            return error_response("请先在插件配置中填写 API Key")
        try:
            client = await self._get_http_client()
            resp = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "voice-enrollment", "input": {"action": "list_voice"}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            voice_list = data.get("output", {}).get("voice_list", [])

            # 保留已有备注
            existing_notes = {v["voice_id"]: v.get("note", "") for v in self._voices_data["custom_voices"]}
            new_voices = []
            for item in voice_list:
                vid = item.get("voice_id", item.get("voice", ""))
                if not vid:
                    continue
                # 从 voice_id 推断模型（格式通常为 model-prefix-xxx）
                model = self._infer_model_from_voice_id(vid, item)
                new_voices.append({
                    "voice_id": vid,
                    "model": model,
                    "type": "custom",
                    "note": existing_notes.get(vid, ""),
                    "added_at": item.get("gmt_create", datetime.now(timezone.utc).isoformat()),
                })
            self._voices_data["custom_voices"] = new_voices
            self._voices_data["last_sync_at"] = datetime.now(timezone.utc).isoformat()
            self._save_voices_data()
            return json_response({"synced": len(new_voices), "voices": new_voices})
        except Exception as e:
            logger.error(f"同步音色失败: {e}")
            return error_response(f"同步失败: {e}")

    async def api_update_note(self):
        payload = await request.json(default={})
        voice_id = payload.get("voice_id", "")
        note = payload.get("note", "")
        if not voice_id:
            return error_response("缺少 voice_id")
        for v in self._voices_data["custom_voices"]:
            if v["voice_id"] == voice_id:
                v["note"] = note
                self._save_voices_data()
                return json_response({"updated": True})
        return error_response("未找到该音色")

    async def api_delete_voice(self):
        payload = await request.json(default={})
        voice_id = payload.get("voice_id", "")
        delete_remote = payload.get("delete_remote", False)
        if not voice_id:
            return error_response("缺少 voice_id")

        # 从本地移除
        self._voices_data["custom_voices"] = [
            v for v in self._voices_data["custom_voices"] if v["voice_id"] != voice_id
        ]
        self._save_voices_data()

        # 可选：从百炼远程删除
        if delete_remote:
            api_key = self._get_api_key()
            if api_key:
                try:
                    client = await self._get_http_client()
                    await client.post(
                        "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": "voice-enrollment", "input": {"action": "delete_voice", "voice_id": voice_id}},
                        timeout=30,
                    )
                except Exception as e:
                    logger.warning(f"远程删除音色失败: {e}")

        return json_response({"deleted": True})

    async def api_get_models(self):
        return json_response({
            "capabilities": MODEL_CAPABILITIES,
            "languages": SUPPORTED_LANGUAGES,
            "models_by_mode": {
                "system": get_available_models("system"),
                "custom": get_available_models("custom"),
            },
        })

    async def api_get_info(self):
        """获取插件基本信息（版本号等）。"""
        return json_response({
            "name": PLUGIN_NAME,
            "version": self._get_plugin_version(),
        })

    async def api_get_providers(self):
        """获取 AstrBot 已配置的聊天模型列表。"""
        providers = []
        try:
            mgr = self.context.provider_manager
            for inst in mgr.provider_insts:
                pid = inst.provider_config.get("id", "")
                model = inst.get_model()
                if pid:
                    display = f"{pid} ({model})" if model else pid
                    providers.append({"id": pid, "name": display})
        except Exception as e:
            logger.warning(f"获取模型列表失败: {e}")
        return json_response({"providers": providers})

    def _get_plugin_version(self) -> str:
        """从 metadata.yaml 读取插件版本号。"""
        try:
            meta_path = Path(__file__).parent / "metadata.yaml"
            content = meta_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("version:"):
                    return line.split(":", 1)[1].strip().strip("\"'")
        except Exception:
            pass
        return "unknown"

    # ========== TTS 核心逻辑 ==========

    def _get_api_key(self) -> str:
        """获取 API Key（优先从 _conf_schema 配置读取）。"""
        try:
            return self.config.get("api_key", "")
        except Exception:
            return ""

    def _infer_model_from_voice_id(self, voice_id: str, item: dict) -> str:
        """从 voice_id 或 API 返回数据推断所属模型。"""
        # API 可能直接返回 target_model 字段
        if item.get("target_model"):
            return item["target_model"]
        # 从 voice_id 前缀推断
        for model in MODEL_CAPABILITIES:
            if voice_id.startswith(model):
                return model
        return self._get_setting("model", "cosyvoice-v3-flash")

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    def _get_temp_dir(self) -> str:
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
        self._audio_files.discard(path)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    async def _synthesize(self, text: str) -> str | None:
        """调用 CosyVoice API 合成语音，返回音频文件路径。"""
        api_key = self._get_api_key()
        if not api_key:
            return None

        dashscope.api_key = api_key

        model = self._get_setting("model", "cosyvoice-v3-flash")
        voice = self._get_setting("voice", "")
        if not voice:
            logger.error("音色 ID 为空，请在 WebUI 中选择音色")
            return None

        volume = int(self._get_setting("volume", 50))
        rate = float(self._get_setting("rate", 1.0))
        pitch = float(self._get_setting("pitch", 1.0))
        language = self._get_setting("language_hint", "zh")
        timeout = int(self._get_setting("timeout", 20))
        seed = int(self._get_setting("seed", 0))
        instruction = str(self._get_setting("instruction", "")).strip()
        mode = self._get_setting("mode", "system")

        # 判断指令是否可用
        voice_type = "system" if mode == "system" else "custom"
        instr_support = get_instruction_support(model, voice_type)
        if instr_support == "none":
            instruction = ""
        elif instruction:
            instruction = _truncate_instruction(instruction)
            if instruction != str(self._get_setting("instruction", "")).strip():
                logger.warning(f"instruction 已截断为: {instruction}")

        temp_dir = self._get_temp_dir()
        os.makedirs(temp_dir, exist_ok=True)

        call_kwargs = {
            "model": model,
            "text": text,
            "voice": voice,
            "format": self._get_setting("format", "wav"),
            "sample_rate": int(self._get_setting("sample_rate", 24000)),
            "volume": volume,
            "rate": rate,
            "pitch": pitch,
            "language_hints": [language],
        }
        if seed > 0:
            call_kwargs["seed"] = seed
        if instruction:
            call_kwargs["instruction"] = instruction
        if self._get_setting("enable_markdown_filter", False):
            call_kwargs["enable_markdown_filter"] = True

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: HttpSpeechSynthesizer.call(**call_kwargs)
            )
        except Exception as e:
            logger.error(f"TTS API 异常: {e}")
            return None

        if not result or not result.audio_url:
            logger.error(f"TTS 返回空结果: {result}")
            return None

        try:
            client = await self._get_http_client()
            resp = await client.get(result.audio_url, timeout=timeout)
            resp.raise_for_status()
            audio_data = resp.content
        except Exception as e:
            logger.error(f"下载音频失败: {e}")
            return None

        if not audio_data:
            logger.error("TTS 返回空数据")
            return None

        path = os.path.join(temp_dir, f"cosyecho_{uuid.uuid4()}.wav")
        await loop.run_in_executor(None, Path(path).write_bytes, audio_data)
        self._audio_files.add(path)
        logger.info(f"语音已保存: {path} ({len(audio_data)} bytes)")
        return path

    # ========== 翻译 ==========

    def _should_translate(self) -> bool:
        """判断是否需要翻译。翻译模型可为空（自动回退到当前会话模型）。"""
        if not self._get_setting("translation_enabled", False):
            return False
        if not self._get_setting("system_prompt", ""):
            return False
        return True

    async def _resolve_translation_provider(self, umo: str) -> str:
        """解析翻译模型 ID：配置的模型为空时回退到当前会话的对话模型。"""
        provider_id = self._get_setting("translation_model", "")
        if not provider_id:
            try:
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            except Exception:
                provider_id = ""
        return provider_id or ""

    async def _translate_text(self, text: str, umo: str) -> str:
        """通过 LLM 翻译文本。模型调用失败时自动回退到当前会话的对话模型。"""
        provider_id = await self._resolve_translation_provider(umo)
        if not provider_id:
            logger.warning("无可用翻译模型，跳过翻译")
            return text

        system_prompt = self._get_setting("system_prompt", "")

        try:
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=text,
                system_prompt=system_prompt,
            )
            if llm_resp and llm_resp.completion_text:
                translated = llm_resp.completion_text.strip()
                if translated:
                    return translated
            return text
        except Exception as e:
            logger.warning(f"翻译模型 {provider_id} 调用失败: {e}，尝试回退到会话模型")

        # 回退：使用当前会话的对话模型重试
        try:
            fallback_id = await self.context.get_current_chat_provider_id(umo=umo)
            if fallback_id and fallback_id != provider_id:
                llm_resp = await self.context.llm_generate(
                    chat_provider_id=fallback_id,
                    prompt=text,
                    system_prompt=system_prompt,
                )
                if llm_resp and llm_resp.completion_text:
                    translated = llm_resp.completion_text.strip()
                    if translated:
                        return translated
        except Exception as e2:
            logger.error(f"翻译回退模型也失败: {e2}")
        return text

    # ========== 触发控制 ==========

    def _check_whitelist(self, config_key: str, umo: str) -> bool:
        whitelist = self._get_setting(config_key, [])
        if isinstance(whitelist, str):
            whitelist = [s.strip() for s in whitelist.split(",") if s.strip()]
        whitelist_str = [str(x) for x in whitelist]
        return not whitelist_str or umo in whitelist_str

    def _should_process_message(self, event: AstrMessageEvent) -> bool:
        if not self._get_api_key():
            return False
        umo = event.unified_msg_origin
        if event.is_private_chat():
            if not self._get_setting("private_voice_enabled", True):
                return False
            if not self._check_whitelist("private_whitelist", umo):
                return False
            trigger_prob = float(self._get_setting("private_trigger_probability", 0.2))
        else:
            if not self._get_setting("group_voice_enabled", True):
                return False
            if not self._check_whitelist("group_whitelist", umo):
                return False
            trigger_prob = float(self._get_setting("group_trigger_probability", 0.2))

        if trigger_prob < 1.0 and random.random() > trigger_prob:
            return False
        return True

    # ========== 事件钩子 ==========

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """将 LLM 回复转为语音发送。"""
        if getattr(resp, "is_chunk", False):
            return
        if not self._should_process_message(event):
            return

        original_text = (resp.completion_text or "").strip()
        if not original_text:
            return

        umo = event.unified_msg_origin

        text_to_speak = original_text
        if self._should_translate():
            translated = await self._translate_text(original_text, umo)
            if translated != original_text:
                text_to_speak = translated

        # 文本超过上限则跳过语音，仅发送原文（上限可在 WebUI 自定义，0 表示不限制）
        # 此处直接 return 不修改消息链，原文将作为普通文本正常发出，不受“同时发送原文”开关影响
        max_chars = int(self._get_setting("max_text_chars", _DEFAULT_MAX_TEXT_CHARS))
        if max_chars > 0 and len(text_to_speak) > max_chars:
            logger.info(f"TTS 文本过长（{len(text_to_speak)} > {max_chars}），跳过语音仅发送文本")
            return

        try:
            audio_path = await self._synthesize(text_to_speak)
        except Exception as e:
            logger.error(f"语音合成异常: {e}")
            return

        if not audio_path:
            logger.error("语音合成失败，跳过发送")
            return

        # 安全阀
        total_pending = sum(len(s) for s in self._pending_audio.values())
        if total_pending >= _MAX_PENDING_AUDIO_PATHS:
            logger.warning(f"待清理音频数（{total_pending}）达上限，强制清理")
            for paths in self._pending_audio.values():
                for p in paths:
                    self._cleanup_audio_file(p)
            self._pending_audio.clear()

        self._pending_audio.setdefault(umo, set()).add(audio_path)

        send_text = self._get_setting("send_text_with_voice", False)
        try:
            if Record is not None and MessageChain is not None:
                if send_text:
                    chain = MessageChain([
                        Comp.Plain(original_text),
                        Comp.Record(file=audio_path, url=audio_path),
                    ])
                else:
                    chain = MessageChain([Comp.Record(file=audio_path, url=audio_path)])
                resp.result_chain = chain
            elif hasattr(resp, "result_chain") and hasattr(resp.result_chain, "chain"):
                resp.result_chain.chain.append(Comp.Record(file=audio_path, url=audio_path))
            else:
                logger.error("无法构建消息链：MessageChain/Record 导入失败")
        except Exception as e:
            logger.error(f"发送语音失败: {e}")
            self._cleanup_audio_file(audio_path)

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        """消息发送后清理临时音频文件。"""
        umo = event.unified_msg_origin
        paths = self._pending_audio.pop(umo, set())
        for path in paths:
            self._cleanup_audio_file(path)

    # ========== 生命周期 ==========

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
