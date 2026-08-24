// 验证壳终端面板标题版本标识：连接 CDP 读 panel-title 文本
const targets = await (await fetch("http://127.0.0.1:9222/json")).json();
const shell = targets.find((t) => t.url === "http://tauri.localhost/");
if (!shell) {
  console.log("未找到 shell target:", targets.map((t) => t.url));
  process.exit(1);
}
const ws = new WebSocket(shell.webSocketDebuggerUrl);
ws.onopen = () => {
  ws.send(
    JSON.stringify({
      id: 1,
      method: "Runtime.evaluate",
      params: {
        expression: 'document.getElementById("panel-title")?.textContent || "(null)"',
        returnByValue: true,
      },
    })
  );
};
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id === 1) {
    console.log("panel-title 文本:", JSON.stringify(m.result?.result?.value));
    process.exit(0);
  }
};
setTimeout(() => { console.log("超时"); process.exit(1); }, 8000);
