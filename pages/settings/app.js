const bridge = window.AstrBotPluginPage;

let modelsData = null;
let currentSettings = {};
let modePresets = {};          // 各模式独立设置缓存 {mode: {model, voice, instruction}}
let prevMode = null;           // 上一次的模式
let restoreVoice = null;       // 待恢复的音色选择
let groupWhitelist = [];       // 群聊白名单 UMO 数组
let privateWhitelist = [];     // 私聊白名单 UMO 数组
// 差异计数基准快照在下方 Dirty State 区声明（baselineSettings）

// ========== Toast 通知 ==========
let toastTimer = null;
function showToast(msg, type) {
  const el = document.getElementById("toast");
  el.innerHTML = "";
  if (type) {
    const icon = document.createElement("span");
    icon.className = "toast-icon";
    icon.textContent = type === "success" ? "\u2713" : "\u2715";
    el.appendChild(icon);
  }
  el.appendChild(document.createTextNode(msg));
  el.className = "toast show" + (type ? " toast-" + type : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast"; }, 3000);
}

// ========== 差异计数（基于上次保存快照） ==========
// baselineSettings 保存「上一次保存时」的完整设置快照。
// 每次交互后对比当前 UI 状态与快照，统计实际发生变化的字段数量，
// 保证「改回原状则计数相应减少」。
let baselineSettings = null;

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function deepEqual(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((v, i) => deepEqual(v, b[i]));
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    return ka.every((k) => deepEqual(a[k], b[k]));
  }
  return false;
}

// 统计 current 与 baseline 之间发生变化的字段数量。
// 关键：model / voice / instruction 是与「当前模式」绑定的局部设置，
// 切换模式时它们会跟着变，因此不能和 baseline 的顶层字段直接比。
// 改为在「各自模式 slot」内比对（current.mode_presets[mode] vs baseline.mode_presets[mode]），
// 这样单纯来回切换模式不会产生虚假计数，改回原模式即归零。
function countChanges(current, baseline) {
  if (!baseline) return 0;
  let n = 0;

  // 1) 当前激活模式本身
  if (current.mode !== baseline.mode) n++;

  // 2) 每个模式的 model/voice/instruction 在自身 slot 内比对
  const curPresets = current.mode_presets || {};
  const basePresets = baseline.mode_presets || {};
  for (const mode of Object.keys(curPresets)) {
    if (!deepEqual(curPresets[mode], basePresets[mode])) n++;
  }
  // baseline 中存在但 current 中已删除的 slot 也视为改动
  for (const mode of Object.keys(basePresets)) {
    if (!(mode in curPresets)) n++;
  }

  // 3) 其余顶层字段（排除会被模式切换牵动的字段与 mode_presets 本身）
  const SKIP = new Set(["mode", "model", "voice", "instruction", "mode_presets"]);
  for (const key of Object.keys(current)) {
    if (SKIP.has(key)) continue;
    if (!deepEqual(current[key], baseline[key])) n++;
  }

  return n;
}

// 对比当前 UI 状态与基准快照，刷新保存按钮与角标
function recompute() {
  const current = collectSettings();
  const count = countChanges(current, baselineSettings);
  updateSaveUI(count);
  return count;
}

function updateSaveUI(count) {
  const btn = document.getElementById("btn-save");
  const badge = document.getElementById("saveBadge");
  const changed = count > 0;
  btn.disabled = !changed;
  if (changed) {
    badge.textContent = count;
    badge.style.display = "inline-flex";
    badge.classList.remove("pulse");
    void badge.offsetWidth; // 触发重排以重启动画
    badge.classList.add("pulse");
  } else {
    badge.style.display = "none";
  }
}

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
  syncSystemPromptLang();
  prevMode = getMode();
  restoreVoice = currentSettings.voice;
  await onModeChange(true);  // 等待音色异步加载完成后再建立基准，避免空值产生虚假计数
  // 以「加载完成的设置」作为差异计数的基准快照
  baselineSettings = deepClone(currentSettings);
  recompute();
}

