const bridge = window.AstrBotPluginPage;

let modelsData = null;
let currentSettings = {};
let modePresets = {};          // 各模式独立设置缓存 {mode: {model, voice, instruction}}
let prevMode = null;           // 上一次的模式
let restoreVoice = null;       // 待恢复的音色选择
let groupWhitelist = [];       // 群聊白名单 UMO 数组
let privateWhitelist = [];     // 私聊白名单 UMO 数组

// ========== 初始化 ==========
const context = await bridge.ready();
document.title = bridge.t("pages.settings.title", "CosyEcho 设置");

await loadModels();
await Promise.all([loadSettings(), loadPluginInfo(), loadProviders()]);
bridge.onContext(() => {
  document.title = bridge.t("pages.settings.title", "CosyEcho 设置");
});

// ========== 数据加载 ==========
async function loadModels() {
  modelsData = await bridge.apiGet("models");
  populateLanguages();
}

async function loadPluginInfo() {
  try {
    const info = await bridge.apiGet("info");
    const el = document.getElementById("plugin-version");
    if (el && info.version) el.textContent = `v${info.version}`;
  } catch (e) { /* ignore */ }
}

async function loadProviders() {
  try {
    const data = await bridge.apiGet("providers");
    const sel = document.getElementById("translation_model");
    sel.innerHTML = '<option value="">自动（使用当前会话模型）</option>';
    for (const p of data.providers) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name !== p.id ? `${p.name} (${p.id})` : p.id;
      sel.appendChild(opt);
    }
    if (currentSettings.translation_model) {
      sel.value = currentSettings.translation_model;
    }
  } catch (e) { /* ignore */ }
}

async function loadSettings() {
  currentSettings = await bridge.apiGet("settings");
  // 迁移旧模式值：cloned / designed → custom
  if (currentSettings.mode === "cloned" || currentSettings.mode === "designed") {
    currentSettings.mode = "custom";
  }
  const presets = currentSettings.mode_presets || {};
  if (presets.cloned || presets.designed) {
    presets.custom = presets.custom || presets.cloned || presets.designed;
    delete presets.cloned;
    delete presets.designed;
  }
  modePresets = presets;
  applySettingsToUI(currentSettings);
  prevMode = getMode();
  restoreVoice = currentSettings.voice;
  onModeChange(true);
}

function populateLanguages() {
  const sel = document.getElementById("language_hint");
  sel.innerHTML = "";
  for (const lang of modelsData.languages) {
    const opt = document.createElement("option");
    opt.value = lang.code;
    opt.textContent = `${lang.name} (${lang.code})`;
    sel.appendChild(opt);
  }
}

// ========== UI 绑定 ==========
function applySettingsToUI(s) {
  const radio = document.querySelector(`input[name="mode"][value="${s.mode}"]`);
  if (radio) radio.checked = true;

  setVal("volume", s.volume);
  setVal("rate", s.rate);
  setVal("pitch", s.pitch);
  setVal("language_hint", s.language_hint);
  setVal("seed", s.seed);
  setVal("instruction", s.instruction);
  document.getElementById("enable_markdown_filter").checked = !!s.enable_markdown_filter;

  document.getElementById("group_voice_enabled").checked = s.group_voice_enabled !== false;
  document.getElementById("private_voice_enabled").checked = s.private_voice_enabled !== false;
  setVal("group_trigger_probability", s.group_trigger_probability);
  setVal("private_trigger_probability", s.private_trigger_probability);
  document.getElementById("send_text_with_voice").checked = !!s.send_text_with_voice;

  // 白名单标签
  groupWhitelist = Array.isArray(s.group_whitelist) ? [...s.group_whitelist] : [];
  privateWhitelist = Array.isArray(s.private_whitelist) ? [...s.private_whitelist] : [];
  renderUmoTags("group");
  renderUmoTags("private");

  document.getElementById("translation_enabled").checked = !!s.translation_enabled;
  setVal("translation_model", s.translation_model);
  setVal("system_prompt", s.system_prompt);

  updateSliderDisplays();
}

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el && val !== undefined && val !== null) el.value = val;
}

