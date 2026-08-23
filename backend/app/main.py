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

from . import config, security, store as store_mod
from .store import Store

logger = logging.getLogger("lantai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动初始化（L8 修复：以 lifespan 替代已废弃的 on_event）。"""
    config.ensure_dirs()
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


from .routers import chat, docs, settings  # noqa: E402

app.include_router(docs.router)
app.include_router(chat.router)
app.include_router(settings.router)

if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
