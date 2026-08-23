"""对话历史 API（0.1.5）：会话创建/列表/删除/重命名、消息列表。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..schemas import ConversationCreate, ConversationOut, MessageOut, ok
from ..store import Store

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

store = Store()


class ConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


@router.post("")
def create_conversation(body: ConversationCreate):
    conv_id = store.create_conversation(body.title or "新对话")
    return ok(ConversationOut(**store.get_conversation(conv_id)).model_dump(), message="对话已创建。")


@router.get("")
def list_conversations():
    return ok([ConversationOut(**c).model_dump() for c in store.list_conversations()])


@router.put("/{conv_id}")
def rename_conversation(conv_id: int, body: ConversationRename):
    """会话重命名（N-L9）。"""
    if not store.rename_conversation(conv_id, body.title):
        raise HTTPException(status_code=404, detail="对话不存在或已被删除。")
    return ok(ConversationOut(**store.get_conversation(conv_id)).model_dump(), message="对话已重命名。")


@router.get("/{conv_id}/messages")
def list_messages(conv_id: int):
    if store.get_conversation(conv_id) is None:
        raise HTTPException(status_code=404, detail="对话不存在或已被删除。")
    return ok([MessageOut(**m).model_dump() for m in store.list_messages(conv_id)])


@router.delete("/{conv_id}")
def delete_conversation(conv_id: int):
    if not store.delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="对话不存在或已被删除。")
    return ok(None, message="对话已删除。")
