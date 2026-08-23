/* 兰台（lantai）前端逻辑 —— 原生 JS，无框架
 * 业务功能（问答 / 文档管理）为首页；设置图标进入配置功能（密码门禁）。
 */
"use strict";

/* ---------------- 工具 ---------------- */
const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const opts = { headers: {}, ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  let resp;
  try {
    resp = await fetch(path, opts);
  } catch (e) {
    toast("网络错误：无法连接后端服务，请确认服务已启动。", "error");
    throw e;
  }
  let payload = null;
  try { payload = await resp.json(); } catch (e) { /* ignore */ }
  if (!resp.ok || (payload && payload.code !== 0)) {
    const msg = (payload && payload.message) || `请求失败（HTTP ${resp.status}）`;
    const err = new Error(msg);
    err.status = resp.status;
    throw err;
  }
  return payload ? payload.data : null;
}

let toastTimer = null;
function toast(message, type = "info") {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast " + (type === "error" ? "error" : type === "success" ? "success" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), type === "info" ? 2600 : 4200);
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

function fmtSize(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(2) + " MB";
}

const CATEGORY_LABELS = {
  text: "文字文档", office: "Office 文档", pdf_text: "文字 PDF",
  image: "图片", pdf_image: "图片 PDF（OCR）",
  chat: "问答模型", embedding: "Embedding 模型",
};
const AI_KEYS = ["text", "office", "pdf_text", "image", "pdf_image", "chat", "embedding"];
const AI_DESCS = {
  text: "txt / md 等纯文本文件",
  office: "docx 等 Office 文档（提取文字与表格）",
  pdf_text: "带文本层的 PDF",
  image: "图片：视觉模型生成内容描述后入库",
  pdf_image: "扫描件 PDF：逐页 OCR 识别文字",
  chat: "问答生成模型（全局）",
  embedding: "向量化模型（全局，如 bge-m3）",
};
// 槽位 → 供应商能力映射（用于推荐模型与能力提示）
const SLOT_CAP = { text: "chat", office: "chat", pdf_text: "chat", image: "vision", pdf_image: "vision", chat: "chat", embedding: "embedding" };
const CAP_LABELS = { chat: "问答/文字处理", vision: "图片理解/OCR", embedding: "向量化" };
let vendorsCache = [];

function normUrl(u) {
  return String(u || "").trim().replace(/\/+$/, "");
}

async function loadVendors() {
  try {
    vendorsCache = await api("/api/settings/vendors");
  } catch (e) {
    vendorsCache = [];
  }
}

/* ---------------- Tab 切换 ---------------- */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    $("#view-" + btn.dataset.view).classList.add("active");
  });
});

/* ---------------- 文档管理 ---------------- */
const fileInput = $("#file-input");
$("#btn-upload").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
  const files = Array.from(fileInput.files || []);
  if (!files.length) return;
  const failed = [];
  for (const f of files) {
    if (f.size > 20 * 1024 * 1024) { failed.push(`${f.name}：超过 20MB 限制`); continue; }
    const fd = new FormData();
    fd.append("file", f);
    try {
      await api("/api/docs/upload", { method: "POST", body: fd });
    } catch (e) {
      failed.push(`${f.name}：${e.message}`);
    }
  }
  fileInput.value = "";
  if (failed.length) toast("部分文件上传失败：\n" + failed.join("\n"), "error");
  else toast("上传成功，正在解析…", "success");
  await loadDocs();
  startPolling();
});

let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const docs = await api("/api/docs").catch(() => null);
    if (!docs) return;
    renderDocs(docs);
    if (!docs.some((d) => d.status === "parsing")) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }, 2000);
}

async function loadDocs() {
  const docs = await api("/api/docs");
  renderDocs(docs);
  if (docs.some((d) => d.status === "parsing")) startPolling();
}

