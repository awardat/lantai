/* 兰台（lantai）前端逻辑 —— 原生 JS，无框架
 * 业务功能（问答 / 文档管理）为首页；设置图标进入配置功能（密码门禁）。
 */
"use strict";

/* ---------------- 工具 ---------------- */
const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const opts = { headers: {}, ...options };
  // 双通道会话（0.1.25，CH-046）：壳内 iframe 跨站上下文 cookie 不可用，
  // 经 X-Lantai-Session 头传递（localStorage 存储）；浏览器直开时 cookie 通道仍可用
  const sess = localStorage.getItem("lantai_session");
  if (sess) opts.headers["X-Lantai-Session"] = sess;
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
  if (resp.status === 401) {
    // 会话失效：清除本地会话，由调用方决定是否回登录框
    localStorage.removeItem("lantai_session");
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

// 属性上下文转义（0.1.34，CH-060）：在 esc 基础上补双/单引号，用于 title/onclick 等属性位
function escAttr(s) {
  return esc(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmtSize(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(2) + " MB";
}

const CATEGORY_LABELS = {
  text: "文字文档", office: "Office 文档", pdf_text: "文字 PDF",
  image: "图片", pdf_image: "图片 PDF（OCR）",
  chat: "问答模型", embedding: "Embedding 模型", rerank: "重排（Rerank）",
};
const AI_KEYS = ["text", "office", "pdf_text", "image", "pdf_image", "chat", "embedding", "rerank"];
const AI_DESCS = {
  text: "txt / md 等纯文本文件",
  office: "docx 等 Office 文档（提取文字与表格）",
  pdf_text: "带文本层的 PDF",
  image: "图片：视觉模型生成内容描述后入库",
  pdf_image: "扫描件 PDF：逐页 OCR 识别文字",
  chat: "问答生成模型（全局）",
  embedding: "向量化模型（全局，如 bge-m3）",
  rerank: "交叉编码器精排（可选；启用后检索结果重排，需 rerank 模型）",
};
// 槽位 → 供应商能力映射（用于推荐模型与能力提示）
const SLOT_CAP = { text: "chat", office: "chat", pdf_text: "chat", image: "vision", pdf_image: "vision", chat: "chat", embedding: "embedding", rerank: "rerank" };
const CAP_LABELS = { chat: "问答/文字处理", vision: "图片理解/OCR", embedding: "向量化", rerank: "重排" };
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

/* ---------------- 左栏导航（问答 / 文件管理 / 设置） ---------------- */
document.querySelectorAll(".side-nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.id === "btn-settings") { openSettings(); return; }
    document.querySelectorAll(".side-nav-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    $("#view-" + btn.dataset.view).classList.add("active");
  });
});

/* ---------------- 文档管理（0.1.18：批量上传浮层 + 解析队列） ---------------- */
const uploadOverlay = $("#upload-overlay");

function openUploadOverlay() {
  uploadOverlay.classList.remove("hidden");
  $("#upload-list").innerHTML = "";
}
$("#btn-close-upload").addEventListener("click", () => uploadOverlay.classList.add("hidden"));
uploadOverlay.addEventListener("click", (e) => {
  if (e.target === uploadOverlay) uploadOverlay.classList.add("hidden");
});
$("#btn-upload").addEventListener("click", openUploadOverlay);
$("#btn-pick-files").addEventListener("click", () => $("#upload-file-input").click());

// 拖拽上传
const dropZone = $("#drop-zone");
["dragenter", "dragover"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => { e.preventDefault(); dropZone.classList.add("dragover"); })
);
["dragleave", "drop"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => { e.preventDefault(); dropZone.classList.remove("dragover"); })
);
dropZone.addEventListener("drop", (e) => {
  const files = Array.from(e.dataTransfer.files || []);
  if (files.length) uploadFiles(files);
});
$("#upload-file-input").addEventListener("change", (e) => {
  const files = Array.from(e.target.files || []);
  e.target.value = "";
  if (files.length) uploadFiles(files);
});