function populateLanguages() {
  const sel = document.getElementById("language_hint");
  sel.innerHTML = "";
  for (const lang of modelsData.languages) {
    const opt = document.createElement("option");
    opt.value = lang.code;
    opt.textContent = lang.name;
    sel.appendChild(opt);
  }
}

// ========== UI 绑定 ==========
function applySettingsToUI(s) {
  const radio = s.mode || 'system';
  setModeUI(radio);

  setVal("volume", s.volume);
  setVal("rate", s.rate);
  setVal("pitch", s.pitch);
  setVal("language_hint", s.language_hint);
  setVal("seed", s.seed);
  setVal("max_text_chars", s.max_text_chars);
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
  const active = document.querySelector('.seg-btn.active');
  return active ? active.dataset.value : 'system';
}

function setModeUI(mode) {
  const control = document.querySelector('.segmented-control');
  control.dataset.active = mode;
  control.querySelectorAll('.seg-btn').forEach(btn => {
    const isActive = btn.dataset.value === mode;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-checked', isActive);
  });
}

async function onModeChange(isInit = false) {
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
  await onModelChange();  // 等待音色下拉框异步加载完成

  document.getElementById("voice-mgmt").style.display = newMode === "system" ? "none" : "block";
  recompute();  // 音色加载完成后再统计差异，避免空值导致虚假计数
}

async function onModelChange() {
  const mode = getMode();
  const model = document.getElementById("model").value;
  updateInstructionUI(model, mode);
  updateMarkdownFilterUI(model, mode);
  await loadVoices();
  recompute();  // 音色加载完成后重新统计差异
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
      <td><button class="btn btn-primary btn-sm save-note" data-vid="${escapeHtml(v.voice_id)}" disabled><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path transform="translate(0 24) scale(0.025)" d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h447q16 0 30.5 6t25.5 17l114 114q11 11 17 25.5t6 30.5v447q0 33-23.5 56.5T760-120H200Zm560-526L646-760H200v560h560v-446ZM565-275q35-35 35-85t-35-85q-35-35-85-35t-85 35q-35 35-35 85t35 85q35 35 85 35t85-35ZM280-560h280q17 0 28.5-11.5T600-600v-80q0-17-11.5-28.5T560-720H280q-17 0-28.5 11.5T240-680v80q0 17 11.5 28.5T280-560Zm-80-86v446-560 114Z"/></svg><span class="save-note-text">保存</span></button></td>
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
      saveBtn.querySelector('.save-note-text').textContent = "保存中";
      try {
        await bridge.apiPost("voices/note", { voice_id: input.dataset.vid, note: input.value });
        saveBtn.querySelector('.save-note-text').textContent = "已保存";
        // 刷新音色下拉框中的备注显示
        await refreshVoiceSelectOnly();
        setTimeout(() => { saveBtn.querySelector('.save-note-text').textContent = "保存"; }, 1200);
      } catch (e) {
        saveBtn.querySelector('.save-note-text').textContent = "失败";
        setTimeout(() => { saveBtn.querySelector('.save-note-text').textContent = "保存"; saveBtn.disabled = false; }, 1200);
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
      recompute();
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
      recompute();
    }
    input.value = "";
    btn.disabled = true;
    input.focus();
  };
  btn.addEventListener("click", add);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  input.addEventListener("input", () => {
    btn.disabled = input.value.trim() === "";
  });
}
bindUmoAdd("group");
bindUmoAdd("private");

// 目标语言切换时同步更新系统提示词里的语言（保留用户其它自定义内容）。
// 兼容新旧两种措辞（"翻译成X语" / "翻译为 {target_lang}"），支持反复切换而不会叠加。
function langNameFromCode(code) {
  const lang = (modelsData?.languages || []).find(l => l.code === code);
  return lang ? lang.name : code;
}