function renderDocs(docs) {
  const tbody = $("#doc-tbody");
  if (!docs.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="7">暂无文档，点击右上角「上传文档」开始</td></tr>';
    return;
  }
  tbody.innerHTML = docs.map((d) => {
    const stateCls = d.status === "ready" ? "ready" : d.status === "failed" ? "failed" : "parsing";
    const stateText = d.status === "ready" ? "已就绪" : d.status === "failed" ? "失败" : "解析中…";
    const errorTip = d.error ? ` title="${esc(d.error)}"` : "";
    return `<tr>
      <td>${esc(d.name)}</td>
      <td>${esc(CATEGORY_LABELS[d.category] || d.category)}</td>
      <td>${fmtSize(d.size)}</td>
      <td><span class="state ${stateCls}"${errorTip}>${stateText}</span></td>
      <td>${d.chunk_count}</td>
      <td>${esc(d.created_at)}</td>
      <td>
        <button class="mini-btn" onclick="openPreview(${d.id})">预览</button>
        <button class="mini-btn danger" onclick="deleteDoc(${d.id}, '${esc(d.name).replace(/'/g, "\\'")}')">删除</button>
      </td>
    </tr>`;
  }).join("");
}

async function deleteDoc(id, name) {
  if (!confirm(`确定删除文档「${name}」吗？其全部切片与源文件将一并删除。`)) return;
  try {
    const r = await api(`/api/docs/${id}`, { method: "DELETE" });
    toast(r ? r.message || "已删除" : "已删除", "success");
  } catch (e) {
    toast(e.message, "error");
  }
  loadDocs();
}

/* ---------------- 问答 ---------------- */
$("#btn-ask").addEventListener("click", ask);
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
});

async function ask() {
  const q = $("#chat-input").value.trim();
  if (!q) { toast("请输入问题。", "error"); return; }
  const btn = $("#btn-ask");
  btn.disabled = true;
  $("#chat-status").textContent = "正在检索知识库并生成答案…";
  $("#chat-answer").classList.add("hidden");
  $("#chat-sources").innerHTML = "";
  try {
    const r = await api("/api/chat", { method: "POST", body: { question: q, top_k: 5 } });
    $("#chat-answer").classList.remove("hidden");
    $("#chat-answer").innerHTML = `<div class="answer-label">答案</div><div></div>`;
    $("#chat-answer").lastElementChild.textContent = r.answer;
    renderSources(r.sources || []);
    $("#chat-status").textContent = `检索到 ${(r.sources || []).length} 个相关切片`;
  } catch (e) {
    $("#chat-status").textContent = "";
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function renderSources(sources) {
  const box = $("#chat-sources");
  if (!sources.length) return;
  box.innerHTML = `<div class="sources-title">引用来源（按相似度排序）</div>` +
    sources.map((s) => `<div class="source-card">
      <div class="source-head">
        <span class="source-name">${esc(s.doc_name)}</span>
        <span class="badge score">相似度 ${s.score}</span>
        <span class="badge cat">${esc(CATEGORY_LABELS[s.category] || s.category)}</span>
        <button class="mini-btn" onclick="openPreview(${s.doc_id})">预览源文件</button>
      </div>
      <div class="source-text">${esc(s.chunk_text)}</div>
    </div>`).join("");
}

/* ---------------- 预览 ---------------- */
async function openPreview(docId) {
  $("#preview-overlay").classList.remove("hidden");
  $("#preview-body").innerHTML = '<p class="hint">加载中…</p>';
  try {
    const r = await api(`/api/docs/${docId}/preview`);
    $("#preview-title").textContent = r.doc.name;
    if (r.type === "image") {
      $("#preview-body").innerHTML = `<img src="${r.raw_url}" alt="${esc(r.doc.name)}">`;
    } else {
      let note = "";
      if (r.note) note = `<div class="preview-note">${esc(r.note)}</div>`;
      $("#preview-body").innerHTML = `${note}<pre></pre>`;
      $("#preview-body").querySelector("pre").textContent = r.content || "（无文本内容）";
    }
  } catch (e) {
    $("#preview-body").innerHTML = `<p class="hint">预览失败：${esc(e.message)}</p>`;
  }
}
$("#btn-close-preview").addEventListener("click", () => $("#preview-overlay").classList.add("hidden"));
$("#preview-overlay").addEventListener("click", (e) => {
  if (e.target === $("#preview-overlay")) $("#preview-overlay").classList.add("hidden");
});

/* ---------------- 设置（密码门禁） ---------------- */
const settingsOverlay = $("#settings-overlay");

$("#btn-settings").addEventListener("click", openSettings);
$("#btn-close-settings").addEventListener("click", closeSettings);
settingsOverlay.addEventListener("click", (e) => {
  if (e.target === settingsOverlay) closeSettings();
});

async function openSettings() {
  settingsOverlay.classList.remove("hidden");
  $("#settings-gate").classList.remove("hidden");
  $("#settings-body").classList.add("hidden");
  $("#settings-password-input").value = "";
  await loadVendors();
  // 探测会话是否有效
  try {
    await api("/api/settings/ai");
    showSettingsBody();
  } catch (e) {
    if (e.status !== 401) toast(e.message, "error");
  }
}

function closeSettings() {
  settingsOverlay.classList.add("hidden");
}

function showSettingsBody() {
  $("#settings-gate").classList.add("hidden");
  $("#settings-body").classList.remove("hidden");
  loadAiConfig();
  loadTokens();
  loadAbout();
}

$("#btn-settings-verify").addEventListener("click", async () => {
  const pw = $("#settings-password-input").value;
  if (!pw) { toast("请输入配置密码。", "error"); return; }
  try {
    await api("/api/settings/verify", { method: "POST", body: { password: pw } });
    toast("验证通过。", "success");
    showSettingsBody();
  } catch (e) {
    toast(e.message, "error");
  }
});
$("#settings-password-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#btn-settings-verify").click();
});