// 上传（前端小并发 3），列表实时显示状态
async function uploadFiles(files) {
  const list = $("#upload-list");
  const rows = files.map((f) => {
    const row = document.createElement("div");
    row.className = "upload-item";
    row.innerHTML = `<span class="up-name">${esc(f.name)}</span><span class="up-size">${fmtSize(f.size)}</span><span class="up-state">等待</span>`;
    list.appendChild(row);
    return { file: f, row, state: row.querySelector(".up-state") };
  });
  const results = { ok: 0, fail: 0 };
  let idx = 0;
  async function worker() {
    while (idx < rows.length) {
      const cur = rows[idx++];
      if (cur.file.size > 20 * 1024 * 1024) {
        cur.state.textContent = "超过 20MB";
        cur.state.className = "up-state err";
        results.fail++;
        continue;
      }
      cur.state.textContent = "上传中…";
      const fd = new FormData();
      fd.append("file", cur.file);
      try {
        await api("/api/docs/upload", { method: "POST", body: fd });
        cur.state.textContent = "已入队";
        cur.state.className = "up-state ok";
        results.ok++;
      } catch (e) {
        cur.state.textContent = "失败";
        cur.state.className = "up-state err";
        cur.row.title = e.message;
        results.fail++;
      }
    }
  }
  await Promise.all([worker(), worker(), worker()]);
  toast(`上传完成：成功 ${results.ok} 个${results.fail ? `，失败 ${results.fail} 个` : ""}，已加入解析队列。`, results.fail ? "error" : "success");
  loadDocs();
  startPolling();
}

let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const docs = await api("/api/docs").catch(() => null);
    if (!docs) return;
    renderDocs(docs);
    // 解析状态仅在「设置 → 解析」Tab 激活且已登录时刷新：
    // 未登录时调用需会话的 /api/settings/parse 会 401 刷日志（0.1.31，CH-056）；
    // Tab 显隐由 .stab-body.active 控制（非 .hidden），0.1.32（CH-058/M2）修正判断
    const parseTabActive = $("#stab-parse").classList.contains("active");
    if (parseTabActive && localStorage.getItem("lantai_session")) {
      refreshParseStatus();
    }
    if (!docs.some((d) => d.status === "parsing" || d.status === "queued")) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }, 2000);
}

async function loadDocs() {
  const docs = await api("/api/docs");
  renderDocs(docs);
  if (docs.some((d) => d.status === "parsing" || d.status === "queued")) startPolling();
}

/* ---- 解析队列设置（0.1.18） ---- */
async function refreshParseStatus() {
  try {
    const s = await api("/api/settings/parse");
    const el = $("#parse-status");
    if (el) el.textContent = `运行中 ${s.parsing} 个 · 排队中 ${s.queued} 个 · 并发上限 ${s.concurrency}`;
    return s;
  } catch (e) {
    return null;
  }
}

$("#parse-concurrency").addEventListener("blur", async () => {
  const input = $("#parse-concurrency");
  const n = parseInt(input.value, 10);
  if (!Number.isFinite(n) || n < 1 || n > 50) {
    toast("并发数需在 1~50 之间。", "error");
    const s = await refreshParseStatus();
    if (s) input.value = s.concurrency;
    return;
  }
  try {
    const s = await api("/api/settings/parse", { method: "PUT", body: { concurrency: n } });
    input.value = s.concurrency;
    const el = $("#parse-status");
    if (el) el.textContent = `运行中 ${s.parsing} 个 · 排队中 ${s.queued} 个 · 并发上限 ${s.concurrency}`;
    toast(`解析并发数已调整为 ${s.concurrency}。`, "success");
  } catch (e) {
    toast(e.message, "error");
  }
});

async function loadParseTab() {
  const s = await refreshParseStatus();
  if (s) $("#parse-concurrency").value = s.concurrency;
}

