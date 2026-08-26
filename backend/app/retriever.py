"""检索器：问题向量化 → 向量库 top-k 检索（0.1.39 起 hybrid + rerank + 降级）。

流水线（对外接口 retrieve() 不变，业务调用无感）：
1. 向量召回 top-K（embedding 故障时自动降级 BM25 关键词检索）；
2. BM25 召回 top-K（FTS5 + 中文 bigram）；
3. RRF（倒数排名融合）合并两路候选 → top-k（R107）；
4. rerank（R106，设置页「重排」开启时）：交叉编码器精排 → top-k。
"""
from __future__ import annotations

import logging

from . import config, embeddings, store as store_mod

log = logging.getLogger("lantai")

RRF_K = 60          # RRF 常数
RECALL_TOP = 20     # 融合候选规模（向量/BM25 各取前 RECALL_TOP，再融合取 top_k）


def _rerank_results(cfg: dict, question: str, sources: list[dict], top_k: int) -> list[dict]:
    """交叉编码器重排候选（R106）。重排失败时容错回退原排序（不阻塞问答）。"""
    from .llm import rerank
    from .schemas import AiItem

    docs = [s["chunk_text"] for s in sources]
    try:
        pairs = rerank(AiItem(**cfg), question, docs, top_n=min(len(docs), 20))
    except Exception as exc:  # noqa: BLE001 重排服务不可用 → 回退向量/融合结果
        log.warning("rerank 调用失败，回退原排序：%s", exc)
        return sources[:top_k]
    out: list[dict] = []
    for idx, score in pairs:
        if idx >= len(sources):
            continue
        s = dict(sources[idx])
        s["score"] = round(float(score), 4)
        out.append(s)
        if len(out) >= top_k:
            break
    return out


def retrieve(question: str, top_k: int = config.DEFAULT_TOP_K, st: store_mod.Store | None = None) -> list[dict]:
    """检索 top-k 切片（含相似度分数与文档信息）。

    混合检索（R107）：向量 + BM25 两路召回经 RRF 融合；embedding 故障时静默降级
    为 BM25 关键词检索（零 AI 依赖兜底）；「重排」开启时（R106）再做交叉编码器精排。
    """
    from .schemas import AiItem

    st = st or store_mod.Store()
    cfg = st.get_ai_config()
    k = min(top_k, config.MAX_TOP_K)

    # 1. 向量召回（embedding 故障 → 空列表，走 BM25 兜底；维度不一致等
    #    存储层问题不降级——保留"删除旧文档重新上传"的中文自救指引，CH-076/L1）
    vec: list[dict] = []
    q_vec = None
    try:
        q_vec = embeddings.embed_query(AiItem(**cfg["embedding"]), question)
    except Exception as exc:  # noqa: BLE001 降级：AI embedding 不可用
        log.warning("embedding 不可用，降级 BM25 关键词检索：%s", exc)
    if q_vec is not None:
        vec = st.search(q_vec, top_k=max(k, RECALL_TOP))  # RuntimeError（如维度不一致）上抛，不吞

    # 2. BM25 召回
    bm = st.keyword_search(question, top_k=max(k, RECALL_TOP))

    # 3. RRF 融合（单路为空时 RRF 退化为该路排序）
    sources = _rrf_fuse(vec, bm, k)

    # 4. rerank 精排（R106，设置页开启时）
    rcfg = cfg.get("rerank") or {}
    if sources and rcfg.get("enabled") and (rcfg.get("model") or "").strip():
        sources = _rerank_results(rcfg, question, sources, k)
    return sources


def _rrf_fuse(vec: list[dict], bm: list[dict], top_k: int) -> list[dict]:
    """RRF（Reciprocal Rank Fusion）：按排名倒数加分融合两路候选，无需调权重。"""
    if not vec:
        return bm[:top_k]
    if not bm:
        return vec[:top_k]
    fused: dict[int, list] = {}

    def add(items: list[dict]) -> None:
        for rank, s in enumerate(items):
            entry = fused.get(s["chunk_id"])
            if entry is None:
                fused[s["chunk_id"]] = [1.0 / (RRF_K + rank + 1), s]
            else:
                entry[0] += 1.0 / (RRF_K + rank + 1)

    add(vec)
    add(bm)
    ordered = sorted(fused.items(), key=lambda kv: -kv[1][0])
    return [s for _, (_, s) in ordered[:top_k]]


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