# AGENTS.md — astrbot_plugin_cosyecho

## What this is

Single-file AstrBot plugin (`main.py`, ~360 lines) that hooks into LLM responses and converts text to speech using Alibaba Cloud's CosyVoice voice-cloning API. Dependencies (`dashscope`, `httpx`) are declared in `requirements.txt` and also provided by AstrBot core. Requires AstrBot >=4.26.0.

## Architecture

- `main.py` — everything: config loading, translation, TTS synthesis, event handling
- `_conf_schema.json` — plugin config schema (AstrBot renders UI from this)
- `metadata.yaml` — AstrBot plugin metadata (name, version, repo, support_platforms)
- No tests, no build step, no CLI, no linting

## Key files to read when changing behavior

| Concern | Location |
|---------|----------|
| Config schema / defaults | `_conf_schema.json` |
| Whitelist / trigger logic | `_should_process_message()` |
| TTS API call | `_synthesize()` — `HttpSpeechSynthesizer.call()` |
| Message rewriting | `on_llm_response()` — replaces `resp.result_chain` |
| Audio cleanup | `after_message_sent()` — cleans up per-message temp audio files |

## Important gotchas

- **No `@register` decorator**: Relies on `metadata.yaml` for plugin identity. AstrBot auto-discovers `Star` subclasses since v3.5.19+.
- **MessageChain/Record import fallback chain** (lines 18–31): Two import paths tried in sequence. `Plain` is always available via `Comp.Plain`.
- **Audio file lifecycle**: `_pending_audio` tracks paths per-UMO. Cleanup in `after_message_sent()` per-message, plus `terminate()` as兜底. AstrBot processes messages serially per session, so同一 UMO 不会并发触发钩子。
- **`is_chunk` filter**: `on_llm_response` skips `resp.is_chunk == True` to avoid duplicate TTS on streaming LLM output.
- **Instruction length limit**: 100 chars, CJK chars count as 2. Enforced by `_count_instruction_length()` and the API.
- **Translation uses `llm_generate`**: Official API with `system_prompt` parameter (verified in source).
- **Config slider fields**: Use `"slider": {"min": ..., "max": ..., "step": ...}`. No top-level `min`/`max`/`step`.
- **Numerical config safety**: `_safe_int()` / `_safe_float()` prevent `ValueError` from malformed input.
- **API Key handling**: Set via `dashscope.api_key = api_key` before calling `HttpSpeechSynthesizer.call()`. Do NOT pass `api_key` as a kwarg to `call()` — the SDK does not accept it.
- **Plugin name**: Uses `self.name` (not hardcoded), requires AstrBot >=4.9.2.

## Running / testing

No formal test suite. This plugin runs inside AstrBot's plugin runtime. To test:

1. Install into AstrBot via plugin market or by placing in `plugins/` dir
2. Configure API key, voice ID, and model in plugin settings
3. Send messages that trigger LLM responses — voice should accompany replies

## Config structure

Config keys map 1:1 to `_conf_schema.json`. Access via `self.config.get(key, default)`. When adding a new config key, add it to `_conf_schema.json` first.

## Dependencies

Declared in `requirements.txt`:
- `dashscope>=1.14.0` — Alibaba Cloud SDK (`HttpSpeechSynthesizer`)
- `httpx>=0.24.0` — async HTTP client for downloading audio

Both are also provided by AstrBot core; the declarations are defensive.