// 手动指定文件大类重试选项（0.1.37，CH-065）：用于识别问题手工兜底（如扫描件误判
// 文字 PDF 时指定"图片 PDF（OCR）"走 OCR 通道）；具体扩展名指定（0.1.36 CH-063）
// 后端接口仍保留（API 调用兼容），前端统一按大类选择
const RETRY_CATEGORIES = [
  ["text", "文本（txt/md）"],
  ["office", "Office 文档"],
  ["pdf_text", "文字 PDF"],
  ["pdf_image", "图片 PDF（OCR）"],
  ["image", "图片"],
];
const retryCatOptions = '<option value="">按原类型</option>' + RETRY_CATEGORIES.map(([v, label]) => `<option value="${v}">${label}</option>`).join("");

// 文件计数 + 分类筛选联动（0.1.37，用户提出）：筛选按钮实时显示各状态文件数
const FILTER_LABELS = { "": "全部", ready: "已就绪", queued: "排队中", parsing: "解析中", failed: "失败" };

function updateDocCounts(docs) {
  const counts = { "": docs.length, ready: 0, queued: 0, parsing: 0, failed: 0 };
  for (const d of docs) if (counts[d.status] !== undefined) counts[d.status]++;
  document.querySelectorAll("#doc-filter .filter-btn").forEach((btn) => {
    const st = btn.dataset.status || "";
    btn.textContent = `${FILTER_LABELS[st] || st} (${counts[st]})`;
  });
}

function renderDocs(docs) {
  const tbody = $("#doc-tbody");
  // 文件计数（0.1.37）：全量统计后渲染到筛选按钮（计数与筛选联动，轮询期间实时更新）
  updateDocCounts(docs);
  // 状态筛选（0.1.34，CH-060）：按当前筛选状态过滤后渲染
  const filtered = docFilter ? docs.filter((d) => d.status === docFilter) : docs;
  if (!filtered.length) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="7">${docs.length ? "没有符合当前筛选条件的文档" : "暂无文档，点击右上角「上传文档」开始"}</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map((d) => {
    const stateMap = { ready: ["ready", "已就绪"], failed: ["failed", "失败"], queued: ["queued", "排队中"], parsing: ["parsing", "解析中…"] };
    const [stateCls, stateText] = stateMap[d.status] || ["parsing", d.status];
    // 失败原因悬停提示：escAttr 转义引号，避免 error 含 " 破坏 title 属性（CH-060/M1）
    const errorTip = d.error ? ` title="${escAttr(d.error)}"` : "";
    // 失败行：大类下拉（指定后重试按该大类解析，识别问题手工兜底）+ 重试按钮（0.1.34/0.1.37）
    const retryBox = d.status === "failed" ? `<select class="retry-type" data-id="${d.id}" title="文件被识别错时手动指定真实大类后点「重试」（如扫描件指定「图片 PDF（OCR）」）">${retryCatOptions}</select>
        <button class="mini-btn" onclick="retryDoc(${d.id})">重试</button>` : "";
    // 0.1.45（CH-089/A）：已就绪文档可「重新解析」（版本升级后按当前方法重造切片，如表格 NL）
    const reparseBtn = d.status === "ready" ? `<button class="mini-btn" onclick="reparseDoc(${d.id}, '${esc(d.name).replace(/'/g, "\\'")}')" title="按当前解析方法重新解析（升级版本后可重新生成切片）">重新解析</button>` : "";
    return `<tr>
      <td>${esc(d.name)}</td>
      <td>${esc(CATEGORY_LABELS[d.category] || d.category)}</td>
      <td>${fmtSize(d.size)}</td>
      <td><span class="state ${stateCls}"${errorTip}>${stateText}</span></td>
      <td>${d.chunk_count}</td>
      <td>${esc(d.created_at)}</td>
      <td>
        <button class="mini-btn" onclick="openPreview(${d.id})">预览</button>
        ${retryBox}
        ${reparseBtn}
        <button class="mini-btn danger" onclick="deleteDoc(${d.id}, '${esc(d.name).replace(/'/g, "\\'")}')">删除</button>
      </td>
    </tr>`;
  }).join("");
}

