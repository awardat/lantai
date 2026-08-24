// CDP 模拟文件拖放：验证前端 drop 处理在收到事件时是否正常工作
// 用法：壳运行中（DSH_DEBUG_DEVTOOLS=1）执行
const targets = await (await fetch("http://127.0.0.1:9222/json")).json();
const iframe = targets.find((t) => t.type === "iframe");
if (!iframe) {
  console.log("未找到 iframe target");
  process.exit(1);
}
const ws = new WebSocket(iframe.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
const send = (method, params = {}) =>
  new Promise((res) => {
    const i = ++id;
    pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m);
    pending.delete(m.id);
  }
};
await new Promise((r) => (ws.onopen = r));

// 打开上传浮层（模拟点击"上传文档"）
await send("Runtime.evaluate", {
  expression: `document.getElementById('upload-overlay').classList.remove('hidden')`,
});

// 构造拖放数据（一个真实存在的文件）
const dragData = {
  items: [],
  files: ["C:\\code\\lantai\\scripts\\make_sample_docs.py"],
  dragOperationsMask: 1,
};

// dragEnter → dragOver → drop 到 #drop-zone 中心
const rect = await send("Runtime.evaluate", {
  expression: `(() => { const r = document.getElementById('drop-zone').getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; })()`,
  returnByValue: true,
});
const { x, y } = rect.result.result.value;

for (const type of ["dragEnter", "dragOver", "drop"]) {
  const r = await send("Input.dispatchDragEvent", {
    type,
    x,
    y,
    data: dragData,
  });
  console.log(type, "→", r.error ? JSON.stringify(r.error) : "ok");
}

// 等待后检查上传列表是否有条目（前端 drop 处理器是否触发）
await new Promise((r) => setTimeout(r, 1500));
const check = await send("Runtime.evaluate", {
  expression: `(() => { const items = document.querySelectorAll('#upload-list .upload-item'); return {count: items.length, first: items[0] ? items[0].textContent.slice(0, 50) : null}; })()`,
  returnByValue: true,
});
console.log("上传列表:", JSON.stringify(check.result.result.value));

process.exit(0);
