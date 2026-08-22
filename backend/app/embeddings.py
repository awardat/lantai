"""Embedding 调用：OpenAI 兼容 embeddings 端点（Ollama 走 /v1）。

注意：DeepSeek 官方 API 无 embeddings 接口；云端请选 OpenAI/通义等支持
embeddings 的服务，或 embedding 使用本地 Ollama（如 bge-m3）。
"""
from __future__ import annotations

import httpx
import numpy as np

from . import config
from .llm import _friendly_error, normalize_base_url
from .schemas import AiItem

_BATCH = 16


def embed_texts(item: AiItem, texts: list[str]) -> np.ndarray:
    """批量向量化，返回 (n, dim) float32 矩阵。"""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    base = normalize_base_url(item.base_url)
    headers = {"Content-Type": "application/json"}
    if item.api_key:
        headers["Authorization"] = f"Bearer {item.api_key}"
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=config.TIMEOUT_EMBED) as client:
            for i in range(0, len(texts), _BATCH):
                batch = texts[i : i + _BATCH]
                resp = client.post(
                    f"{base}/embeddings",
                    json={"model": item.model, "input": batch},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                vectors.extend(d["embedding"] for d in data["data"])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(_friendly_error(exc, base)) from exc
    return np.asarray(vectors, dtype=np.float32)


def embed_query(item: AiItem, text: str) -> np.ndarray:
    """单条问题向量化，返回 (dim,) float32。"""
    mat = embed_texts(item, [text])
    return mat[0]
