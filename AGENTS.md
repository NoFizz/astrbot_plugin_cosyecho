# AGENTS.md

This file provides guidance to Lingma (lingma.aliyun.com) when working with code in this repository.

## 项目性质

这是一个 **AstrBot 插件**（`astrbot_plugin_cosyecho`），不是独立应用。它运行在 AstrBot 实例内部，通过拦截 LLM 回复将文本合成为语音（基于阿里云百炼 CosyVoice）。因此**没有构建、测试、lint 命令**，也没有测试套件。

**运行环境要求**：Python >= 3.10、AstrBot >= 4.26.0、仅支持 aiocqhttp（OneBot QQ）平台。

## 开发工作流

- 安装依赖：`pip install -r requirements.txt`（`dashscope`、`httpx`）。
- 开发循环 = 修改代码 → 在 AstrBot WebUI「插件管理」中**重载插件**（或重启 AstrBot）。插件代码修改后必须重载才生效。
- **纯前端改动**（`pages/settings/` 下的 html/js/css）由 Dashboard 直接静态托管，**刷新 Page 页面即可**，无需重载插件。
- 插件目录路径即工作区：`.../core/data/plugins/astrbot_plugin_cosyecho`。

## 关键约束（踩过的坑）

- **包内导入必须用相对导入**：AstrBot 通过 `__import__('data.plugins.astrbot_plugin_cosyecho.main', fromlist=[...])` 加载插件，插件目录被视为 Python 包。导入同目录模块必须写 `from .voices_data import ...`，用绝对导入会报 `ModuleNotFoundError`。
- **`MessageChain` / `Record` 有跨版本兼容导入**：`main.py` 顶部先尝试 `astrbot.api`，失败再回退 `astrbot.core`，两者都失败时为 `None`。改动消息链构建逻辑时必须保留这个回退结构。

## 架构（需跨文件理解的部分）

### 双层配置体系
- `_conf_schema.json` 仅包含 `api_key`，走 AstrBot 原生配置面板，读入 `self.config`。
- 其余**全部配置**存于 data 目录的 `settings.json`（路径：`get_astrbot_data_path()/plugin_data/astrbot_plugin_cosyecho/`），由 WebUI 管理。
- `main.py` 中的 `_DEFAULT_SETTINGS` 是配置键与默认值的**唯一事实来源**。`api_save_settings` 只接受 `_DEFAULT_SETTINGS` 中已声明的键——**新增配置项必须同时加进 `_DEFAULT_SETTINGS`**，否则保存会被静默丢弃。
- 音色元数据（自定义音色 + 备注 + 同步时间）单独存于同目录 `voices_data.json`。

### WebUI（AstrBot 插件 Page）
- 页面位于 `pages/settings/{index.html, app.js, style.css}`，通过 `window.AstrBotPluginPage` bridge 与后端通信。
- `app.js` 是 **ES Module + top-level await**：首行 `const bridge = window.AstrBotPluginPage`，随后 `await bridge.ready()` 初始化上下文。修改前端时注意保持顶层 await 结构，不要包裹进 `DOMContentLoaded` 或 IIFE。
- 后端用 `context.register_web_api()` 注册端点，路由前缀为 `/astrbot_plugin_cosyecho/`；前端调用时只用相对路径（如 `apiGet("models")`、`apiPost("voices/note", {...})`）。
- 新增后端端点 = 在 `_register_web_apis` 列表中登记 + 实现 handler；新增前端调用 = 用 bridge 的 `apiGet/apiPost`。
- 已注册端点：`settings`(GET)、`settings/save`(POST)、`voices`(GET)、`voices/sync`(POST)、`voices/note`(POST)、`voices/delete`(POST)、`models`(GET)、`info`(GET)、`providers`(GET)。

### 模型能力矩阵（单一事实来源）
- `voices_data.py::MODEL_CAPABILITIES` 定义每个模型是否支持系统音色/自定义音色、以及指令（instruction）规则（自由 / 固定格式 / 不支持）。系统音色列表也在该文件。
- 它**同时驱动两端**：后端 `_synthesize()` 据此决定是否下发 `instruction`；前端据此筛选可用模型、音色池并动态显隐指令输入区。改动模型能力时只改这一处。

### 音色池隔离
- 自定义音色（复刻/设计）在百炼平台创建时通过 `target_model` 绑定到具体模型，**不能跨模型使用**。UI 按所选模型过滤音色；`mode` 只有 `system` 和 `custom` 两值（复刻与设计已合并为 `custom`）。
- `settings.json` 中的 `mode_presets` 按模式缓存 `{model, voice, instruction}`，切换模式时恢复；加载时会将历史遗留的 `cloned`/`designed` 迁移为 `custom`。

### TTS 管线（`on_llm_response` 钩子）
触发门控（白名单 + 概率）→ 可选 LLM 翻译 → 文本截断（`max_text_chars` 设置项，0=不限）→ `_synthesize()` → 用 `Record` 消息链替换 `resp.result_chain`。
- `_synthesize()` 用 `loop.run_in_executor` 包裹同步的 `HttpSpeechSynthesizer.call`（返回音频 URL），再用 httpx 异步下载到临时文件。整个合成流程对事件循环非阻塞。
- **翻译回退**：翻译模型为空或调用失败时，自动回退到当前会话的对话模型（`context.get_current_chat_provider_id`）。
- **文本超限行为**：超过 `max_text_chars` 时直接 return 不修改消息链，原文作为普通文本正常发出（不受 `send_text_with_voice` 开关影响）。

### 音频生命周期
临时音频文件由 `_audio_files` + 按 UMO 分组的 `_pending_audio` 追踪，在 `after_message_sent` 钩子中清理；`_MAX_PENDING_AUDIO_PATHS` 是防止发送失败导致泄漏的安全阀；`terminate()` 做最终清理。

## UI 设计规范（用户既定要求）

- 字体：正文系统无衬线字体栈（`-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", ...`），标题衬线字体（`Georgia, "Times New Roman", "Songti SC", "Noto Serif SC", ...`）。
- 配色：**Bilibili Web 设计系统**——品牌蓝 `#00AEEC`（主色/按钮底）、品牌粉 `#FB7299`（强调/链接/指示条）。浅色白底 `#F5F6F8` / 深色 `#18191C` 底。禁止使用东方传统色/日式传统色变量。
- 圆角：操作元素 4px（`--radius-sm`）、卡片 8px（`--radius`）、按钮 4px、UMO 标签胶囊形 20px。
- 开关：iOS 风格滑动开关（开启态主色 `var(--primary)`、弹性缓动、按住拉伸），CSS 选择器须用 `.form-group label.switch` 以压过 `.form-group label` 的 `display:block`。
- 按钮图标：Material Symbols Rounded，SVG path 内联，无外部 CDN 依赖。保存按钮用 `save` 图标、添加按钮用 `add_2` 图标。禁用态统一 `opacity: 0.35`。
- 音色下拉项格式：`备注名｜voice_id`（备注在左，无备注仅显示 voice_id）。
- 白名单：UMO 标签式输入（输入框 + 添加按钮，添加按钮随输入框内容启用/禁用，标签带 × 可删，每行 2 个），非逗号分隔文本。
