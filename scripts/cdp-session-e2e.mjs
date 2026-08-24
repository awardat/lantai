// 0.1.25 端到端：壳内 iframe 登录 → localStorage 存会话 → header 通道访问受保护接口
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

// 1. 模拟前端登录流程：verify → 存 localStorage
const login = await send("Runtime.evaluate", {
  expression: `(async () => {
    const r = await fetch('/api/settings/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({password:'Admin#123'})});
    const j = await r.json();
    if (j.code === 0 && j.data && j.data.session) localStorage.setItem('lantai_session', j.data.session);
    return {code: j.code, saved: !!localStorage.getItem('lantai_session')};
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
console.log("登录+存储:", JSON.stringify(login.result?.result?.value));

// 2. 模拟前端 api() 封装：带 X-Lantai-Session 头访问受保护接口
const getAi = await send("Runtime.evaluate", {
  expression: `(async () => {
    const s = localStorage.getItem('lantai_session');
    const r = await fetch('/api/settings/ai', {headers: {'X-Lantai-Session': s}});
    const j = await r.json();
    return {status: r.status, code: j.code, groups: j.data ? Object.keys(j.data).length : 0};
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
console.log("header 通道访问:", JSON.stringify(getAi.result?.result?.value));

// 3. 无凭证对照
const noAuth = await send("Runtime.evaluate", {
  expression: `fetch('/api/settings/ai').then(r => r.json()).then(j => j.code)`,
  awaitPromise: true,
  returnByValue: true,
});
console.log("无凭证对照(应 401):", JSON.stringify(noAuth.result?.result?.value));

process.exit(0);