function updateSliderDisplays() {
  document.getElementById("volume-val").textContent = document.getElementById("volume").value;
  document.getElementById("rate-val").textContent = parseFloat(document.getElementById("rate").value).toFixed(1);
  document.getElementById("pitch-val").textContent = parseFloat(document.getElementById("pitch").value).toFixed(1);
  document.getElementById("group-prob-val").textContent = parseFloat(document.getElementById("group_trigger_probability").value).toFixed(2);
  document.getElementById("private-prob-val").textContent = parseFloat(document.getElementById("private_trigger_probability").value).toFixed(2);
}

// ========== 模式/模型/音色联动（含各模式设置记忆） ==========
function getMode() {
  const checked = document.querySelector('input[name="mode"]:checked');
  return checked ? checked.value : "system";
}

function onModeChange(isInit = false) {
  const newMode = getMode();

  // 切换前：保存上一个模式的设置
  if (!isInit && prevMode && prevMode !== newMode) {
    modePresets[prevMode] = {
      model: document.getElementById("model").value,
      voice: document.getElementById("voice").value,
      instruction: document.getElementById("instruction").value,
    };
  }

  const models = modelsData.models_by_mode[newMode] || [];
  const modelSel = document.getElementById("model");
  modelSel.innerHTML = "";
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelSel.appendChild(opt);
  }

  // 恢复目标模式记忆的模型与指令
  const preset = modePresets[newMode];
  let targetModel = null;
  if (preset && models.includes(preset.model)) targetModel = preset.model;
  else if (models.includes(currentSettings.model)) targetModel = currentSettings.model;
  if (targetModel) modelSel.value = targetModel;

  if (preset && preset.instruction !== undefined) {
    document.getElementById("instruction").value = preset.instruction;
  }

  // 待恢复的音色
  restoreVoice = (preset && preset.voice) ? preset.voice : currentSettings.voice;

  prevMode = newMode;
  onModelChange();

  document.getElementById("voice-mgmt").style.display = newMode === "system" ? "none" : "block";
}

async function onModelChange() {
  const mode = getMode();
  const model = document.getElementById("model").value;
  updateInstructionUI(model, mode);
  updateMarkdownFilterUI(model, mode);
  await loadVoices();
}

async function loadVoices() {
  const mode = getMode();
  const model = document.getElementById("model").value;
  const voiceSel = document.getElementById("voice");
  voiceSel.innerHTML = "";

  try {
    const data = await bridge.apiGet("voices", { model, mode });
    if (mode === "system") {
      for (const v of data.system_voices) {
        const opt = document.createElement("option");
        opt.value = v.voice;
        opt.textContent = `${v.name} (${v.voice}) - ${v.trait}`;
        voiceSel.appendChild(opt);
      }
    } else {
      for (const v of data.custom_voices) {
        const opt = document.createElement("option");
        opt.value = v.voice_id;
        // 备注显示在音色 ID 左侧
        opt.textContent = v.note ? `${v.note}｜${v.voice_id}` : v.voice_id;
        voiceSel.appendChild(opt);
      }
      if (data.custom_voices.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "暂无音色，请先同步";
        voiceSel.appendChild(opt);
      }
      const syncEl = document.getElementById("sync-time");
      syncEl.textContent = data.last_sync_at ? `上次同步: ${new Date(data.last_sync_at).toLocaleString()}` : "";
      renderVoiceTable(data.custom_voices);
    }
    // 恢复音色选择
    const target = restoreVoice || currentSettings.voice;
    if (target) {
      const exists = [...voiceSel.options].some(o => o.value === target);
      if (exists) voiceSel.value = target;
    }
  } catch (e) {
    console.error("加载音色失败:", e);
  }
}

