"""配置 API：密码门禁 / AI 配置 / API token / 修改密码 / 系统信息。

除 verify 与 system/info 外均需会话（设置页密码校验后发放的 Cookie）。
RBAC（R101）落地后，此处升级为权限点鉴权。
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response

from .. import config, llm, security, store as store_mod
from ..schemas import (
    AiConfigPut,
    ParseConfig,
    PasswordChange,
    SystemInfo,
    TestRequest,
    TokenCreate,
    TokenCreated,
    TokenOut,
    VerifyRequest,
    ok,
)
from ..store import Store

router = APIRouter(prefix="/api/settings", tags=["settings"])

store = Store()
SESSION_COOKIE = "lantai_session"


def _require_session(session: str | None, header_session: str | None = None) -> None:
    # 双通道会话（0.1.25，CH-046）：壳内 iframe 与顶层 tauri.localhost 跨站，
    # SameSite=Lax 会话 cookie 在第三方上下文被 WebView2 拒绝存储；
    # 前端改经 X-Lantai-Session 请求头传递（localStorage），浏览器直开仍走 cookie。
    if not security.validate_session(header_session or session):
        raise HTTPException(status_code=401, detail="未验证的配置会话，请先输入配置密码。")


def _masked_config() -> dict:
    """返回脱敏后的 AI 配置（API Key 只留尾 4 位）。"""
    cfg = store.get_ai_config()
    out = {}
    for key, item in cfg.items():
        item = dict(item)
        if item.get("api_key"):
            item["api_key"] = security.mask_api_key(item["api_key"])
        out[key] = item
    return out


@router.post("/verify")
def verify(body: VerifyRequest, response: Response):
    if not security.check_rate_limit():
        raise HTTPException(status_code=429, detail="尝试次数过多，请 1 分钟后再试。")
    stored = store.get_setting("admin_password_hash", "")
    if not stored or not security.verify_password(body.password, stored):
        security.register_failure()
        raise HTTPException(status_code=401, detail="配置密码错误。")
    security.reset_failures()
    token = security.create_session()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return ok({"session": token}, message="验证通过。")


@router.get("/ai")
def get_ai(session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    return ok(_masked_config())


@router.put("/ai")
def put_ai(body: AiConfigPut, session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    current = store.get_ai_config()
    incoming = {k: v.model_dump() for k, v in body.items.items()}
    for key, item in incoming.items():
        if key not in current:
            continue
        old = current[key]
        new = dict(old)
        new.update({kk: vv for kk, vv in item.items() if kk in ("provider", "base_url", "model", "prompt")})
        # 0.1.39（R106）：enabled 能力开关（rerank 槽位用）
        if "enabled" in item and isinstance(item.get("enabled"), bool):
            new["enabled"] = item["enabled"]
        # 0.1.46（CH-090）：local_ocr 本地 OCR 开关（pdf_image 槽位用）
        if "local_ocr" in item and isinstance(item.get("local_ocr"), bool):
            new["local_ocr"] = item["local_ocr"]
        provider = (item.get("provider") or "").strip()
        if provider not in ("", "ollama", "openai-compatible"):
            raise HTTPException(status_code=400, detail="provider 仅支持 ollama 或 openai-compatible。")
        if provider:
            new["provider"] = provider
        temp = item.get("temperature")
        if temp is not None:
            try:
                new["temperature"] = min(2.0, max(0.0, float(temp)))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="temperature 必须是 0~2 之间的数字。") from None
        api_key = (item.get("api_key") or "").strip()
        if api_key and not api_key.startswith("****"):
            new["api_key"] = security.encrypt_api_key(api_key)
        else:
            # 保持原值（get_ai_config 已解密为明文，需重新加密后落库）
            new["api_key"] = security.encrypt_api_key(old.get("api_key", ""))
        incoming[key] = new
    store.save_ai_config(incoming)
    return ok(_masked_config(), message="AI 配置已保存，立即生效。")


@router.post("/ai/test")
def test_ai(body: TestRequest, session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    cfg = body.config.model_dump()
    item = dict(cfg)
    if (item.get("api_key") or "").startswith("****"):
        # 脱敏值：改用该槽位已保存的 Key
        stored = store.get_ai_config().get(body.key, {}).get("api_key", "")
        item["api_key"] = stored
    from ..schemas import AiItem

    try:
        models = llm.list_models(AiItem(**item))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ok({"models": models}, message=f"连接成功，共 {len(models)} 个模型。")


@router.post("/password")
def change_password(body: PasswordChange, session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    stored = store.get_setting("admin_password_hash", "")
    if not stored or not security.verify_password(body.old_password, stored):
        raise HTTPException(status_code=401, detail="旧密码不正确。")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位。")
    store.set_setting("admin_password_hash", security.hash_password(body.new_password))
    security.clear_sessions()  # 修改后所有会话失效，需重新验证
    return ok(None, message="密码已修改，请重新验证后进入配置。")


@router.get("/tokens")
def list_tokens(session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    return ok([TokenOut(**t).model_dump() for t in store.list_api_tokens()])


@router.post("/tokens")
def create_token(body: TokenCreate, session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    plain = security.generate_api_token()
    tid = store.create_api_token(body.name, plain)
    row = next(t for t in store.list_api_tokens() if t["id"] == tid)
    out = TokenCreated(**row, plaintext=plain)
    return ok(out.model_dump(), message="Token 已生成，明文仅展示这一次，请立即复制保存。")


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    _require_session(session, x_session)
    if not store.revoke_api_token(token_id):
        raise HTTPException(status_code=404, detail="Token 不存在或已吊销。")
    return ok(None, message="Token 已吊销，立即失效。")


@router.get("/system/info")
def system_info():
    import platform
    import sys

    return ok(
        SystemInfo(
            version=config.APP_VERSION,
            platform=f"{sys.platform} / {platform.machine()}",
            data_dir=str(config.DATA_DIR),
        ).model_dump()
    )


@router.get("/vendors")
def list_vendors():
    """预置 AI 供应商目录（免会话）：供配置界面下拉选择，自动填充 URL 与推荐模型。"""
    from ..vendors import VENDORS

    return ok(VENDORS)


@router.get("/parse")
def get_parse(session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    """解析队列配置与状态（0.1.18）：并发数 / 运行中 / 排队中。"""
    _require_session(session, x_session)
    from .. import task_queue

    return ok(task_queue.stats())


@router.put("/parse")
def put_parse(body: ParseConfig, session: str | None = Cookie(default=None, alias="lantai_session"),
        x_session: str | None = Header(default=None, alias="X-Lantai-Session")):
    """调整解析并发数（1~50），即时生效。"""
    _require_session(session, x_session)
    from .. import task_queue

    n = task_queue.set_concurrency(body.concurrency)
    store.set_setting("parse_concurrency", str(n))
    return ok(task_queue.stats(), message=f"解析并发数已调整为 {n}，立即生效。")
