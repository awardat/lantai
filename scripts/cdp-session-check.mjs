// 复现壳内 iframe 会话问题：verify 登录 → 检查 cookie 与后续请求
// 用法：启动壳（DSH_DEBUG_DEVTOOLS=1）后运行 node cdp-session-check.mjs
const targets = await (await fetch("http://127.0.0.1:9222/json")).json();
const iframe = targets.find((t) => t.type === "iframe");
if (!iframe) {
  console.log("未找到 iframe target:", targets.map((t) => `${t.type}:${t.url}`));
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

// 1. verify 登录
const login = await send("Runtime.evaluate", {
  expression: `fetch('/api/settings/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({password:'Admin#123'})}).then(r => r.json())`,
  awaitPromise: true,
  returnByValue: true,
});
console.log("verify 响应:", JSON.stringify(login.result?.result?.value));

// 2. 检查当前 cookie（document.cookie 只显示非 httponly；会话 cookie 是 httponly，用 CDP Network 域看）
const cookie = await send("Runtime.evaluate", {
  expression: `document.cookie`,
  returnByValue: true,
});
console.log("document.cookie:", JSON.stringify(cookie.result?.result?.value));

// 3. 用 fetch 携带同源 cookie 请求受保护接口（fetch 默认 credentials: same-origin）
const getAi = await send("Runtime.evaluate", {
  expression: `fetch('/api/settings/ai').then(r => r.json())`,
  awaitPromise: true,
  returnByValue: true,
});
console.log("GET /api/settings/ai:", JSON.stringify(getAi.result?.result?.value).slice(0, 200));

process.exit(0);