document.querySelectorAll(".stab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".stab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".stab-body").forEach((v) => v.classList.remove("active"));
    $("#stab-" + btn.dataset.stab).classList.add("active");
  });
});

/* ---- AI 配置 ---- */
let aiConfigCache = null;

async function loadAiConfig() {
  try {
    aiConfigCache = await api("/api/settings/ai");
    renderAiCards();
  } catch (e) {
    toast(e.message, "error");
    if (e.status === 401) { $("#settings-body").classList.add("hidden"); $("#settings-gate").classList.remove("hidden"); }
  }
}

function renderAiCards() {
  const box = $("#ai-cards");
  box.innerHTML = AI_KEYS.map((key) => {
    const c = aiConfigCache[key] || {};
    const masked = c.api_key || "";
    const placeholder = masked ? `已保存 ${masked}（留空保持不变）` : "API Key（Ollama 可留空）";
    const matched = vendorsCache.find((v) => normUrl(v.base_url) === normUrl(c.base_url)) || null;
    const cap = SLOT_CAP[key];
    const capNote = matched && !matched.capabilities.includes(cap)
      ? `⚠ 该供应商不支持${CAP_LABELS[cap]}，请选择其他供应商（如通义/硅基流动）。`
      : "";
    return `<div class="ai-card" data-key="${key}">
      <div class="ai-card-head">
        <span class="cat">${CATEGORY_LABELS[key]}</span>
        <span class="desc">${AI_DESCS[key]}</span>
        <span class="model-tag">${esc(c.model || "未配置")}</span>
      </div>
      <div class="ai-card-body">
        <div class="cap-note">${esc(capNote)}</div>
        <div class="grid2">
          <div class="form-row">
            <label>供应商（选择后自动填充 URL 与推荐模型）</label>
            <select data-v="vendor">
              <option value="">自定义</option>
              ${vendorsCache.map((v) => `<option value="${esc(v.id)}" ${matched && matched.id === v.id ? "selected" : ""}>${esc(v.name)}</option>`).join("")}
            </select>
            <input type="hidden" data-f="provider" value="${esc(c.provider || "ollama")}">
          </div>
          <div class="form-row">
            <label>Base URL（可手动修改）</label>
            <input data-f="base_url" value="${esc(c.base_url || "")}" placeholder="如 http://127.0.0.1:11434 或 https://api.deepseek.com/v1">
          </div>
          <div class="form-row">
            <label>API Key</label>
            <input data-f="api_key" type="password" placeholder="${esc(placeholder)}" autocomplete="off">
          </div>
          <div class="form-row">
            <label>模型名</label>
            <input data-f="model" value="${esc(c.model || "")}" placeholder="如 qwen2.5:7b / llava:7b / bge-m3">
          </div>
          <div class="form-row full">
            <label>提示词（留空使用默认）</label>
            <input data-f="prompt" value="${esc(c.prompt || "")}">
          </div>
          <div class="form-row">
            <label>温度（0~2）</label>
            <input data-f="temperature" type="number" min="0" max="2" step="0.1" value="${c.temperature ?? 0.2}">
          </div>
          <div class="form-row" style="justify-content:flex-end; flex-direction:row; align-items:flex-end;">
            <button class="mini-btn" onclick="testAi('${key}')">测试连接</button>
          </div>
        </div>
      </div>
    </div>`;
  }).join("");
  box.querySelectorAll(".ai-card-head").forEach((head) => {
    head.addEventListener("click", () => head.parentElement.classList.toggle("open"));
  });
  // 供应商选择：自动填充 provider / base_url / 推荐模型，并提示能力不匹配
  box.querySelectorAll('select[data-v="vendor"]').forEach((sel) => {
    sel.addEventListener("change", () => {
      const card = sel.closest(".ai-card");
      const key = card.dataset.key;
      const v = vendorsCache.find((x) => x.id === sel.value);
      if (!v) return;
      const cap = SLOT_CAP[key];
      card.querySelector('[data-f="provider"]').value = v.provider;
      card.querySelector('[data-f="base_url"]').value = v.base_url;
      const modelInput = card.querySelector('[data-f="model"]');
      const rec = v.models[cap] || v.models.chat;
      if (rec) modelInput.value = rec;
      const note = card.querySelector(".cap-note");
      note.textContent = v.capabilities.includes(cap)
        ? ""
        : `⚠ 该供应商不支持${CAP_LABELS[cap]}，请选择其他供应商（如通义/硅基流动）。`;
    });
  });
}

