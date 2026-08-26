"""文本切块：段落感知 + 长度窗口（默认 400 字符/块，重叠 50 字符）。"""
from __future__ import annotations

import re

from . import config

_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINE_RE = re.compile(r"\n\s*\n")
# 中日韩统一表意文字/扩展区/兼容区（含假名时排除——仅汉字之间删空格，
# 假名/英文单词间距保留；0.1.38 CH-073 方案 A）
_CJK_GAP_RE = re.compile(
    r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])\s+([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])"
)


def clean_ocr_spacing(text: str) -> str:
    """清理 OCR 文本层字间空白（0.1.38，CH-073 方案 A）：
    删除 CJK 汉字之间的空格/换行碎片（OCR 文本层常见缺陷："国 务 院"→"国务院"、
    单字分组换行合并）；英文单词间空格与中英之间空格不受影响。
    循环替换直至无 CJK 间空隙（空白可能被前一次替换后的相邻汉字暴露）。
    """
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        text = _CJK_GAP_RE.sub(r"\1\2", text)
    return text


def _normalize(text: str) -> str:
    """规整空白：合并行内连续空格，保留换行；再清理 CJK 间空格碎片（0.1.38 CH-073）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    return clean_ocr_spacing("\n".join(lines)).strip()


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
