"""文档管理 API：上传 / 列表 / 详情 / 删除 / 预览。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config, filetype, pipeline, store as store_mod
from ..schemas import DocumentOut, ok
from ..store import Store

router = APIRouter(prefix="/api/docs", tags=["docs"])

store = Store()


def _doc_out(doc: dict) -> DocumentOut:
    return DocumentOut(**doc)


@router.post("/upload")
def upload_document(file: UploadFile = File(...), background: BackgroundTasks = BackgroundTasks()):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型（{ext or '无扩展名'}）。支持：txt / md / pdf / docx / 图片（png、jpg、jpeg、webp、bmp、gif）。",
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

    background.add_task(pipeline.process_document, doc_id)
    return ok(_doc_out(store.get_document(doc_id)).model_dump(), message="上传成功，正在解析…")


@router.get("")
def list_documents():
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
        content = filetype.parse_docx(file_path)
        return ok({"type": "text", "doc": _doc_out(doc).model_dump(), "content": content, "format": "plain"})
    if category in ("pdf_text", "pdf_image"):
        # 0.1.9：PDF 预览优先用浏览器原生查看器（iframe 加载源文件），文本提取作为降级
        pages = filetype.pdf_text_layers(file_path)
        page_texts = [t for t, _ok in pages]  # 几何排序后的页面文本
        rendered = "\n\n".join(f"【第 {i + 1} 页】\n{p.strip()}" for i, p in enumerate(page_texts) if p and p.strip())
        note = ""
        if category == "pdf_image" and not rendered:
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
    return FileResponse(file_path, media_type=media_type, filename=doc["name"])
