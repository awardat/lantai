"""文档管理 API：上传 / 列表 / 详情 / 删除 / 预览。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config, filetype, pipeline, store as store_mod
from ..schemas import DocumentOut, ok
from ..store import Store

router = APIRouter(prefix="/api/docs", tags=["docs"])

store = Store()

# 文件大类（0.1.37，CH-065）：重试时可按大类手工兜底（识别问题纠正）
RETRY_CATEGORIES = ("text", "office", "pdf_text", "pdf_image", "image")
CATEGORY_LABELS = {"text": "文本", "office": "Office 文档", "pdf_text": "文字 PDF", "pdf_image": "图片 PDF（OCR）", "image": "图片"}


def _doc_out(doc: dict) -> DocumentOut:
    return DocumentOut(**doc)


@router.post("/upload")
def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型（{ext or '无扩展名'}）。支持：{config.allowed_exts_label()}。",
        )
    data = file.file.read()  # def 端点：同步读取上传内容（FastAPI 线程池执行）
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.MAX_UPLOAD_MB}MB 限制，请压缩后重试。")
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空。")

    name = filetype.sanitize_filename(file.filename or "unnamed")
    category = filetype.classify_ext(ext)
    if category == "unknown":
        raise HTTPException(status_code=415, detail=f"不支持的文件类型：{ext}")

    doc_id = store.add_document(name=name, category=category, ext=ext, size=len(data))
    doc_dir = config.UPLOAD_DIR / str(doc_id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / name).write_bytes(data)

    # 0.1.18：入解析队列（并发受限），状态 queued → worker 置 parsing → ready/failed
    from .. import task_queue

    store.set_document_status(doc_id, "queued")
    task_queue.enqueue(doc_id)
    return ok(_doc_out(store.get_document(doc_id)).model_dump(), message="上传成功，已加入解析队列。")


@router.get("")
def list_documents(page: int | None = None, page_size: int | None = None, status: str | None = None):
    """文档列表（0.1.49，CH-094：可选分页，每页 20/50/100 默认 20；可选状态过滤）。

    不带分页参数 → 返回全量数组（兼容脚本/旧调用）；带 page 时 →
    data = {total, page, page_size, items, stats}（stats 为全量各状态计数）。
    """
    if page is not None:
        page_size = page_size or 20
        if page_size not in (20, 50, 100):
            raise HTTPException(status_code=400, detail="page_size 仅支持 20 / 50 / 100。")
        if page < 1:
            raise HTTPException(status_code=400, detail="page 从 1 开始。")
        if status and status not in ("ready", "queued", "parsing", "failed"):
            raise HTTPException(status_code=400, detail="status 仅支持 ready / queued / parsing / failed。")
        data = store.list_documents(page=page, size=page_size, status=status or None)
        data["items"] = [_doc_out(d).model_dump() for d in data["items"]]
        return ok(data)
    docs = [_doc_out(d).model_dump() for d in store.list_documents()]
    return ok(docs)


@router.get("/{doc_id}")
def get_document(doc_id: int):
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在或已被删除。")
    return ok(_doc_out(doc).model_dump())


@router.delete("/{doc_id}")
def delete_document(doc_id: int):
    doc = store.delete_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在或已被删除。")
    # 删除源文件目录（源文件随文档删除，预览随之失效）
    doc_dir = config.UPLOAD_DIR / str(doc_id)
    if doc_dir.exists():
        import shutil

        shutil.rmtree(doc_dir, ignore_errors=True)
    return ok(None, message=f"已删除文档：{doc['name']}")


@router.post("/{doc_id}/retry")
def retry_document(doc_id: int, payload: Optional[dict] = Body(default=None)):
    """失败文档重新提交解析（0.1.34 CH-060；0.1.35 CH-062 原子条件 UPDATE；
    0.1.36 CH-063 可选 ext 指定扩展名；0.1.37 CH-065 可选 category 指定文件大类兜底）。"""
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在或已被删除。")
    ext = None
    category = None
    raw_ext = None
    raw_cat = None
    if payload:
        raw_ext = payload.get("ext")
        raw_cat = payload.get("category")
        if raw_ext and raw_cat:
            raise HTTPException(status_code=400, detail="ext 与 category 不可同时指定，请只传其一。")
        if raw_ext:
            # 指定具体扩展名（0.1.36）：白名单校验，分类由扩展名推导
            ext = str(raw_ext).strip().lower()
            if not ext.startswith("."):
                ext = "." + ext
            if ext not in config.ALLOWED_EXTS:
                raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext}")
            category = filetype.classify_ext(ext)
        elif raw_cat:
            # 指定文件大类（0.1.37）：识别问题手工兜底，扩展名按大类联动
            category = str(raw_cat).strip().lower()
            if category not in RETRY_CATEGORIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的文件大类：{raw_cat}（可选：{' / '.join(RETRY_CATEGORIES)}）",
                )
            if category in ("pdf_text", "pdf_image"):
                ext = ".pdf"  # PDF 大类必须按 PDF 解析器走
            elif category == "image":
                ext = ".png"
            elif category == "text":
                ext = doc.get("ext") if doc.get("ext") in (".txt", ".md") else ".txt"
            # office：保持原扩展名（Office 内部细分由扩展名决定，伪装场景仍可用 ext 指定）
    if not store.retry_document(doc_id, ext=ext, category=category):
        raise HTTPException(status_code=400, detail="仅失败状态的文档可以重新解析。")
    from ..task_queue import enqueue

    enqueue(doc_id)
    # 提示按"用户指定的是什么"展示（大类联动出的 ext 不喧宾夺主）
    if raw_cat:
        message = f"已重新提交解析：{doc['name']}（按 {CATEGORY_LABELS[category]} 大类）"
    elif raw_ext:
        message = f"已重新提交解析：{doc['name']}（按 {ext} 类型）"
    else:
        message = f"已重新提交解析：{doc['name']}"
    return ok(None, message=message)


@router.post("/{doc_id}/reparse")
def reparse_document(doc_id: int):
    """文档级重新解析（0.1.45，CH-089/A）：任意非解析中文档清除既有切片后，
    按当前版本方法重新入队解析——版本升级（如 0.1.44 表格 NL）后升级老文档产物。
    与 retry 的区别：ready 状态也允许（retry 仅 failed），保留源文件与 doc_id。"""
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在或已被删除。")
    if doc["status"] == "parsing":
        raise HTTPException(status_code=400, detail="文档正在解析中，请稍后（解析完成后再重新解析）。")
    store.reparse_document(doc_id)
    from ..task_queue import enqueue

    enqueue(doc_id)
    return ok(_doc_out(store.get_document(doc_id)).model_dump(), message=f"已提交重新解析：{doc['name']}")


@router.get("/{doc_id}/preview")
def preview_document(doc_id: int):
    """Web 内预览：返回按类型渲染的文本内容（图片返回 raw 直出提示）。"""
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在或已被删除。")
    file_path = config.UPLOAD_DIR / str(doc_id) / doc["name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="源文件缺失，无法预览。")

    category = doc["category"]
    if category == "image":
        return ok({"type": "image", "doc": _doc_out(doc).model_dump(), "raw_url": f"/api/docs/{doc_id}/preview/raw"})

    if category == "text":
        content = filetype.read_text_file(file_path)
        return ok({"type": "text", "doc": _doc_out(doc).model_dump(), "content": content, "format": "plain"})
    if category == "office":
        # CH-058/H2：按扩展名分发预览（docx/doc/wps/xls/xlsx/pptx/ppt），
        # 不再硬编码 parse_docx（非 docx 预览会 500）
        content = filetype.parse_office(file_path, doc.get("ext", ""))
        note = ""
        if not content.strip():
            note = "（该格式暂无法提取文本（如 .ppt 老版二进制演示文稿），可下载源文件查看）"
        return ok({"type": "text", "doc": _doc_out(doc).model_dump(), "content": content, "format": "plain", "note": note})
    if category in ("pdf_text", "pdf_image"):
        # 0.1.9：PDF 预览优先用浏览器原生查看器（iframe 加载源文件），文本提取作为降级
        pages = filetype.pdf_text_layers(file_path)
        page_texts = [t for t, _ok in pages]  # 几何排序后的页面文本
        rendered = "\n\n".join(f"【第 {i + 1} 页】\n{p.strip()}" for i, p in enumerate(page_texts) if p and p.strip())
        note = ""
        if category == "pdf_image":
            if filetype.pdf_is_pseudo_text(file_path):
                note = "（检测到文本层但编码不可映射（内嵌字体缺 ToUnicode），复制粘贴为乱码；下方为浏览器原生渲染，内容经 OCR 识别后可检索）"
            elif not rendered:
                note = "（本 PDF 为扫描件，无文本层；下方为浏览器原生渲染的原始页面，OCR 结果可在知识库中检索）"
        return ok(
            {
                "type": "pdf",
                "doc": _doc_out(doc).model_dump(),
                "content": rendered,
                "raw_url": f"/api/docs/{doc_id}/preview/raw",
                "note": note,
            }
        )

    raise HTTPException(status_code=415, detail="该类型暂不支持预览。")


@router.get("/{doc_id}/preview/raw")
def preview_raw(doc_id: int):
    """源文件直出（图片原样展示；其他类型浏览器内打开或下载）。"""
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在或已被删除。")
    file_path = config.UPLOAD_DIR / str(doc_id) / doc["name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="源文件缺失，无法预览。")
    media_type = filetype.mime_of(doc["ext"])
    # 0.1.13：inline 内联显示（iframe/浏览器原生 PDF 查看器），不再触发下载
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=doc["name"],
        content_disposition_type="inline",
    )