// 失败文档重新提交解析（0.1.34，CH-060；0.1.36 支持 ext；0.1.37 支持 category 大类）
async function retryDoc(id) {
  const sel = document.querySelector(`.retry-type[data-id="${id}"]`);
  const body = {};
  if (sel && sel.value) body.category = sel.value;
  try {
    const r = await api(`/api/docs/${id}/retry`, { method: "POST", body });
    toast(r && r.message ? r.message : "已重新提交解析。", "success");
  } catch (e) {
    toast(e.message, "error");
  }
  loadDocs();
}

// 0.1.45（CH-089/A）：已就绪文档重新解析（版本升级后按当前方法重造切片）
async function reparseDoc(id, name) {
  if (!confirm(`按当前解析方法重新解析「${name}」？\n将清除该文档现有切片并重新入库，同内容不会重复保留。`)) return;
  try {
    const r = await api(`/api/docs/${id}/reparse`, { method: "POST" });
    toast(r && r.message ? r.message : "已提交重新解析。", "success");
  } catch (e) {
    toast(e.message, "error");
  }
  loadDocs();
}

// 状态筛选按钮（全部/已就绪/排队中/解析中/失败）
let docFilter = "";
document.querySelectorAll("#doc-filter .filter-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#doc-filter .filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    docFilter = btn.dataset.status || "";
    loadDocs();
  });
});

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

/* ---------------- 对话历史（0.1.5 / 0.1.8 左栏会话列表） ---------------- */
let currentConvId = null;    // null = 未关联会话（提问时自动创建）
let convJustCreated = false; // 本次提问是否新建会话（用于首轮自动命名标题）

function clearMessages() {
  const box = $("#chat-messages");
  box.innerHTML = '<div class="chat-empty">开始提问吧 —— 例如：什么是兰台？</div>';
}

function appendMsg(role, content, isStreamAnswer) {
  const box = $("#chat-messages");
  const empty = box.querySelector(".chat-empty");
  if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = "msg " + (role === "user" ? "user" : "assistant");
  el.innerHTML = `<div class="msg-label">${role === "user" ? "我" : "兰台"}</div><div class="msg-body"></div>`;
  const body = el.querySelector(".msg-body");
  if (isStreamAnswer) {
    body.innerHTML = `<div class="answer-text"></div><div class="src-line"></div>`;
    body.firstElementChild.textContent = content;
  } else {
    body.textContent = content;
  }
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}

async function renderConvList() {
  const convs = await api("/api/conversations");
  const list = $("#conv-list");
  if (!convs.length) {
    list.innerHTML = '<div class="conv-empty">暂无会话，点击 ＋ 新建</div>';
    return;
  }
  list.innerHTML = convs.map((c) => {
    const title = c.title || ("对话 #" + c.id);
    return `<div class="conv-item ${currentConvId === c.id ? "active" : ""}" data-id="${c.id}" title="${esc(title)}">
      <span class="conv-title">${esc(title)}</span>
      <span class="conv-actions">
        <button class="icon-mini" data-act="rename" title="重命名">✎</button>
        <button class="icon-mini" data-act="del" title="删除">🗑</button>
      </span>
    </div>`;
  }).join("");
  if (currentConvId !== null && !convs.some((c) => c.id === currentConvId)) {
    currentConvId = null;
    clearMessages();
  }
}