function collectAiItem(key) {
  const card = document.querySelector(`.ai-card[data-key="${key}"]`);
  const item = { provider: "", base_url: "", api_key: "", model: "", prompt: "", temperature: 0.2 };
  card.querySelectorAll("[data-f]").forEach((el) => {
    if (el.type === "number") {
      const v = parseFloat(el.value);
      item[el.dataset.f] = Number.isFinite(v) ? v : 0.2;
    } else {
      item[el.dataset.f] = el.value.trim();
    }
  });
  return item;
}

async function testAi(key) {
  const item = collectAiItem(key);
  if (!item.api_key && aiConfigCache && aiConfigCache[key] && aiConfigCache[key].api_key) {
    item.api_key = aiConfigCache[key].api_key; // 未填新 Key 时用已保存的（脱敏值，后端自动换存储值）
  }
  try {
    const r = await api("/api/settings/ai/test", { method: "POST", body: { key, config: item } });
    const models = (r && r.models) || [];
    toast(`连接成功：${models.length} 个模型（${models.slice(0, 5).join("、")}${models.length > 5 ? "…" : ""}）`, "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

$("#btn-save-ai").addEventListener("click", async () => {
  const items = {};
  for (const key of AI_KEYS) items[key] = collectAiItem(key);
  try {
    await api("/api/settings/ai", { method: "PUT", body: { items } });
    toast("AI 配置已保存，立即生效。", "success");
    await loadAiConfig();
  } catch (e) {
    toast(e.message, "error");
  }
});

/* ---- API Token ---- */
async function loadTokens() {
  try {
    const tokens = await api("/api/settings/tokens");
    const tbody = $("#token-tbody");
    if (!tokens.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="6">暂无 Token</td></tr>';
      return;
    }
    tbody.innerHTML = tokens.map((t) => `<tr>
      <td>${esc(t.name)}</td>
      <td>${esc(t.prefix)}</td>
      <td>${esc(t.created_at)}</td>
      <td>${esc(t.last_used_at || "—")}</td>
      <td>${t.revoked ? '<span class="state failed">已吊销</span>' : '<span class="state ready">有效</span>'}</td>
      <td>${t.revoked ? "" : `<button class="mini-btn danger" onclick="revokeToken(${t.id})">吊销</button>`}</td>
    </tr>`).join("");
  } catch (e) {
    if (e.status !== 401) toast(e.message, "error");
  }
}

async function revokeToken(id) {
  if (!confirm("确定吊销该 Token 吗？吊销后立即失效。")) return;
  try {
    await api(`/api/settings/tokens/${id}`, { method: "DELETE" });
    toast("Token 已吊销。", "success");
    loadTokens();
  } catch (e) {
    toast(e.message, "error");
  }
}

$("#btn-create-token").addEventListener("click", async () => {
  const name = $("#token-name").value.trim();
  if (!name) { toast("请填写 Token 名称。", "error"); return; }
  try {
    const r = await api("/api/settings/tokens", { method: "POST", body: { name } });
    const box = $("#token-plain");
    box.classList.remove("hidden");
    box.innerHTML = `<div>新 Token（仅展示一次，请立即复制）：</div>
      <div style="word-break:break-all;margin:6px 0">${esc(r.plaintext)}</div>
      <button class="mini-btn" onclick="copyToken()">复制</button>
      <div class="copy-hint">调用方式：Authorization: Bearer ${esc(r.plaintext)}</div>`;
    window._lastPlain = r.plaintext;
    $("#token-name").value = "";
    loadTokens();
  } catch (e) {
    toast(e.message, "error");
  }
});

async function copyToken() {
  try {
    await navigator.clipboard.writeText(window._lastPlain || "");
    toast("已复制。", "success");
  } catch (e) {
    toast("复制失败，请手动选择复制。", "error");
  }
}

/* ---- 修改密码 ---- */
$("#btn-change-pw").addEventListener("click", async () => {
  const oldPw = $("#pw-old").value;
  const newPw = $("#pw-new").value;
  const newPw2 = $("#pw-new2").value;
  if (!oldPw || !newPw) { toast("请填写完整。", "error"); return; }
  if (newPw.length < 8) { toast("新密码至少 8 位。", "error"); return; }
  if (newPw !== newPw2) { toast("两次输入的新密码不一致。", "error"); return; }
  try {
    await api("/api/settings/password", { method: "POST", body: { old_password: oldPw, new_password: newPw } });
    toast("密码已修改，请重新验证后进入配置。", "success");
    $("#pw-old").value = $("#pw-new").value = $("#pw-new2").value = "";
    $("#settings-body").classList.add("hidden");
    $("#settings-gate").classList.remove("hidden");
  } catch (e) {
    toast(e.message, "error");
  }
});

/* ---- 关于 ---- */
async function loadAbout() {
  try {
    const info = await api("/api/settings/system/info");
    $("#about-info").innerHTML = `
      <p><b>兰台（lantai）</b> · 本地 RAG 知识库演示系统</p>
      <p>版本：<b>${esc(info.version)}</b></p>
      <p>平台：${esc(info.platform)}</p>
      <p>数据目录：${esc(info.data_dir)}</p>
      <p class="hint">起名取自汉代皇家档案馆「兰台」——你的文档典藏之所。</p>`;
  } catch (e) {
    if (e.status !== 401) toast(e.message, "error");
  }
}

/* ---------------- 初始化 ---------------- */
loadDocs();
