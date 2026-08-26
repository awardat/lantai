"""Dify 外部知识库 API 适配（0.1.38，CH-071）。

协议（Dify External Knowledge API）：
- `POST {注册端点}/retrieval`，`Authorization: Bearer <API Key>`（兰台侧 = 设置页生成的 API token）
- 请求：{knowledge_id, query, retrieval_setting:{top_k, score_threshold}, metadata_condition?}
- 响应：{"records": [{"content", "score", "title", "metadata"}]}；metadata 必须为对象（非 null）

当前实现（按"改动最小"）：knowledge_id 暂不细分（检索全部就绪文档），
metadata_condition 暂不处理；鉴权强制 Bearer token。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request

from .. import retriever
from ..store import Store

router = APIRouter(prefix="/api/external", tags=["external"])

store = Store()


def _require_bearer(request: Request) -> None:
    """强制 Bearer token 鉴权（Dify 侧 API Key 填兰台设置页生成的 API token）。"""
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token or not store.validate_api_token(token):
        raise HTTPException(status_code=401, detail="API token 无效或已吊销，请在设置页重新生成。")


@router.post("/retrieval")
def retrieval(request: Request, payload: Optional[dict] = Body(default=None)):
    """Dify 外部知识库检索入口：知识库向量检索 → Dify records 格式。"""
    _require_bearer(request)
    if not payload:
        raise HTTPException(status_code=400, detail="请求体不能为空。")
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询词不能为空。")
    rs = payload.get("retrieval_setting") or {}
    try:
        top_k = int(rs.get("top_k") or 5)
        threshold = float(rs.get("score_threshold") or 0.0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="retrieval_setting 格式错误（top_k 需整数，score_threshold 需数字 0~1）。") from None
    if top_k < 1 or top_k > 100:
        raise HTTPException(status_code=400, detail="top_k 需在 1~100 之间。")

    try:
        sources = retriever.retrieve(query, top_k=top_k)
    except RuntimeError as exc:
        # 检索故障（如 embedding 服务不可用）：非 200 让 Dify 侧可见错误
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    records = [
        {
            "content": s["chunk_text"],
            "score": float(s["score"]),
            "title": s["doc_name"],
            "metadata": {"doc_id": s["doc_id"], "category": s.get("category", "")},
        }
        for s in sources
        if s["score"] >= threshold
    ]
    return {"records": records}