$("#conv-list").addEventListener("click", async (e) => {
  const item = e.target.closest(".conv-item");
  if (!item) return;
  const id = parseInt(item.dataset.id, 10);
  const actBtn = e.target.closest("[data-act]");
  if (actBtn) {
    e.stopPropagation();
    if (actBtn.dataset.act === "rename") {
      const old = item.querySelector(".conv-title").textContent;
      const title = prompt("输入新的对话名称：", old);
      if (!title || !title.trim()) return;
      try {
        await api(`/api/conversations/${id}`, { method: "PUT", body: { title: title.trim() } });
        toast("对话已重命名。", "success");
        await renderConvList();
      } catch (err) { toast(err.message, "error"); }
    } else if (actBtn.dataset.act === "del") {
      if (!confirm("确定删除该对话及其全部消息吗？")) return;
      try {
        await api(`/api/conversations/${id}`, { method: "DELETE" });
        if (currentConvId === id) { currentConvId = null; clearMessages(); }
        toast("对话已删除。", "success");
        await renderConvList();
      } catch (err) { toast(err.message, "error"); }
    }
    return;
  }
  // 切换会话：加载历史消息
  currentConvId = id;
  clearMessages();
  await renderConvList();
  try {
    const msgs = await api(`/api/conversations/${id}/messages`);
    for (const m of msgs) appendMsg(m.role, m.content, false);
  } catch (err) { toast(err.message, "error"); }
  $("#chat-input").focus();
});

$("#btn-new-conv").addEventListener("click", async () => {
  try {
    const r = await api("/api/conversations", { method: "POST", body: { title: "新对话" } });
    currentConvId = r.id;
    clearMessages();
    await renderConvList();
    $("#chat-input").focus();
  } catch (e) { toast(e.message, "error"); }
});

async function ensureConversation() {
  if (currentConvId !== null) return;
  const r = await api("/api/conversations", { method: "POST", body: { title: "新对话" } });
  currentConvId = r.id;
  convJustCreated = true;
  await renderConvList();
}

/* ---------------- 问答（SSE 流式，0.1.8：消息流 + 来源小字内嵌） ---------------- */
$("#btn-ask").addEventListener("click", ask);
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
});

function renderSourcesInline(el, sources) {
  if (!sources.length) { el.textContent = ""; return; }
  el.innerHTML = sources.map((s) =>
    `<div class="src-item">来源：<b>${esc(s.doc_name)}</b> · 相似度 ${s.score} · <a href="javascript:void(0)" onclick="openPreview(${s.doc_id})">预览</a></div>`
  ).join("");
}

