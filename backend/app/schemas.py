"""pydantic 数据模型（请求 / 响应）。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    name: str
    category: str
    ext: str
    size: int
    status: str
    error: Optional[str] = None
    chunk_count: int = 0
    created_at: str


class Source(BaseModel):
    chunk_id: int
    doc_id: int
    doc_name: str
    category: str
    chunk_text: str
    score: float


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source] = []


class AiItem(BaseModel):
    provider: str = "ollama"  # ollama | openai-compatible
    base_url: str = "http://127.0.0.1:11434"
    api_key: str = ""  # 保存时为空=保持不变
    model: str = ""
    prompt: str = ""
    temperature: float = 0.2


class AiConfigPut(BaseModel):
    items: dict[str, AiItem]


class TestRequest(BaseModel):
    key: str = ""  # 配置槽位（text/office/pdf_text/image/pdf_image/chat/embedding）
    config: AiItem


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyRequest(BaseModel):
    password: str


class TokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class TokenOut(BaseModel):
    id: int
    name: str
    prefix: str
    created_at: str
    last_used_at: Optional[str] = None
    revoked: int = 0


class TokenCreated(TokenOut):
    plaintext: str


class SystemInfo(BaseModel):
    version: str
    platform: str
    data_dir: str


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


def ok(data: Any = None, message: str = "ok") -> ApiResponse:
    return ApiResponse(code=0, message=message, data=data)
