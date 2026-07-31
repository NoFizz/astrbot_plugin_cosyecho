<h1 align="center">CosyEcho 音色克隆/语音合成/astrbot_plugin_cosyecho</h1>

<p align="center">
  <img src="logo.png" width="128" height="128" alt="astrbot_plugin_cosyecho logo">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.2-blue" alt="version">
  <img src="https://img.shields.io/badge/license-AGPL--3.0-green" alt="license">
  <img src="https://img.shields.io/badge/AstrBot->=4.26.0-orange" alt="AstrBot version">
  <img src="https://img.shields.io/badge/platform-aiocqhttp-lightgrey" alt="platform">
</p>

基于阿里云百炼 CosyVoice 的 AstrBot 语音合成插件。LLM 回复自动转为语音发送，支持系统音色、自定义音色两种模式，内置 WebUI 配置面板。

## 功能特性

- **两种音色模式**：系统内置音色 / 自定义音色（复刻与设计）
- **WebUI 管理面板**：在 AstrBot Dashboard 内直接配置所有参数，Material Symbols 图标按钮（保存 / 添加），禁用态自动变灰
- **音色管理**：自动同步百炼账号下的自定义音色，按模型池筛选，支持备注（保存按钮图标化，修改后自动点亮）
- **指令控制**：通过自然语言指令控制情感、方言、语速等合成效果
- **触发策略**：群聊/私聊独立白名单与触发概率控制，白名单采用 UMO 标签式输入（添加按钮随输入框内容启用/禁用）
- **翻译合成**：可选 LLM 翻译后再合成语音，翻译模型支持 model_manager 统一管理
- **双层配置体系**：`_conf_schema.json` 暴露翻译设置供 model_manager 发现与批量写入，其余设置通过 WebUI 管理

## 支持的模型

| 模型 | 系统音色 | 复刻/设计音色 | 指令(自定义音色) | 指令(系统音色) |
|------|---------|-------------|---------------|-------------|
| cosyvoice-v3.5-plus | 不支持 | 支持 | 任意自然语言 | - |
| cosyvoice-v3.5-flash | 不支持 | 支持 | 任意自然语言 | - |
| cosyvoice-v3-plus | 支持 | 支持 | 不支持 | 固定格式 |
| cosyvoice-v3-flash | 支持 | 支持 | 任意自然语言 | 固定格式 |

## 安装

### 方法一：通过插件市场安装（推荐）

1. 打开 AstrBot WebUI → 插件管理 → 插件市场。
2. 添加插件源（如尚未添加）：
   - 源名称：`AstrBot Official Plugin Market`
   - 源地址：`https://cloud-test.astrbot.app/api/v1/market/plugins.json`
3. 在插件市场中搜索 **CosyEcho**（`astrbot_plugin_cosyecho`），点击安装。
4. 等待安装完成，确认插件已启用。

### 方法二：从 GitHub 安装

1. 打开 AstrBot WebUI → 插件管理 → 新增插件。
2. 选择 **从 GitHub 安装**。
3. 填入仓库地址：
   ```
   https://github.com/NoFizz/astrbot_plugin_cosyecho
   ```
4. 等待安装完成，确认插件已启用。

### 方法三：手动安装