// 转义正则元字符。语言名来自后端数据，此处仅作防御性处理。
function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function syncSystemPromptLang() {
  const sp = document.getElementById("system_prompt");
  const sel = document.getElementById("language_hint");
  if (!sp || !sel) return;
  const name = langNameFromCode(sel.value);
  const original = sp.value;

  // 情况一：提示词含 {target_lang} 占位符 —— 直接填充，不触碰其余任何字符。
  if (original.includes("{target_lang}")) {
    sp.value = original.replace(/\{target_lang\}/g, name);
    return;
  }

  // 情况二：语言名已被填充过 —— 只替换「翻译成/为」后紧跟的【已知语言名】。
  // 采用白名单精确匹配（而非贪婪吞到分隔符），因此绝不会吞掉语言名之后的
  // 任何自定义内容；若用户写的是白名单外的目标（如「文言文」「用户母语」），
  // 则完全不匹配、原样保留。
  const known = (modelsData?.languages || [])
    .map(l => l && l.name)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)  // 长名优先，避免「葡萄牙语」被更短的同后缀名截断
    .map(escapeRegExp);
  if (!known.length) return;
  const re = new RegExp(`(翻译(?:成|为)\\s*)(?:${known.join("|")})`, "g");
  sp.value = original.replace(re, (m, prefix) => prefix + name);
}

document.getElementById("language_hint").addEventListener("change", () => {
  syncSystemPromptLang();
  recompute();
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
    max_text_chars: parseInt(document.getElementById("max_text_chars").value) || 0,
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
document.querySelectorAll('.seg-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    setModeUI(btn.dataset.value);
    onModeChange(false);  // 内部会在音色加载完成后 recompute
  });
});
document.getElementById("model").addEventListener("change", () => { onModelChange(); });

["volume", "rate", "pitch", "group_trigger_probability", "private_trigger_probability"].forEach(id => {
  document.getElementById(id).addEventListener("input", () => { updateSliderDisplays(); recompute(); });
});

// 拖动条填充色随当前值更新（修复浅色模式轨道底色偏暗：轨道底色改由主题变量驱动）
function updateRangeFill(el) {
  const min = parseFloat(el.min) || 0;
  const max = parseFloat(el.max) || 100;
  const val = parseFloat(el.value);
  const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
  el.style.setProperty("--range-value", pct + "%");
}
document.querySelectorAll('input[type="range"]').forEach(el => {
  updateRangeFill(el);
  el.addEventListener("input", () => updateRangeFill(el));
});

// 其他表单元素变更时重新计算差异计数
document.querySelectorAll("input[type='number'], input[type='text'], input[type='checkbox'], select:not(#model), textarea").forEach(el => {
  el.addEventListener("change", recompute);
});

document.getElementById("btn-save").addEventListener("click", async () => {
  const btn = document.getElementById("btn-save");
  const settings = collectSettings();
  btn.classList.add("loading");
  btn.disabled = true;
  try {
    await bridge.apiPost("settings/save", settings);
    // 以「刚保存的设置」作为新的基准快照
    baselineSettings = deepClone(settings);
    currentSettings = settings;
    showToast("设置已保存", "success");
    recompute(); // 此时计数为 0，按钮恢复灰色禁用
  } catch (e) {
    showToast("保存失败: " + e.message, "error");
    btn.disabled = false; // 失败则允许用户重试
  } finally {
    btn.classList.remove("loading");
  }
});

document.getElementById("btn-sync").addEventListener("click", async () => {
  const btn = document.getElementById("btn-sync");
  btn.disabled = true;
  btn.textContent = "同步中...";
  try {
    const result = await bridge.apiPost("voices/sync", {});
    await loadVoices();
    showToast(`同步完成，共 ${result.synced} 个音色`, "success");
  } catch (e) {
    showToast("同步失败: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "同步音色";
  }
});