function updateInstructionUI(model, mode) {
  const group = document.getElementById("instruction-group");
  const textarea = document.getElementById("instruction");
  const hint = document.getElementById("instruction-hint");
  const cap = modelsData.capabilities[model];
  if (!cap) { group.style.display = "none"; return; }

  const voiceType = mode === "system" ? "system" : "custom";
  let support = "none";
  if (voiceType === "system") {
    support = cap.instruction_system === "fixed" ? "fixed" : "none";
  } else {
    support = cap.instruction_custom ? "free" : "none";
  }

  if (support === "none") {
    group.style.display = "none";
  } else {
    group.style.display = "block";
    textarea.disabled = false;
    hint.textContent = support === "fixed"
      ? "此模型系统音色需使用固定格式指令，参见官方文档"
      : "支持任意自然语言指令，最多 100 字符（汉字按 2 计）";
  }
}

function updateMarkdownFilterUI(model, mode) {
  document.getElementById("markdown-filter-group").style.display =
    (model === "cosyvoice-v3-flash" && mode !== "system") ? "block" : "none";
}

// ========== HTML 转义（防 XSS） ==========
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ========== 音色管理表格（备注 + 保存按钮） ==========
function renderVoiceTable(voices) {
  const tbody = document.getElementById("voice-list");
  tbody.innerHTML = "";
  for (const v of voices) {
    const tr = document.createElement("tr");
    const shortId = v.voice_id.length > 30 ? v.voice_id.slice(0, 30) + "..." : v.voice_id;
    tr.innerHTML = `
      <td title="${escapeHtml(v.voice_id)}">${escapeHtml(shortId)}</td>
      <td>${escapeHtml(v.model)}</td>
      <td><input type="text" value="${escapeHtml(v.note || "")}" data-vid="${escapeHtml(v.voice_id)}" class="note-input" /></td>
      <td><button class="btn btn-primary btn-sm save-note" data-vid="${escapeHtml(v.voice_id)}" disabled>保存</button></td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll(".note-input").forEach(input => {
    const original = input.value;
    const row = input.closest("tr");
    const saveBtn = row.querySelector(".save-note");
    // 修改后才点亮保存按钮
    input.addEventListener("input", () => {
      saveBtn.disabled = input.value === original;
    });
    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = "保存中";
      try {
        await bridge.apiPost("voices/note", { voice_id: input.dataset.vid, note: input.value });
        saveBtn.textContent = "已保存";
        // 刷新音色下拉框中的备注显示
        await refreshVoiceSelectOnly();
        setTimeout(() => { saveBtn.textContent = "保存"; }, 1200);
      } catch (e) {
        saveBtn.textContent = "失败";
        setTimeout(() => { saveBtn.textContent = "保存"; saveBtn.disabled = false; }, 1200);
      }
    });
  });
}

// 仅刷新音色下拉框（不重绘表格，避免丢失正在编辑的备注）
async function refreshVoiceSelectOnly() {
  const mode = getMode();
  if (mode === "system") return;
  const model = document.getElementById("model").value;
  const voiceSel = document.getElementById("voice");
  const current = voiceSel.value;
  try {
    const data = await bridge.apiGet("voices", { model, mode });
    voiceSel.innerHTML = "";
    for (const v of data.custom_voices) {
      const opt = document.createElement("option");
      opt.value = v.voice_id;
      opt.textContent = v.note ? `${v.note}｜${v.voice_id}` : v.voice_id;
      voiceSel.appendChild(opt);
    }
    if (current) voiceSel.value = current;
  } catch (e) { /* ignore */ }
}

// ========== 白名单 UMO 标签 ==========
function renderUmoTags(kind) {
  const container = document.getElementById(`${kind}_umo_tags`);
  const list = kind === "group" ? groupWhitelist : privateWhitelist;
  container.innerHTML = "";
  list.forEach((umo, idx) => {
    const tag = document.createElement("span");
    tag.className = "umo-tag";
    tag.innerHTML = `<span class="umo-text" title="${escapeHtml(umo)}">${escapeHtml(umo)}</span><button type="button" class="umo-remove" data-idx="${idx}">&times;</button>`;
    container.appendChild(tag);
  });
  container.querySelectorAll(".umo-remove").forEach(btn => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.dataset.idx);
      if (kind === "group") groupWhitelist.splice(i, 1);
      else privateWhitelist.splice(i, 1);
      renderUmoTags(kind);
    });
  });
}

function bindUmoAdd(kind) {
  const input = document.getElementById(`${kind}_umo_input`);
  const btn = document.getElementById(`${kind}_umo_add`);
  const add = () => {
    const val = input.value.trim();
    if (!val) return;
    const list = kind === "group" ? groupWhitelist : privateWhitelist;
    if (!list.includes(val)) {
      list.push(val);
      renderUmoTags(kind);
    }
    input.value = "";
    input.focus();
  };
  btn.addEventListener("click", add);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
}
bindUmoAdd("group");
bindUmoAdd("private");

// ========== 系统提示词随目标语言联动 ==========
function langNameFromCode(code) {
  const lang = (modelsData?.languages || []).find(l => l.code === code);
  return lang ? lang.name : code;
}
document.getElementById("language_hint").addEventListener("change", () => {
  const code = document.getElementById("language_hint").value;
  document.getElementById("system_prompt").value = `把下面的文本翻译成${langNameFromCode(code)}，不要额外解释`;
});

// ========== 保存 ==========
function collectSettings() {
  const mode = getMode();
  // 保存当前模式的设置到预设
  modePresets[mode] = {
    model: document.getElementById("model").value,
    voice: document.getElementById("voice").value,
    instruction: document.getElementById("instruction").value,
  };
  return {
    mode,
    model: document.getElementById("model").value,
    voice: document.getElementById("voice").value,
    volume: parseInt(document.getElementById("volume").value),
    rate: parseFloat(document.getElementById("rate").value),
    pitch: parseFloat(document.getElementById("pitch").value),
    language_hint: document.getElementById("language_hint").value,
    seed: parseInt(document.getElementById("seed").value) || 0,
    instruction: document.getElementById("instruction").value,
    enable_markdown_filter: document.getElementById("enable_markdown_filter").checked,
    group_voice_enabled: document.getElementById("group_voice_enabled").checked,
    group_trigger_probability: parseFloat(document.getElementById("group_trigger_probability").value),
    group_whitelist: [...groupWhitelist],
    private_voice_enabled: document.getElementById("private_voice_enabled").checked,
    private_trigger_probability: parseFloat(document.getElementById("private_trigger_probability").value),
    private_whitelist: [...privateWhitelist],
    send_text_with_voice: document.getElementById("send_text_with_voice").checked,
    translation_enabled: document.getElementById("translation_enabled").checked,
    translation_model: document.getElementById("translation_model").value,
    system_prompt: document.getElementById("system_prompt").value,
    mode_presets: modePresets,
  };
}

// ========== 事件绑定 ==========
document.querySelectorAll('input[name="mode"]').forEach(r => r.addEventListener("change", () => onModeChange(false)));
document.getElementById("model").addEventListener("change", onModelChange);

["volume", "rate", "pitch", "group_trigger_probability", "private_trigger_probability"].forEach(id => {
  document.getElementById(id).addEventListener("input", updateSliderDisplays);
});

document.getElementById("btn-save").addEventListener("click", async () => {
  const settings = collectSettings();
  try {
    await bridge.apiPost("settings/save", settings);
    currentSettings = settings;
    document.getElementById("save-status").textContent = "已保存";
    setTimeout(() => { document.getElementById("save-status").textContent = ""; }, 3000);
  } catch (e) {
    document.getElementById("save-status").textContent = "保存失败: " + e.message;
  }
});

document.getElementById("btn-sync").addEventListener("click", async () => {
  const btn = document.getElementById("btn-sync");
  btn.disabled = true;
  btn.textContent = "同步中...";
  try {
    const result = await bridge.apiPost("voices/sync", {});
    await loadVoices();
    alert(`同步完成，共 ${result.synced} 个音色`);
  } catch (e) {
    alert("同步失败: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "同步音色";
  }
});