1. 将本仓库克隆或下载到 AstrBot 的插件目录：
   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/NoFizz/astrbot_plugin_cosyecho.git
   ```
2. 安装依赖：
   ```bash
   pip install -r astrbot_plugin_cosyecho/requirements.txt
   ```
3. 在 AstrBot WebUI 中重载插件，或重启 AstrBot。

### 安装后检查

- 确认 `requirements.txt` 中的依赖已正确安装。
- 在 WebUI 插件管理中确认插件状态为"已启用"且无报错。
- 在插件配置中填入阿里云百炼 API Key。
- 进入插件 WebUI 页面（点击插件卡片 → 打开 Pages → settings）完成设置。

## 配置说明

本插件采用双层配置体系：

- **AstrBot 原生配置**（`_conf_schema.json`）：API Key + 翻译设置（`translation_model`、`translation_enabled`、`language_hint`、`system_prompt`），在插件管理面板中填写。其中 `translation_model` 标记 `_special: "select_provider"`，可被 model_manager 自动发现并统一管理。
- **WebUI 设置**（`settings.json`）：所有其他参数，在插件 Pages ��面中配置。

### AstrBot 原生配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `api_key` | string | 空 | 阿里云百炼 API Key，在百炼控制台��取 |
| `translation_model` | text | 空 | 翻译模型 ID，标记 `_special: "select_provider"` 供 model_manager 选择 |
| `translation_enabled` | bool | false | 是否启用翻译 |
| `language_hint` | string | zh | 目标语言，下拉框选项（zh/en/ja/ko/...） |
| `system_prompt` | string | 见默认值 | 翻译系统提示词，支持 `{target_lang}` 占位符 |

### WebUI 设置

所有配置均在 WebUI 页面中完成（插件卡片 → Pages → settings）。

#### 基础设置

- **音色模式**：系统音色 / 自定义音色
- **模型**：根据模式自动筛选可用模型
- **音色**：根据模型+模式自动筛选音色池

#### 音色管理（复刻/设计模式）

- 点击"同步音色"从百炼 API 拉取账号下所有自定义音色
- 音色按模型池分组，切换模型时自动筛选
- 支持为每个音色添加备注
- 支持删除本地记录或同时删除远程音色

#### 合成参数

- 音量 [0, 100]、语速 [0.5, 2.0]、音高 [0.5, 2.0]
- 目标语言（中/英/日/韩/法/德/俄/葡/泰/印尼/越）
- 指令 instruction（根据模型和音色类型动态启用/禁用）
- Seed 随机种子、Markdown 过滤

#### 触发控制

- 群聊/私聊独立开关、白名单（UMO 格式）、触发概率
- 同时发送原文开关

#### 翻译设置

- 翻译开关 + 翻译模型 + 系统提示词

## 使用示例

本插件无用户命令，采用事件驱动方式自动工作。

**触发方式**：当 LLM 生成回复后，插件自动拦截回复文本（通过 `on_llm_response` 钩子），将其合成为语音消息发送。

**使用流程**：
1. 在插件配置中填入百炼 API Key
2. 进入 WebUI 页面选择模式、模型、音色，点击保存
3. 正常与 LLM 对话，回复会自动转为语音发送

## 依赖要求

- Python >= 3.10
- AstrBot >= 4.26.0
- dashscope >= 1.14.0
- httpx >= 0.24.0

## 支持平台

仅支持 **aiocqhttp**（OneBot QQ）。

原因：语音消息（`Record`）当前仅在 aiocqhttp 平台上验证通过。

## 数据存储与隐私

- **设置文件**：`data/plugin_data/astrbot_plugin_cosyecho/settings.json`，存储 WebUI 配置
- **音色数据**：`data/plugin_data/astrbot_plugin_cosyecho/voices_data.json`，存储同步的自定义音色列表
- **外部 API**：语音合成调用阿里云百炼 API（dashscope），合成文本会发送至百炼服务
- **临时音频**：合成产生的临时音频文件在消息发送后自动清理

## 注意事项

1. **工作原理**：通过拦截 LLM 回复（`on_llm_response`），将文本合成为语音后替换原消息发送。
2. **插件冲突**：如果其他插件在 `on_decorating_result` 阶段重写了消息链，可能会覆盖语音消息。
3. **平台支持**：语音消息（`Record`）当前仅在 aiocqhttp（OneBot QQ）上验证通过。
4. **文本限制**：合成文本默认最大 1000 字符（可在 WebUI 自定义，0 表示不限制）；超出上限时跳过语音、仅发送原文（不受"同时发送原文"开关影响）。
5. **指令限制**：instruction 最大 100 字符（汉字按 2 计），超出自动截断。
6. **音色绑定**：复刻/设计音色创建时绑定模型，不能跨模型使用。
7. **音频清理**：临时音频文件在消息发送后自动清理，内置安全阀防止泄漏。

## 许可证

本项目基于 [AGPL-3.0](LICENSE) 许可证开源。

## 作者

**NoFizz** · [GitHub](https://github.com/NoFizz)

如遇问题或有功能建议，欢迎提交 [Issue](https://github.com/NoFizz/astrbot_plugin_cosyecho/issues)。