async function ask() {
  const q = $("#chat-input").value.trim();
  if (!q) { toast("请输入问题。", "error"); return; }
  const btn = $("#btn-ask");
  btn.disabled = true;

  appendMsg("user", q, false);          // 用户气泡
  $("#chat-input").value = "";           // 提问后清空输入框
  const assistantEl = appendMsg("assistant", "", true);
  const answerEl = assistantEl.querySelector(".answer-text");
  const srcLineEl = assistantEl.querySelector(".src-line");

  try {
    await ensureConversation(); // 未关联会话时自动创建
    const resp = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, top_k: 8, conversation_id: currentConvId }),
    });
    if (!resp.ok || !resp.body) {
      let msg = `请求失败（HTTP ${resp.status}）`;
      try { const p = await resp.json(); if (p && p.message) msg = p.message; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buf = "";
    let answer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(t.slice(5).trim()); } catch (e) { continue; }
        if (ev.type === "sources") {
          renderSourcesInline(srcLineEl, ev.sources || []);
        } else if (ev.type === "delta") {
          answer += ev.content;
          answerEl.textContent = answer;
        } else if (ev.type === "error") {
          toast(ev.message, "error");
        }
      }
    }
    // 首轮问答自动生成会话标题（用第一轮问题，超长截断）
    if (convJustCreated && answer.trim()) {
      const title = q.length > 20 ? q.slice(0, 20) + "…" : q;
      await api(`/api/conversations/${currentConvId}`, { method: "PUT", body: { title } });
      convJustCreated = false;
      await renderConvList();
    }
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/* ---------------- 预览 ---------------- */
async function openPreview(docId) {
  $("#preview-overlay").classList.remove("hidden");
  $("#preview-body").innerHTML = '<p class="hint">加载中…</p>';
  try {
    const r = await api(`/api/docs/${docId}/preview`);
    $("#preview-title").textContent = r.doc.name;
    if (r.type === "pdf") {
      // 0.1.9：PDF 用浏览器原生查看器渲染源文件（支持缩放/翻页/搜索）
      let note = "";
      if (r.note) note = `<div class="preview-note">${esc(r.note)}</div>`;
      $("#preview-body").innerHTML = `${note}<iframe class="pdf-frame" src="${r.raw_url}" title="${esc(r.doc.name)}"></iframe>`;
    } else if (r.type === "image") {
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

$("#btn-close-settings").addEventListener("click", closeSettings);
settingsOverlay.addEventListener("click", (e) => {
  if (e.target === settingsOverlay) closeSettings();
});

async function openSettings() {
  settingsOverlay.classList.remove("hidden");
  $("#settings-panel").classList.add("panel-gate"); // 密码门禁：小窗口自适应
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
  $("#settings-panel").classList.remove("panel-gate"); // 进入配置：切换为大窗口
  $("#settings-gate").classList.add("hidden");
  $("#settings-body").classList.remove("hidden");
  loadAiConfig();
  loadParseTab();
  loadTokens();
  loadAbout();
}

$("#btn-settings-verify").addEventListener("click", async () => {
  const pw = $("#settings-password-input").value;
  if (!pw) { toast("请输入配置密码。", "error"); return; }
  try {
    const data = await api("/api/settings/verify", { method: "POST", body: { password: pw } });
    // 双通道会话：保存会话 token（壳内 iframe 场景 cookie 不可用，改走请求头）
    if (data && data.session) localStorage.setItem("lantai_session", data.session);
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
    const capNote = cap !== "rerank" && matched && !matched.capabilities.includes(cap)
      ? `⚠ 该供应商不支持${CAP_LABELS[cap]}，请选择其他供应商（如通义/硅基流动）。`
      : "";
    // 0.1.39（R106）：rerank 组启用开关
    const toggleRow = key === "rerank"
      ? `<div class="form-row full">
          <label class="toggle-label"><input type="checkbox" data-f="enabled" ${c.enabled ? "checked" : ""}> 启用重排（开启后每次问答对候选做交叉编码器精排）</label>
        </div>`
      : "";
    // 0.1.46（CH-090）：pdf_image 卡「本地 OCR」开关（Tesseract 离线识别，替代视觉模型）
    const localOcrRow = key === "pdf_image"
      ? `<div class="form-row full">
          <label class="toggle-label"><input type="checkbox" data-f="local_ocr" ${c.local_ocr ? "checked" : ""}> 使用本地 OCR（Tesseract，离线免费；需先安装并添加中文语言数据 chi_sim，安装方法见 README「本地 OCR」）</label>
        </div>`
      : "";
    return `<div class="ai-card" data-key="${key}">
      <div class="ai-card-head">
        <span class="cat">${CATEGORY_LABELS[key]}</span>
        <span class="desc">${AI_DESCS[key]}</span>
        <span class="model-tag">${esc(c.model || "未配置")}</span>
      </div>
      <div class="ai-card-body">
        ${localOcrRow}
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
            <button class="mini-btn" onclick="testAi('${key}')">测试</button>
          </div>
          ${toggleRow}
        </div>
        <div class="test-result" data-test-result="${key}"></div>
      </div>
    </div>`;
  }).join("");
  box.querySelectorAll(".ai-card-head").forEach((head) => {
    head.addEventListener("click", () => head.parentElement.classList.toggle("open"));
  });
  // 自动保存：输入框焦点离开（blur）即保存；供应商下拉 change 时先填充再保存
  box.querySelectorAll("input[data-f], select[data-f]").forEach((el) => {
    el.addEventListener("blur", autoSaveAi);
  });
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
      autoSaveAi(); // 供应商选择即时保存
    });
  });
}

