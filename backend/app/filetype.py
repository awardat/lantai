"""文件类型分类与解析：五类文件（文字文档 / Office / 文字 PDF / 图片 / 图片 PDF·OCR）。

分类规则：
- txt / md                     → text      文字文档
- docx                         → office    Office 文档
- pdf（有文本层，≥阈值字符）    → pdf_text  文字 PDF
- pdf（文本层缺失/过少）        → pdf_image 图片 PDF（扫描件，走 OCR）
- png/jpg/jpeg/webp/bmp/gif    → image     图片（视觉模型描述）
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Optional

from . import config

_SAFE_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    """净化文件名：去除路径分隔符与控制字符，防止路径穿越。"""
    name = Path(name).name  # 只取最后一段
    name = _SAFE_RE.sub("_", name).strip().strip(".")
    return name or "unnamed"


def classify_ext(ext: str) -> str:
    """扩展名 → 分类（不涉及 PDF 文本层判定）。"""
    ext = ext.lower()
    if ext in (".txt", ".md"):
        return "text"
    if ext == ".docx":
        return "office"
    if ext == ".pdf":
        return "pdf_text"  # 占位，解析时再判定是否 pdf_image
    if ext in config.IMAGE_EXTS:
        return "image"
    return "unknown"


def read_text_file(path: Path) -> str:
    """读取 txt/md（显式 UTF-8，容错 GBK 回落）。"""
    raw = path.read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_docx(path: Path) -> str:
    """docx → 段落 + 表格文本。"""
    from docx import Document  # python-docx

    doc = Document(str(path))
    parts: list[str] = []
    # 按文档顺序提取段落与表格
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for block in doc.element.body.iterchildren():
        if block.tag.endswith("}p"):
            para = Paragraph(block, doc)
            if para.text.strip():
                parts.append(para.text.strip())
        elif block.tag.endswith("}tbl"):
            table = Table(block, doc)
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def pdf_text_layers(path: Path) -> list[str]:
    """pypdf 逐页提取文本层。返回每页文本列表。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def pdf_extract_page_images(path: Path) -> list[tuple[int, bytes, str]]:
    """提取 PDF 各页内嵌图片（扫描件通常为整页图）。返回 [(页码, 字节, media_type)]。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    out: list[tuple[int, bytes, str]] = []
    for i, page in enumerate(reader.pages):
        try:
            for img in page.images:
                data = img.data
                mime = mimetypes.guess_type(img.name or "x.png")[0] or "image/png"
                out.append((i + 1, data, mime))
        except Exception:
            continue
    return out


def mime_of(ext: str) -> str:
    return mimetypes.guess_type("x" + ext)[0] or "application/octet-stream"
