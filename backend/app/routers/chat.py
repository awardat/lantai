"""问答与检索 API：POST /api/chat（问答+引用）、GET /api/search（仅检索）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .. import llm, retriever, security, store as store_mod
from ..schemas import AiItem, ChatRequest, ChatResponse, Source, ok
from ..store import Store

router = APIRouter(prefix="/api", tags=["chat"])

store = Store()


def _check_bearer(request: Request) -> None:
    """外部调用鉴权：带 Authorization: Bearer 时校验 API token（无效则拒绝）。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if not store.validate_api_token(token):
            raise HTTPException(status_code=401, detail="API token 无效或已吊销，请在设置页重新生成。")


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    _check_bearer(request)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空。")

    try:
        sources = retriever.retrieve(question, top_k=body.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not sources:
        return ok(
            ChatResponse(
                answer="知识库中未检索到与问题相关的内容。请换一种问法，或先在「文档管理」中上传相关文档。",
                sources=[],
            ).model_dump()
        )

    context = retriever.build_context(sources)
    cfg = store.get_ai_config()["chat"]
    item = AiItem(**cfg)
    system_prompt = (cfg.get("prompt") or "").strip()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": f"以下是知识库检索到的参考资料：\n\n{context}\n\n请根据以上资料回答问题：{question}",
        }
    )
    try:
        answer = llm.chat(item, messages)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ok(
        ChatResponse(
            answer=answer,
            sources=[Source(**s).model_dump() for s in sources],
        ).model_dump()
    )


@router.get("/search")
async def search(q: str, top_k: int = 5):
    """仅检索不生成（调试 / 演示用）。"""
    q = (q or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="检索词不能为空。")
    try:
        sources = retriever.retrieve(q, top_k=top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ok([Source(**s).model_dump() for s in sources])
