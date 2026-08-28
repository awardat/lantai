"""解析管线：文件类型路由 → 文本提取 → 切块 → 向量化 → 入库。

- 文字文档 / Office / 文字 PDF：本地解析（无需 LLM）；
- 图片：调用该类型配置的视觉模型生成内容描述；
- 图片 PDF（扫描件）：逐页提取内嵌图片 → OCR 模型识别。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import chunker, config, embeddings, filetype, llm, store as store_mod
from .store import Store


def _vision_describe(cfg: dict, raw: bytes, mime: str, fallback_prompt: str, slot: str = "", doc_id: int | None = None) -> str:
    from .schemas import AiItem

    item = AiItem(**cfg)
    prompt = (cfg.get("prompt") or "").strip() or fallback_prompt
    # 0.1.37（CH-066）：非通用格式（TIFF/JPEG2000 等）统一转码 JPEG，消除供应商 400
    raw, mime = filetype.normalize_image_for_vision(raw, mime)
    return llm.chat(
        item,
        [{"role": "user", "content": prompt}],
        images=[(raw, mime)],
        timeout=config.TIMEOUT_VISION,
        slot=slot,
        doc_id=doc_id,
    )


def _extract_text(doc: dict, file_path: Path, st: Store) -> tuple[str, str]:
    """返回 (文本, 最终分类)。"""
    category = doc["category"]
    if category == "text":
        return filetype.read_text_file(file_path), category
    if category == "office":
        # 0.1.30：doc/wps/xls/xlsx/ppt/pptx 按扩展名分发；.ppt 二进制演示文稿无纯 Python
        # 提取方案，可能返回空 → 下方空文本统一走"文本提取受限"提示
        return filetype.parse_office(file_path, doc.get("ext", "")), category
    if category == "pdf_text":
        # R117② 页级判定：文本页走几何排序提取，图片页（无文本层）走 OCR
        pages = filetype.pdf_text_layers(file_path)
        text_parts: list[str] = []
        ocr_pages: list[int] = []
        for i, (page_text, is_text_page) in enumerate(pages, 1):
            if is_text_page:
                text_parts.append(page_text)
            else:
                ocr_pages.append(i)
        if ocr_pages:
            text_parts.append(_ocr_pdf_pages(file_path, st, ocr_pages, doc_id=doc.get("id")))
        # R117③：文字 PDF 页内图片（图表）→ 视觉描述 + 页码绑定（跳过已 OCR 的图片页）
        text_parts.append(_describe_inline_images(file_path, st, skip_pages=set(ocr_pages), doc_id=doc.get("id")))
        text = "\n\n".join(p for p in text_parts if p and p.strip())
        if len(text.strip()) < config.PDF_TEXT_MIN_CHARS:
            # 全部页面均无有效文本 → 判定为扫描件：先更新分类（失败时也不误导），再整文档走 OCR
            st.set_document_category(doc.get("id"), "pdf_image")
            return _ocr_pdf(file_path, st, doc_id=doc.get("id")), "pdf_image"
        # 含 OCR 内容（图片页）→ 分类归为 pdf_image（0.1.11：避免单页扫描件显示为"文字 PDF"）
        final_category = "pdf_image" if ocr_pages else category
        return text, final_category
    if category == "image":
        cfg = st.get_ai_config()["image"]
        raw = file_path.read_bytes()
        mime = filetype.mime_of(doc["ext"])
        return _vision_describe(cfg, raw, mime, "请描述这张图片的内容。", slot="image", doc_id=doc.get("id")), category
    if category == "pdf_image":
        return _ocr_pdf(file_path, st), category
    raise RuntimeError(f"不支持的文件类型：{doc.get('ext', '')}")


def _describe_inline_images(file_path: Path, st: Store, skip_pages: set[int] | None = None, doc_id: int | None = None) -> str:
    """文字 PDF 页内图片（图表/照片）→ 视觉模型描述，前缀标注页码（图题/引用绑定基础）。

    视觉模型不可用或图片缺失时跳过，不阻塞解析。
    """
    skip_pages = skip_pages or set()
    try:
        images = filetype.pdf_extract_page_images(file_path)
    except Exception:
        return ""
    images = [(p, d, m) for p, d, m in images if p not in skip_pages]
    if not images:
        return ""
    cfg = st.get_ai_config()["image"]
    parts = []
    for page_no, data, mime in images:
        try:
            desc = _vision_describe(cfg, data, mime, "请描述这张图片的内容，包括其中的文字。", slot="image", doc_id=doc_id)
            parts.append(f"【图片（第 {page_no} 页）】{desc}")
        except Exception:
            continue  # 视觉模型不可用：跳过该图
    return "\n".join(parts)


def _ocr_pdf_pages(file_path: Path, st: Store, page_nos: list[int], doc_id: int | None = None) -> str:
    """对指定页码的页面图片执行 OCR（pdf_image 通道配置；0.1.46 支持本地 Tesseract）。"""
    wanted = set(page_nos)
    try:
        images = filetype.pdf_extract_page_images(file_path)
    except Exception:
        return ""
    cfg = st.get_ai_config()["pdf_image"]
    local = bool(cfg.get("local_ocr"))
    parts = []
    for page_no, data, mime in images:
        if page_no not in wanted:
            continue
        try:
            if local:
                text = _ocr_image_tesseract(data, mime)
            else:
                text = _vision_describe(cfg, data, mime, "请识别图片中的全部文字，保持原文顺序。", slot="pdf_image", doc_id=doc_id)
            text = _scrub_ocr_noise(text)  # 0.1.47（CH-092/A）：公式/水印页噪声清洗
            if text:
                parts.append(f"【第 {page_no} 页】\n{text}")
        except Exception:  # noqa: BLE001 逐页容错（对齐 _ocr_pdf，CH-091）：坏页跳过
            continue
    return "\n\n".join(parts)


def _ocr_pdf(file_path: Path, st: Store, doc_id: int | None = None) -> str:
    """扫描件 PDF：逐页提取图片 → OCR（0.1.46 起可选本地 Tesseract 离线识别）。

    0.1.38（CH-070/CH-069）：无内嵌位图（矢量描摹/混合 PDF）时回退 pymupdf
    整页渲染 PNG 走同一 OCR 通道；渲染也失败则给出明确提示，不再笼统报"未能提取文本"。
    """
    cfg = st.get_ai_config()["pdf_image"]
    local = bool(cfg.get("local_ocr"))
    images = filetype.pdf_extract_page_images(file_path)
    if not images:
        images = filetype.pdf_render_page_images(file_path)
    if not images:
        raise RuntimeError(
            "该 PDF 无内嵌位图且无法整页渲染（可能是矢量描摹或空白页），"
            "无法执行 OCR，请提供位图版文件。"
        )
    parts = []
    for page_no, data, mime in images:
        # 0.1.47（CH-092/A + CH-091）：逐页容错 + OCR 噪声清洗（公式/水印页不入库）
        try:
            if local:
                text = _ocr_image_tesseract(data, mime)
            else:
                text = _vision_describe(cfg, data, mime, "请识别图片中的全部文字，保持原文顺序。", slot="pdf_image", doc_id=doc_id)
        except Exception as exc:  # noqa: BLE001 超时/解码失败等转中文，逐页跳过
            continue
        text = _scrub_ocr_noise(text)
        if text:
            parts.append(f"【第 {page_no} 页】\n{text}")
    if not parts:
        raise RuntimeError("OCR 未识别到有效文本（可能为公式/符号扫描件），未入库任何内容。")
    return "\n\n".join(parts)


def _find_tesseract() -> str | None:
    """探测本机 Tesseract 可执行文件（PATH → 常见安装路径）。"""
    import shutil

    exe = shutil.which("tesseract")
    if exe:
        return exe
    cands = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Tesseract-OCR\tesseract.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Tesseract-OCR\tesseract.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def _find_tessdata(exe: str) -> str | None:
    """探测中文语言数据目录：TESSDATA_PREFIX → 用户级 tessdata（免提权方案）→ 安装目录 tessdata。"""
    for p in (os.environ.get("TESSDATA_PREFIX"), os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Tesseract-OCR\tessdata")):
        if p and os.path.exists(os.path.join(p, "chi_sim.traineddata")):
            return p
    td = os.path.join(os.path.dirname(exe), "tessdata")
    if os.path.exists(os.path.join(td, "chi_sim.traineddata")):
        return td
    return None


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_LATEX_RE = re.compile(r"\\(?:text|frac|sum|int|begin|end|table|mbox|displaystyle)")
_SAME_CHAR_RE = re.compile(r"([^ \t])\1{5,}")  # 非空白连续同字符 ≥6（空格串不判噪声：OCR 常用多空格分隔字词）


def _scrub_ocr_noise(text: str) -> str:
    """OCR 文本噪声清洗（0.1.47，CH-092/A，GBT 5271.18 公式扫描件教训）。

    图片 PDF 含公式/符号排版时，OCR（Tesseract/视觉）会输出 `\text { 2 }`、
    `} } }`、`1 1 1` 等 LaTeX 命令串伪文本，进入索引即污染检索且超长重复行
    被切片放大（案例 163 切片仅 58 种文本）。规则：
    - 行级丢弃：LaTeX 命令行 / 连续同字符 ≥6 / 无中文且无字母数字且 ASCII 符号占比 >50%（纯符号行）；
    - 连续重复行压缩（同文本 >3 保留 3）；
    - 清洗后为空返回 ""（该页不入库，宁缺毋滥）。
    """
    out: list[str] = []
    prev = None
    repeats = 0
    for raw in (text or "").splitlines():
        ln = raw.strip()
        if not ln:
            continue
        if _LATEX_RE.search(ln):
            continue
        if _SAME_CHAR_RE.search(ln):
            continue
        toks = ln.split()
        if len(toks) >= 4 and len(set(toks)) <= 2:
            continue  # 重复短 token 行（"1 1 1…" / "} } }"）
        has_cjk = bool(_CJK_RE.search(ln))
        has_alnum = bool(_ALNUM_RE.search(ln))
        if not has_cjk and not has_alnum:
            ascii_syms = sum(1 for ch in ln if 0x21 <= ord(ch) <= 0x7E)
            if ascii_syms > len(ln) * 0.5:
                continue
        if ln == prev:
            repeats += 1
            if repeats > 3:
                continue
        else:
            repeats = 1
            prev = ln
        out.append(ln)
    return "\n".join(out).strip()


def _ocr_image_tesseract(data: bytes, mime: str) -> str:
    """本地 Tesseract OCR（0.1.46，CH-090）：图片字节 → 文本（chi_sim + eng）。

    通过命令行走系统 Tesseract（https://github.com/tesseract-ocr），不引入 Python
    重依赖；缺失时给出安装指引（README「本地 OCR：安装方法 A」）。
    0.1.48（CH-093）：成功/失败均写 agent_log（slot=ocr_local）——识别出的文字
    可在 agent-*.log 中查看（此前本地 OCR 不进日志，用户误以为"日志掉了"）。
    """
    import time

    from . import agent_log

    t0 = time.monotonic()
    msg = [{"role": "user", "content": f"本地 OCR（Tesseract，{mime or 'image'}）：识别页图数据 {len(data)} 字节"}]
    try:
        text = _run_tesseract(data)
    except Exception as exc:  # noqa: BLE001
        agent_log.log_call(
            slot="ocr_local", provider="local", base_url="tesseract", model="chi_sim+eng",
            messages=msg, ok=False, error=str(exc),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        raise
    agent_log.log_call(
        slot="ocr_local", provider="local", base_url="tesseract", model="chi_sim+eng",
        messages=msg, answer=(text or "(空)"),
        duration_ms=int((time.monotonic() - t0) * 1000), ok=True,
    )
    return text


def _run_tesseract(data: bytes) -> str:
    """Tesseract 主体调用（探测/校验/PIL 转 PNG/子进程），不含日志。"""
    import subprocess
    import tempfile

    exe = _find_tesseract()
    if not exe:
        raise RuntimeError(
            "已启用本地 OCR，但未检测到 Tesseract：请运行 `winget install UB-Mannheim.TesseractOCR` "
            "安装，并按 README「本地 OCR」补充中文语言数据 chi_sim 后再试。"
        )
    td = _find_tessdata(exe)
    if not td or not os.path.exists(os.path.join(td, "chi_sim.traineddata")):
        raise RuntimeError(
            "已启用本地 OCR，但缺少中文语言数据 chi_sim：请按 README「本地 OCR（安装方法 A）」"
            "下载 chi_sim.traineddata 到 tessdata 目录（或设置 TESSDATA_PREFIX）。"
        )
    tmp = tempfile.TemporaryDirectory(prefix="lantai_ocr_")
    try:
        # 统一转 PNG（tesseract 对常见格式均可，PIL 转换最稳）
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(data))
        png = os.path.join(tmp.name, "page.png")
        img.convert("RGB").save(png)
        cmd = [exe, png, "stdout", "-l", "chi_sim+eng", "--psm", "3", "--tessdata-dir", td]
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    finally:
        tmp.cleanup()
    if r.returncode != 0:
        raise RuntimeError(f"本地 OCR 失败（Tesseract 退出码 {r.returncode}）：{(r.stderr or '')[:200]}")
    return (r.stdout or "").strip()


def process_document(doc_id: int) -> None:
    """解析单个文档（后台任务调用，同步执行于线程池）。"""
    st = Store()
    doc = st.get_document(doc_id)
    if doc is None:
        return
    file_path = config.UPLOAD_DIR / str(doc_id) / doc["name"]
    if not file_path.exists():
        st.set_document_status(doc_id, "failed", f"源文件缺失：{doc['name']}")
        return
    try:
        text, final_category = _extract_text(doc, file_path, st)
        if final_category != doc["category"]:
            st.set_document_category(doc_id, final_category)
        if not text or not text.strip():
            raise RuntimeError("未能从文档中提取到可检索的文本内容。")
        chunks = chunker.chunk_text(text)
        if not chunks:
            raise RuntimeError("未能从文档中提取到可检索的文本内容。")
        # 0.1.47（CH-092/B）：同文档切片精确去重（保留首现）——防御 OCR 噪声/重复段放大
        seen: set[str] = set()
        chunks = [t for t in chunks if not (t in seen or seen.add(t))]
        if not chunks:
            raise RuntimeError("未能从文档中提取到可检索的文本内容。")
        from .schemas import AiItem

        emb_cfg = AiItem(**st.get_ai_config()["embedding"])
        emb = embeddings.embed_texts(emb_cfg, chunks)
        # 幂等（CH-058/M4）：重解析前清理旧切片，防崩溃恢复后同一文档切片重复入库
        st.clear_chunks(doc_id)
        count = st.add_chunks(doc_id, chunks, emb)
        st.set_document_status(doc_id, "ready", chunk_count=count)
    except Exception as exc:  # noqa: BLE001
        st.set_document_status(doc_id, "failed", str(exc))
