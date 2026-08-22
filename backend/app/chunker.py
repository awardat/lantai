"""文本切块：段落感知 + 长度窗口（默认 400 字符/块，重叠 50 字符）。"""
from __future__ import annotations

import re

from . import config

_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINE_RE = re.compile(r"\n\s*\n")


def _normalize(text: str) -> str:
    """规整空白：合并行内连续空格，保留换行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


def chunk_text(text: str, chunk_size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    """按段落累积切块，相邻块保留 overlap 字符重叠。返回非空块列表。"""
    text = _normalize(text)
    if not text:
        return []
    paragraphs = [p.strip() for p in _BLANK_LINE_RE.split(text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            # 超长段落内部按窗口切分
            start = 0
            while start < len(para):
                chunks.append(para[start : start + chunk_size])
                start += chunk_size - overlap
            continue
        if len(current) + len(para) + 1 > chunk_size and current:
            chunks.append(current)
            current = current[-overlap:] if overlap else ""
        current = (current + "\n" + para).strip() if current else para
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]
