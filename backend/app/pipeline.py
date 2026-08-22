"""解析管线：文件类型路由 → 文本提取 → 切块 → 向量化 → 入库。

- 文字文档 / Office / 文字 PDF：本地解析（无需 LLM）；
- 图片：调用该类型配置的视觉模型生成内容描述；
- 图片 PDF（扫描件）：逐页提取内嵌图片 → OCR 模型识别。
"""
from __future__ import annotations

from pathlib import Path

from . import chunker, config, embeddings, filetype, llm, store as store_mod
from .store import Store


def _vision_describe(cfg: dict, raw: bytes, mime: str, fallback_prompt: str) -> str:
    from .schemas import AiItem

    item = AiItem(**cfg)
    prompt = (cfg.get("prompt") or "").strip() or fallback_prompt
    return llm.chat(item, [{"role": "user", "content": prompt}], images=[(raw, mime)], timeout=config.TIMEOUT_VISION)


def _extract_text(doc: dict, file_path: Path, st: Store) -> tuple[str, str]:
    """返回 (文本, 最终分类)。"""
    category = doc["category"]
    if category == "text":
        return filetype.read_text_file(file_path), category
    if category == "office":
        return filetype.parse_docx(file_path), category
    if category == "pdf_text":
        pages = filetype.pdf_text_layers(file_path)
        text = "\n\n".join(p.strip() for p in pages if p and p.strip())
        if len(text.strip()) < config.PDF_TEXT_MIN_CHARS:
            # 文本层过少 → 判定为扫描件，走 OCR
            return _ocr_pdf(file_path, st), "pdf_image"
        return text, category
    if category == "image":
        cfg = st.get_ai_config()["image"]
        raw = file_path.read_bytes()
        mime = filetype.mime_of(doc["ext"])
        return _vision_describe(cfg, raw, mime, "请描述这张图片的内容。"), category
    if category == "pdf_image":
        return _ocr_pdf(file_path, st), category
    raise RuntimeError(f"不支持的文件类型：{doc.get('ext', '')}")


def _ocr_pdf(file_path: Path, st: Store) -> str:
    """扫描件 PDF：逐页提取图片 → OCR 模型识别。"""
    cfg = st.get_ai_config()["pdf_image"]
    images = filetype.pdf_extract_page_images(file_path)
    if not images:
        raise RuntimeError("未能从 PDF 中提取到页面图片，请确认文件内容为扫描图片。")
    parts = []
    for page_no, data, mime in images:
        text = _vision_describe(cfg, data, mime, "请识别图片中的全部文字，保持原文顺序。")
        parts.append(f"【第 {page_no} 页】\n{text}")
    return "\n\n".join(parts)


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
        from .schemas import AiItem

        emb_cfg = AiItem(**st.get_ai_config()["embedding"])
        emb = embeddings.embed_texts(emb_cfg, chunks)
        count = st.add_chunks(doc_id, chunks, emb)
        st.set_document_status(doc_id, "ready", chunk_count=count)
    except Exception as exc:  # noqa: BLE001
        st.set_document_status(doc_id, "failed", str(exc))
