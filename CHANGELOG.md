# 更新日志

本项目的所有重要变更都会记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [2.1.0] - 2026-08-06

### Added

- **WebUI 界面预览图**：README 新增浅色/深色主题截图（`screenshots/`）。
- **AstrBot 版本徽章**：README 徽章补充 `AstrBot >= 4.17.0`（橙色）。
- **翻译模型回退链文档**：README 配置说明新增翻译回退链（配置模型 → 当前会话模型 → 发送原文）。
- **字体随插件打包**：Sarasa UI SC / Sarasa Gothic SC 子集化 woff2（各 400/600 两字重）随插件 `fonts/` 打包，用户无需手动安装字体；已装系统字体的用户走 `local()` 零下载。

### Changed

- **UI 全面升级为 NoFizz 设计美学**：Liquid Glass 玻璃拟态（`backdrop-filter: blur(28px) saturate(180%)` + 背景光斑）、Sarasa UI/Gothic 双链字体 + Birthstone 手写体标题、`--ctl-h: 39px` 统一控件高度、Header 无横幅设计、模式切换出屏动画（600ms `cubic-bezier(0.23,1,0.32,1)` + FLIP 补位，`prefers-reduced-motion` 下直接切换）。
- **README 重构**：按"功能简介 → 功能特性 → 界面预览 → 快速开始 → 使用示例 → 配置项说明 → 常见问题"重排；WebUI 设置改为四列表格式；"注意事项"转为 FAQ。
- **AGENTS.md 同步**：UI 设计规范章节更新为 NoFizz 设计美学（原 Bilibili 设计系统描述过时）。
- **版本同步 2.1.0**：metadata.yaml / README 徽章 / CHANGELOG / 前端 `?v=` 缓存号全部同步。

### Fixed

- **README 乱码**：修复第 86/92 行 UTF-8 替换符（"页面"、"获取"被损坏）。
- **metadata.yaml 解析**：`_get_plugin_version()` 由手写字符串解析改为 PyYAML（`yaml.safe_load` + `utf-8-sig`），兼容 BOM/引号/行内注释；解析失败记录 warning 而非静默返回。
- **异步处理器阻塞**：async 处理器内同步文件 I/O（保存设置/音色、创建目录、清理音频）全部改用 `asyncio.to_thread` 隔离，避免阻塞事件循环。
- **静默异常**：`_cleanup_audio_file` / `_get_temp_dir` / `terminate` 的静默 `except: pass` 补上 warning 日志。

## [2.0.3] - 2026-07-31

### Fixed

- **翻译模型下拉框显示冗余**：后端返回的 `name` 字段已含 `(model)` 后缀，前端又拼了一层 `(id)`，导致显示 `id (model)(id)` 三重嵌套。改为直接显示 `id`。

## [2.0.2] - 2026-07-31

### Changed

- **UI 重构**：从东方传统色双主题切换为 **Bilibili Web 设计系统**——品牌蓝 `#00AEEC` / 品牌粉 `#FB7299`，圆角操作元素 4px / 卡片 8px，标题衬线字体（Georgia / Songti SC），浅色白底 / 深色 `#18191C` 底。
- **按钮标准化**：所有保存/添加按钮统一使用 Material Symbols Rounded 图标（`save` / `add_2`），SVG path 内联本地化存储，无外部依赖；禁用态统一为蓝灰色（`opacity: 0.35`），启用态亮蓝色；UMO 白名单添加按钮随输入框内容启用/禁用。

### Fixed

- **保存按钮无法启用**：checkbox 类型表单元素缺失 `change` 事件监听器，导致勾选开关后保存按钮不亮起。已补全 `input[type='checkbox']` 到 catch-all 监听器。
- **音色表保存按钮图标丢失**：`textContent` 赋值会清除内联 SVG 图标，改为 `querySelector('.save-note-text').textContent` 精确更新文本。

## [2.0.1] - 2026-07-30

### Added

- **插件市场安装**：已上架 AstrBot Official Plugin Market，README 推荐安装方式改为通过插件源一键安装。

### Changed

- **插件展示名**：`display_name` 由"CosyEcho 语音合成（TTS）"更改为"CosyEcho 音色克隆/语音合成"，更准确反映功能定位。
- **UI 配色重构**：从日式传统色（nipponcolors / 縹色）切换为东方传统色双主题——浅色「汝窑天青」（天青主色 / 朱砂强调 / 竹青成功）、深色「玄夜鎏金」（绀宇主色 / 赤金强调 / 丹蔻错误）；标题字体改用思源宋体，强化层级与留白。
- **TTS 文本上限可自定义**：新增 `max_text_chars` 设置项（WebUI 可调，默认 1000，0 表示不限制）；超限时跳过语音仅发送原文，不再硬截断。
- **README 重写**：按统一规范重组文档结构，安装方式扩充为三种（插件市场 / GitHub / 手动）。

### Removed

- **仓库内开发者文档**：移除仓库内开发者文档，更新 .gitignore。

## [2.0.0] - 2026-07-25

v2.0.0 完整重构：双模式（系统音色 / 自定义音色）+ WebUI 配置面板 + 音色管理 + 指令控制 + 触发策略 + 翻译合成。