"""文件类型分类与解析：五类文件（文字文档 / Office / 文字 PDF / 图片 / 图片 PDF·OCR）。

分类规则：
- txt / md                     → text      文字文档
- docx                         → office    Office 文档
- pdf（有文本层，≥阈值字符）    → pdf_text  文字 PDF
- pdf（文本层缺失/过少）        → pdf_image 图片 PDF（扫描件，走 OCR）
- png/jpg/jpeg/webp/bmp/gif    → image     图片（视觉模型描述）
"""
from __future__ import annotations

import io
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
    if ext in (".docx", ".doc", ".wps", ".xls", ".xlsx", ".ppt", ".pptx"):
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


# ---------- 0.1.30：常见办公文档（doc/wps/xls/xlsx/ppt/pptx） ----------

# .doc/.wps 文本提取的最小可读段长度（连续可打印字符数低于此视为噪声丢弃）
_OLE_MIN_RUN = 4


def _ole_utf16le_runs(data: bytes) -> list[str]:
    """从字节流中提取连续可读文本段（UTF-16LE 解码 + 可打印过滤，演示级）。

    OLE2 二进制文档（.doc/.wps）的 WordDocument 流以 UTF-16LE 存储文本，
    简化提取：按 2 字节步长解码，保留连续可打印字符运行。
    """
    runs: list[str] = []
    cur: list[str] = []
    for i in range(0, len(data) - 1, 2):
        cp = data[i] | (data[i + 1] << 8)
        if cp in (0, 0x0D, 0x0A, 0x09) or (0x20 <= cp < 0xFFFF):
            ch = chr(cp)
            if ch.isprintable() or ch in "\r\n\t":
                cur.append(ch)
                continue
        if len(cur) >= _OLE_MIN_RUN:
            runs.append("".join(cur).strip())
        cur = []
    if len(cur) >= _OLE_MIN_RUN:
        runs.append("".join(cur).strip())
    return runs


def parse_doc(path: Path) -> str:
    """.doc（Word 97-2003 OLE2）→ 文本（演示级：WordDocument 流 UTF-16LE 段提取）。"""
    import olefile

    try:
        with olefile.OleFileIO(str(path)) as ole:
            if not ole.exists("WordDocument"):
                return ""
            data = ole.openstream("WordDocument").read()
    except Exception:
        # 非 OLE2 文件（损坏/伪装扩展名）→ 返回空，由上层提示"未能提取文本"
        return ""
    runs = _ole_utf16le_runs(data)
    # 可读性兜底：提取结果过差（如仅噪声）返回空串，由上层提示
    text = "\n".join(runs).strip()
    return text if text_readability(text) >= 0.15 else ""


def parse_wps(path: Path) -> str:
    """.wps（WPS 文字，OLE2 与 Word 兼容）→ 文本（同 .doc 提取）。"""
    return parse_doc(path)


