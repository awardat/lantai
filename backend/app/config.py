"""兰台全局配置：路径、版本、常量。

所有路径基于运行形态解析：
- 源码运行（uvicorn）：BASE_DIR = backend/
- PyInstaller 冻结运行：BASE_DIR = 可执行文件所在目录
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_VERSION = "0.1.39"
APP_NAME = "lantai"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent  # backend/


def _frontend_dir() -> Path:
    """前端静态目录：源码模式 = 项目根/frontend；冻结模式 = 资源根(_internal)/frontend。"""
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", str(Path(sys.executable).resolve().parent)))
        return bundle / "frontend"
    return Path(__file__).resolve().parent.parent.parent / "frontend"


BASE_DIR = _base_dir()
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "rag.db"
LOGS_DIR = DATA_DIR / "logs"
FRONTEND_DIR = _frontend_dir()

MAX_UPLOAD_MB = 20
ALLOWED_EXTS = {
    ".txt", ".md", ".pdf", ".docx", ".doc", ".wps", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def allowed_exts_label() -> str:
    """上传白名单展示文案（0.1.35 起由 ALLOWED_EXTS 动态生成，杜绝与文档三方漂移）。"""
    docs = sorted(e.lstrip(".") for e in ALLOWED_EXTS - IMAGE_EXTS)
    imgs = sorted(e.lstrip(".") for e in IMAGE_EXTS)
    return " / ".join(docs) + " / 图片（" + "、".join(imgs) + "）"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_ADMIN_PASSWORD = "Admin#123"

# 切块参数
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

# 检索参数
DEFAULT_TOP_K = 5
MAX_TOP_K = 20

# PDF 文本层判定阈值（字符数，低于视为扫描件/图片 PDF）
PDF_TEXT_MIN_CHARS = 50

# AI 调用超时（秒）
TIMEOUT_CHAT = 120
TIMEOUT_VISION = 120
TIMEOUT_EMBED = 60
TIMEOUT_MODELS = 15


def ensure_dirs() -> None:
    """确保数据目录存在（首次启动）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
