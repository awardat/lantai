"""0.1.25 双通道会话：settings.py 批量改造（verify 返回 session + header 通道）。"""
import io

p = r"C:\code\lantai\backend\app\routers\settings.py"
t = io.open(p, encoding="utf-8").read()

# 1. import Header
t = t.replace(
    "from fastapi import APIRouter, Cookie, HTTPException, Response",
    "from fastapi import APIRouter, Cookie, Header, HTTPException, Response",
)

# 2. _require_session 双通道
t = t.replace(
    'def _require_session(session: str | None) -> None:\n    if not security.validate_session(session):',
    'def _require_session(session: str | None, header_session: str | None = None) -> None:\n'
    '    # 双通道会话（0.1.25，CH-046）：壳内 iframe 与顶层 tauri.localhost 跨站，\n'
    '    # SameSite=Lax 会话 cookie 在第三方上下文被 WebView2 拒绝存储；\n'
    '    # 前端改经 X-Lantai-Session 请求头传递（localStorage），浏览器直开仍走 cookie。\n'
    '    if not security.validate_session(header_session or session):',
)

# 3. 端点签名加 Header 参数（9 处）
old_sig = 'session: str | None = Cookie(default=None, alias="lantai_session")):'
new_sig = (
    'session: str | None = Cookie(default=None, alias="lantai_session"),\n'
    '        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):'
)
n = t.count(old_sig)
t = t.replace(old_sig, new_sig)
print("签名替换:", n)

# 4. 调用点传双通道
t = t.replace("_require_session(session)", "_require_session(session, x_session)")
print("调用替换:", t.count("_require_session(session, x_session)"))

# 5. verify 返回 session 明文（仅此一次）
t = t.replace(
    'return ok(None, message="验证通过。")',
    'return ok({"session": token}, message="验证通过。")',
)

io.open(p, "w", encoding="utf-8", newline="").write(t)
print("done")