def parse_xls(path: Path) -> str:
    """.xls（Excel 97-2003）→ 单元格文本拼接。"""
    import xlrd

    try:
        book = xlrd.open_workbook(str(path))
    except Exception:
        return ""  # 非 xls（损坏/伪装扩展名）→ 空，由上层提示
    parts: list[str] = []
    for sheet in book.sheets():
        for row in range(sheet.nrows):
            cells = []
            for col in range(sheet.ncols):
                v = sheet.cell_value(row, col)
                if isinstance(v, float) and v == int(v):
                    v = int(v)
                if v not in (None, ""):
                    cells.append(str(v))
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def parse_xlsx(path: Path) -> str:
    """.xlsx → 单元格文本拼接。"""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(str(path), read_only=True, data_only=True)
    except Exception:
        return ""  # 非 xlsx（损坏/伪装扩展名）→ 空，由上层提示
    parts: list[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                parts.append(" | ".join(cells))
    wb.close()
    return "\n".join(parts)


def _shape_text(shape) -> str:
    """递归提取 shape 文本（含文本框/表格/分组）。"""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    out: list[str] = []
    st = shape.shape_type
    if st == MSO_SHAPE_TYPE.GROUP:
        for sub in shape.shapes:
            out.append(_shape_text(sub))
        return "\n".join(out)
    if st == MSO_SHAPE_TYPE.TABLE:
        for row in shape.table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                out.append(" | ".join(cells))
        return "\n".join(out)
    if shape.has_text_frame:
        for para in shape.text_frame.paragraphs:
            t = "".join(run.text for run in para.runs).strip()
            if t:
                out.append(t)
    return "\n".join(out)


def parse_pptx(path: Path) -> str:
    """.pptx → 幻灯片文本框/表格文本。"""
    from pptx import Presentation

    try:
        prs = Presentation(str(path))
    except Exception:
        return ""  # 非 pptx（损坏/伪装扩展名）→ 空，由上层提示
    parts: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            t = _shape_text(shape).strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def parse_office(path: Path, ext: str) -> str:
    """office 类统一解析入口（按扩展名分发，0.1.30）。"""
    ext = ext.lower()
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".doc":
        return parse_doc(path)
    if ext == ".wps":
        return parse_wps(path)
    if ext == ".xls":
        return parse_xls(path)
    if ext == ".xlsx":
        return parse_xlsx(path)
    if ext == ".pptx":
        return parse_pptx(path)
    if ext == ".ppt":
        return ""  # .ppt 为 OLE2 二进制演示文稿，暂无可靠纯 Python 提取，返回空由上层提示
    return ""


_CHAR_CODE_TOKEN_RE = re.compile(r"/[A-Za-z0-9]{1,8}")
_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def text_readability(text: str) -> float:
    """0~1 文本可读性：CJK 占比 + 完整英文单词占比，扣减字符码 token（如 /G21/G22）。

    用途：区分"真实文本"与"编码不可映射的字符码伪文本"（内嵌字体缺 ToUnicode 的 PDF）。
    """
    if not text:
        return 0.0
    total = len(text)
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf")
    word_chars = sum(len(w) for w in _WORD_RE.findall(text))
    code_tokens = len(_CHAR_CODE_TOKEN_RE.findall(text))
    score = (cjk * 1.5 + word_chars) / total + 0.5 - code_tokens * 4 / total
    return max(0.0, min(1.0, score))


# 可读性阈值（0.1.16 样本验证）：GBT 43052 伪文本（字符码）得分 0.0；
# 正常中文/英文文本得分约 1.0；0.4 留出宽松余量，兼顾英文文档与少量噪声。
READABILITY_THRESHOLD = 0.4


def pdf_is_pseudo_text(path: Path) -> bool:
    """检测"文本层存在但编码不可映射"（pypdf 能提取出字符码伪文本，可读性低）。"""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        full = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return False
    return len(full) >= config.PDF_TEXT_MIN_CHARS and text_readability(full) < READABILITY_THRESHOLD


def _pypdf_page_text(path: Path, page_index: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if page_index >= len(reader.pages):
        return ""
    try:
        return reader.pages[page_index].extract_text() or ""
    except Exception:
        return ""


def pdf_text_layers(path: Path) -> list[tuple[str, bool]]:
    """逐页提取文本（R117①：pdfminer layout 按位置取行 → 几何排序还原阅读顺序）。

    返回 [(页面文本, 是否文本页), ...]：
    - 页面文本：按阅读顺序（栏内 y 降序、x 升序）拼接的行；
    - 是否文本页：该页有效文本 ≥ PDF_TEXT_MIN_CHARS 字符且可读性达标（0.1.16 双引擎兜底：
      pdfminer 空/不可读时回退 pypdf，仍不可读（如编码不可映射的伪文本）→ 判图片页走 OCR）。
    处理：跨页重复行（页眉/页脚模式）剔除、页顶/页底纯数字页码碎片剔除、基础双栏检测。
    """
    from collections import Counter

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextLineHorizontal, LTTextContainer

    page_lines: list[list[tuple[str, float, float, float, float]]] = []
    all_lines: list[str] = []
    heights: list[float] = []
    for page_layout in extract_pages(str(path)):
        lines: list[tuple[str, float, float, float, float]] = []
        for el in page_layout:
            if not isinstance(el, LTTextContainer):
                continue
            for ln in el:
                if isinstance(ln, LTTextLineHorizontal):
                    t = ln.get_text().strip()
                    if t:
                        lines.append((t, ln.x0, ln.x1, ln.y0, ln.y1))
        page_lines.append(lines)
        all_lines.extend(t for t, *_ in lines)
        heights.append(float(page_layout.height))
    # 跨页重复行（≥3 页出现 → 页眉/页脚等装饰性内容）
    repeated = {t for t, c in Counter(all_lines).items() if c >= 3}

    pages_out: list[tuple[str, bool]] = []
    for idx, (lines, height) in enumerate(zip(page_lines, heights)):
        ordered = _layout_order(lines, height, repeated)
        text = "\n".join(ordered).strip()
        if len(text) >= config.PDF_TEXT_MIN_CHARS and text_readability(text) >= READABILITY_THRESHOLD:
            pages_out.append((text, True))
            continue
        # 双引擎兜底：pdfminer 空/不可读 → 尝试 pypdf（0.1.16）
        fallback = _pypdf_page_text(path, idx).strip()
        if len(fallback) >= config.PDF_TEXT_MIN_CHARS and text_readability(fallback) >= READABILITY_THRESHOLD:
            pages_out.append((fallback, True))
        else:
            pages_out.append((text, False))
    return pages_out


def _layout_order(
    lines: list[tuple[str, float, float, float, float]],
    height: float,
    repeated: set[str],
) -> list[str]:
    """按阅读顺序排列文本行：过滤装饰 → 双栏检测 → 栏内几何排序。"""
    kept: list[tuple[str, float, float, float, float]] = []
    for t, x0, x1, y0, y1 in lines:
        s = t.strip()
        if not s:
            continue
        if s in repeated:  # 跨页重复（页眉/页脚）
            continue
        # 页码碎片：纯数字且位于页顶（上 12%）/页底（下 15%）区域
        if re.fullmatch(r"[\d\s]{1,6}", s) and (y1 > height * 0.88 or y0 < height * 0.15):
            continue
        kept.append((t, x0, x1, y0, y1))
    if not kept:
        return []

    # 基础双栏检测：行中点 x 的最大空隙
    mids = sorted((x0 + x1) / 2 for _, x0, x1, _, _ in kept)
    page_w = max(x1 for _, _, x1, _, _ in kept) - min(x0 for _, x0, _, _, _ in kept)
    gap, split = 0.0, None
    for a, b in zip(mids, mids[1:]):
        if b - a > gap:
            gap, split = b - a, (a + b) / 2
    two_column = gap > page_w * 0.12 and len(kept) >= 16

    def by_col(col: str) -> list[str]:
        rows = [k for k in kept if (k[1] + k[2]) / 2 < split] if col == "left" else [k for k in kept if (k[1] + k[2]) / 2 >= split]
        return [t for t, *_ in sorted(rows, key=lambda k: (-k[4], k[1]))]  # y 降序、x 升序

    if two_column:
        return by_col("left") + by_col("right")
    return [t for t, *_ in sorted(kept, key=lambda k: (-k[4], k[1]))]


def pdf_extract_page_images(path: Path) -> list[tuple[int, bytes, str]]:
    """提取 PDF 各页内嵌图片（扫描件通常为整页图）。返回 [(页码, 字节, media_type)]。

    依赖 Pillow（pypdf 图片提取要求 `pip install pypdf[image]`）。
    """
    from pypdf import PdfReader

    try:
        from PIL import Image  # noqa: F401  确保 pillow 可用
    except ImportError as exc:
        raise RuntimeError("PDF 图片提取需要 Pillow，请执行：pip install pillow（requirements 已包含）。") from exc

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


# 视觉供应商通用支持格式（MiMo/通义/OpenAI 等均支持；超出即 400 拒绝）
_VISION_OK_FORMATS = {"JPEG", "PNG", "BMP", "WEBP", "GIF"}


def normalize_image_for_vision(data: bytes, mime: str) -> tuple[bytes, str]:
    """视觉模型图片标准化（0.1.37，CH-066）：Pillow 探测图片实际格式，不在供应商通用
    支持范围（jpeg/png/bmp/webp/gif）的格式（如 PDF 内嵌 TIFF/JPEG2000/CCITT）统一
    转码为 JPEG，消除"仅支持 jpg、bmp、webp、gif、png 格式"类 400。解码失败原样返回
    （交由上游报错，不吞异常）。
    """
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as im:
            if (im.format or "").upper() in _VISION_OK_FORMATS:
                return data, mime  # 已支持，原样发送（避免无谓转码与体积膨胀）
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=90)
            return buf.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 无法解码（损坏/未知）→ 原样发送，由上游返回具体错误
        return data, mime
