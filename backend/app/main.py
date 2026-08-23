"""兰台（lantai）FastAPI 应用入口。

- 纯 API：/api/*（docs / chat / settings）
- 前端托管：/ 挂载 frontend/（原生单页，无构建）
- 统一响应：{code, message, data}；错误 message 为中文
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import agent_log, config, security, store as store_mod
from .store import Store

logger = logging.getLogger("lantai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动初始化（L8 修复：以 lifespan 替代已废弃的 on_event）。"""
    config.ensure_dirs()
    _setup_file_logging()
    agent_log.setup_agent_logging()
    st = Store()
    # 首次启动初始化：默认配置密码 / 会话密钥 / 版本号
    if not st.get_setting("admin_password_hash"):
        st.set_setting("admin_password_hash", security.hash_password(config.DEFAULT_ADMIN_PASSWORD))
        logger.info("已初始化默认配置密码（Admin#123），请在设置页修改。")
    if not st.get_setting("session_secret"):
        security._session_secret()
    st.set_setting("app_version", config.APP_VERSION)
    if config.FRONTEND_DIR.exists():
        logger.info("前端静态资源：%s", config.FRONTEND_DIR)
    else:
        logger.warning("前端目录不存在：%s（仅 API 可用）", config.FRONTEND_DIR)
    yield


def _setup_file_logging() -> None:
    """每次启动创建新的日志文件（data/logs/lantai-<启动时间戳>.log），保留最近 20 个。

    M1 修复：开头幂等提前返回（root 已有 FileHandler 时不再创建 fh，避免 reload 场景句柄泄漏）。
    """
    from datetime import datetime

    root = logging.getLogger()
    if any(isinstance(h, logging.FileHandler) for h in root.handlers):
        return  # 已配置（如 reload 场景），避免重复创建

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    log_path = config.LOGS_DIR / f"lantai-{ts}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    # 单点挂载：
    # - root：业务日志（lantai 等）传播至此 → 控制台(uvicorn default) + 文件
    # - uvicorn：uvicorn.error 传播至此（propagate=True 默认）→ 控制台 + 文件
    # - uvicorn.access：propagate=False，自身挂 fh → 控制台(自带 access) + 文件
    root.addHandler(fh)
    uv = logging.getLogger("uvicorn")
    uv.propagate = False
    if not any(isinstance(h, logging.FileHandler) for h in uv.handlers):
        uv.addHandler(fh)
    for name in ("uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [h for h in lg.handlers if not isinstance(h, logging.FileHandler)]
    lg = logging.getLogger("uvicorn.access")
    lg.propagate = False
    if not any(isinstance(h, logging.FileHandler) for h in lg.handlers):
        lg.addHandler(fh)
    root.setLevel(logging.INFO)
    # 保留最近 20 个日志文件
    logs = sorted(config.LOGS_DIR.glob("lantai-*.log"))
    for old in logs[:-20]:
        try:
            old.unlink()
        except OSError:
            pass
    logger.info("日志文件：%s", log_path)


app = FastAPI(
    title="兰台（lantai）本地 RAG 知识库",
    version=config.APP_VERSION,
    description="本地运行的 RAG 知识库演示系统",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
def _http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": exc.detail, "data": None},
    )


@app.exception_handler(RequestValidationError)
def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    msg = first.get("msg", "参数错误")
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": f"参数错误（{loc}）：{msg}", "data": None},
    )


@app.exception_handler(Exception)
def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常：%s", exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"服务内部错误：{exc}。请查看后端日志。", "data": None},
    )


from .routers import chat, conversations, docs, settings  # noqa: E402

app.include_router(docs.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(settings.router)

if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