/* 自动保存（0.1.7）：串行化 PUT，避免并发读改写竞争 */
let aiSaveChain = Promise.resolve();
let autoSaveTimer = null;

function autoSaveAi() {
  const items = {};
  for (const key of AI_KEYS) items[key] = collectAiItem(key);
  aiSaveChain = aiSaveChain
    .then(() => api("/api/settings/ai", { method: "PUT", body: { items } }))
    .then(() => {
      showAutoSaved();
      aiConfigCache = null; // 下次读取刷新脱敏值
    })
    .catch((e) => toast("自动保存失败：" + e.message, "error"));
}

function showAutoSaved() {
  const el = $("#ai-autosave-status");
  if (!el) return;
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  el.textContent = `✓ 已自动保存 ${hh}:${mm}`;
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(() => { el.textContent = ""; }, 4000);
}

function collectAiItem(key) {
  const card = document.querySelector(`.ai-card[data-key="${key}"]`);
  const item = { provider: "", base_url: "", api_key: "", model: "", prompt: "", temperature: 0.2, enabled: false };
  card.querySelectorAll("[data-f]").forEach((el) => {
    if (el.type === "number") {
      const v = parseFloat(el.value);
      item[el.dataset.f] = Number.isFinite(v) ? v : 0.2;
    } else if (el.type === "checkbox") {
      item[el.dataset.f] = el.checked;  // 0.1.39（R106）：rerank 启用开关
    } else {
      item[el.dataset.f] = el.value.trim();
    }
  });
  return item;
}

async function testAi(key) {
  const item = collectAiItem(key);
  if (!item.base_url) { toast("请先填写 Base URL（或选择供应商）。", "error"); return; }
  if (!item.api_key && aiConfigCache && aiConfigCache[key] && aiConfigCache[key].api_key) {
    item.api_key = aiConfigCache[key].api_key; // 未填新 Key 时用已保存的（脱敏值，后端自动换存储值）
  }
  const box = document.querySelector(`.ai-card[data-key="${key}"] [data-test-result]`);
  if (box) { box.className = "test-result"; box.textContent = "正在测试连通性并获取模型清单…"; }
  try {
    const r = await api("/api/settings/ai/test", { method: "POST", body: { key, config: item } });
    const models = (r && r.models) || [];
    if (box) {
      box.className = "test-result ok";
      box.innerHTML = models.length
        ? `✓ 连接成功，共 ${models.length} 个模型。点击模型名填入：<span class="model-chips">${models
            .map((m) => `<span class="chip" onclick="pickModel('${key}', '${esc(m).replace(/'/g, "\\'")}')">${esc(m)}</span>`)
            .join("")}</span>`
        : "✓ 连接成功（未返回模型清单）。";
    }
    toast(`连接成功，共 ${models.length} 个模型。`, "success");
  } catch (e) {
    if (box) { box.className = "test-result err"; box.textContent = "✗ " + e.message; }
    toast(e.message, "error");
  }
}

function pickModel(key, model) {
  const input = document.querySelector(`.ai-card[data-key="${key}"] [data-f="model"]`);
  if (input) input.value = model;
}

$("#btn-save-ai").addEventListener("click", () => {
  autoSaveAi();
  toast("正在保存全部 AI 配置…", "info");
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

function copyTextFallback(text) {
  // 壳内跨站 iframe（tauri.localhost 嵌入 127.0.0.1）：navigator.clipboard 受
  // Permissions Policy clipboard-write 限制会抛错；降级 execCommand("copy")
  // （仅需用户手势，不受该策略限制）
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}

async function copyToken() {
  const text = window._lastPlain || "";
  try {
    await navigator.clipboard.writeText(text);
    toast("已复制。", "success");
    return;
  } catch (e) { /* 跨站 iframe 权限受限，走降级 */ }
  if (copyTextFallback(text)) {
    toast("已复制。", "success");
  } else {
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
renderConvList();
