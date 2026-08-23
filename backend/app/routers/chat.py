"""问答与检索 API：POST /api/chat（非流式）、POST /api/chat/stream（SSE 流式）、GET /api/search。

0.1.5（档位 3）：流式输出（SSE）+ 对话历史（conversation_id 携带上下文，回答后入库）。
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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


def _history_messages(conv_id: Optional[int], max_count: int = 6) -> list[dict]:
    """读取会话最近历史消息，转为 OpenAI 消息格式（不含本轮问题）。"""
    if not conv_id:
        return []
    if store.get_conversation(conv_id) is None:
        raise HTTPException(status_code=404, detail="对话不存在或已被删除。")
    return [{"role": m["role"], "content": m["content"]} for m in store.recent_messages(conv_id, max_count)]


def _build_messages(question: str, context: str, conv_id: Optional[int]) -> list[dict]:
    cfg = store.get_ai_config()["chat"]
    system_prompt = (cfg.get("prompt") or "").strip()
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(_history_messages(conv_id))
    user_content = f"以下是知识库检索到的参考资料：\n\n{context}\n\n请根据以上资料回答问题：{question}"
    messages.append({"role": "user", "content": user_content})
    return messages


def _do_retrieve(question: str, top_k: int) -> list[dict]:
    try:
        return retriever.retrieve(question, top_k=top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/chat")
def chat(body: ChatRequest, request: Request):
    _check_bearer(request)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空。")

    sources = _do_retrieve(question, body.top_k)
    if not sources:
        answer = "知识库中未检索到与问题相关的内容。请换一种问法，或先在「文档管理」中上传相关文档。"
        if body.conversation_id:
            store.add_message(body.conversation_id, "user", question)
            store.add_message(body.conversation_id, "assistant", answer)
        return ok(ChatResponse(answer=answer, sources=[]).model_dump())

    context = retriever.build_context(sources)
    messages = _build_messages(question, context, body.conversation_id)
    cfg = store.get_ai_config()["chat"]
    try:
        answer = llm.chat(AiItem(**cfg), messages)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if body.conversation_id:
        store.add_message(body.conversation_id, "user", question)
        store.add_message(body.conversation_id, "assistant", answer)
    return ok(ChatResponse(answer=answer, sources=[Source(**s).model_dump() for s in sources]).model_dump())


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, request: Request):
    """SSE 流式问答：先发 sources 事件，再逐 delta 输出，最后 done；错误发 error 事件。

    事件格式（每行 `data: <json>`）：
      {"type":"sources","sources":[...]} → {"type":"delta","content":"..."}* → {"type":"done"}
      {"type":"error","message":"..."}
    """
    _check_bearer(request)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空。")

    sources = _do_retrieve(question, body.top_k)

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def gen():
        if not sources:
            answer = "知识库中未检索到与问题相关的内容。请换一种问法，或先在「文档管理」中上传相关文档。"
            if body.conversation_id:
                store.add_message(body.conversation_id, "user", question)
                store.add_message(body.conversation_id, "assistant", answer)
            yield _sse({"type": "sources", "sources": []})
            yield _sse({"type": "delta", "content": answer})
            yield _sse({"type": "done"})
            return

        yield _sse({"type": "sources", "sources": [Source(**s).model_dump() for s in sources]})
        context = retriever.build_context(sources)
        messages = _build_messages(question, context, body.conversation_id)
        cfg = store.get_ai_config()["chat"]
        try:
            answer_parts: list[str] = []
            for delta in llm.chat_stream(AiItem(**cfg), messages):
                answer_parts.append(delta)
                yield _sse({"type": "delta", "content": delta})
        except RuntimeError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"type": "done"})
            return
        answer = "".join(answer_parts)
        if body.conversation_id:
            store.add_message(body.conversation_id, "user", question)
            store.add_message(body.conversation_id, "assistant", answer)
        yield _sse({"type": "done"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/search")
def search(q: str, top_k: int = 5):
    """仅检索不生成（调试 / 演示用）。"""
    q = (q or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="检索词不能为空。")
    sources = _do_retrieve(q, top_k)
    return ok([Source(**s).model_dump() for s in sources])
