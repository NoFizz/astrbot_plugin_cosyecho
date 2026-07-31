# 更新日志

## [2.0.2] - 2026-07-31

### 新增

- **插件配置扩展**：`_conf_schema.json` 新增翻译设置配置项（`translation_model` 标记 `_special: "select_provider"` 供 model_manager 发现、`translation_enabled` 翻译开关、`language_hint` 目标语言下拉框、`system_prompt` 系统提示词），支持通过 AstrBot 原生配置面板和 model_manager 统一管理。
- **`_get_setting()` 配置优先级**：新增 `_CONFIG_PRIORITY_KEYS`，对翻译相关键优先从 `self.config`（`_conf_schema.json` 持久化）读取，支持 model_manager 批量写入。

### 变更

- **UI 重构**：从东方传统色双主题切换为 **Bilibili Web 设计系统**——品牌蓝 `#00AEEC` / 品牌粉 `#FB7299`，圆角操作元素 4px / 卡片 8px，标题衬线字体（Georgia / Songti SC），浅色白底 / 深色 `#18191C` 底。
- **按钮标准化**：所有保存/添加按钮统一使用 Material Symbols Rounded 图标（`save` / `add_2`），SVG path 内联本地化存储，无外部依赖；禁用态统一为蓝灰色（`opacity: 0.35`），启用态亮蓝色；UMO 白名单添加按钮随输入框内容启用/禁用。

### 修复

- **`language_hint` 配置类型**：`_conf_schema.json` 中 `language_hint` 类型从不支持的 `select` 改为 `string` + `options` 枚举，兼容 AstrBot 配置面板。

## [2.0.1] - 2026-07-30

### 新增

- **插件市场安装**：已上架 AstrBot Official Plugin Market，README 推荐安装方式改为通过插件源一键安装。

### 变更

- **插件展示名**：`display_name` 由"CosyEcho 语音合成（TTS）"更改为"CosyEcho 音色克隆/语音合成"，更准确反映功能定位。
- **UI 配色重构**：从日式传统色（nipponcolors / 縹色）切换为东方传统色双主题——浅色「汝窑天青」（天青主色 / 朱砂强调 / 竹青成功）、深色「玄夜鎏金」（绀宇主色 / 赤金强调 / 丹蔻错误）；标题字体改用思源宋体，强化层级与留白。
- **TTS 文本上限可自定义**：新增 `max_text_chars` 设置项（WebUI 可调，默认 1000，0 表示不限制）；超限时跳过语音仅发送原文，不再硬截断。
- **README 重写**：按统一规范重组文档结构，安装方式扩充为三种（插件市场 / GitHub / 手动）。

### 内部

- 移除仓库内开发者文档，更新 .gitignore。

## [2.0.0] - 2026-07-25

v2.0.0 完整重构：双模式（系统音色 / 自定义音色）+ WebUI 配置面板 + 音色管理 + 指令控制 + 触发策略 + 翻译合成。
