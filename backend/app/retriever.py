"""检索器：问题向量化 → 向量库 top-k 检索。

组合点（档位 3）：rerank 重排（R106）、hybrid BM25+向量 融合（R107）
均在此模块扩展，业务调用不变。
"""
from __future__ import annotations

from . import config, embeddings, store as store_mod


def retrieve(question: str, top_k: int = config.DEFAULT_TOP_K, st: store_mod.Store | None = None) -> list[dict]:
    """检索 top-k 切片（含相似度分数与文档信息）。"""
    from .schemas import AiItem

    st = st or store_mod.Store()
    cfg = st.get_ai_config()
    q_vec = embeddings.embed_query(AiItem(**cfg["embedding"]), question)
    return st.search(q_vec, top_k=min(top_k, config.MAX_TOP_K))


def build_context(sources: list[dict], max_chars: int = 6000) -> str:
    """把命中切片组装为模型上下文（按分数降序，截断到 max_chars）。"""
    parts = []
    used = 0
    for i, s in enumerate(sources, 1):
        text = s["chunk_text"].strip()
        if not text:
            continue
        if used + len(text) > max_chars:
            text = text[: max_chars - used]
        parts.append(f"[资料{i}]（来源：{s['doc_name']}，相似度 {s['score']}）\n{text}")
        used += len(text)
        if used >= max_chars:
            break
    return "\n\n".join(parts)
