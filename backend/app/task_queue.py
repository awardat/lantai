"""解析任务队列（0.1.18）：FIFO 队列 + 固定并发 worker（默认 10，设置可调）。

- 上传的文档先入队（status=queued），worker 取出后置 parsing 并执行解析；
- 并发数可在设置页调整（1~50）：增加即时启动新 worker，减少通过 None 哨兵优雅退出；
- 单机内存队列（演示级）；服务重启时 lifespan 将 queued/parsing 文档重新入队恢复。
"""
from __future__ import annotations

import queue
import threading

from .store import Store

_QUEUE: queue.Queue = queue.Queue()
_WORKERS: list[threading.Thread] = []
_LOCK = threading.Lock()
DEFAULT_CONCURRENCY = 10
MAX_CONCURRENCY = 50


def concurrency() -> int:
    try:
        val = int(Store().get_setting("parse_concurrency", DEFAULT_CONCURRENCY))
    except (TypeError, ValueError):
        val = DEFAULT_CONCURRENCY
    return max(1, min(MAX_CONCURRENCY, val))


def _worker() -> None:
    while True:
        doc_id = _QUEUE.get()
        if doc_id is None:  # 退出哨兵（并发下调）
            _QUEUE.task_done()
            break
        try:
            store = Store()
            store.set_document_status(doc_id, "parsing")
            from . import pipeline  # 延迟导入避免循环

            pipeline.process_document(doc_id)
        except Exception:  # noqa: BLE001  worker 兜底，解析异常已在 pipeline 内处理
            pass
        finally:
            _QUEUE.task_done()


def ensure_workers() -> None:
    """按当前配置并发数补齐 worker（启动/调整后调用）。"""
    target = concurrency()
    with _LOCK:
        while len(_WORKERS) < target:
            t = threading.Thread(target=_worker, name=f"parse-worker-{len(_WORKERS)}", daemon=True)
            _WORKERS.append(t)
            t.start()


def set_concurrency(n: int) -> int:
    """动态调整并发数：增加补 worker；减少投入退出哨兵。返回实际并发。"""
    n = max(1, min(MAX_CONCURRENCY, int(n)))
    with _LOCK:
        cur = len(_WORKERS)
        if n > cur:
            for _ in range(n - cur):
                t = threading.Thread(target=_worker, name=f"parse-worker-{len(_WORKERS)}", daemon=True)
                _WORKERS.append(t)
                t.start()
        elif n < cur:
            for _ in range(cur - n):
                _QUEUE.put(None)
    return n


def enqueue(doc_id: int) -> None:
    _QUEUE.put(doc_id)


def stats() -> dict:
    """队列统计：运行中（parsing）/ 排队中（queued）。"""
    store = Store()
    rows = store._query("SELECT status, COUNT(*) AS c FROM documents WHERE status IN ('queued','parsing') GROUP BY status")
    parsing = queued = 0
    for r in rows:
        if r["status"] == "parsing":
            parsing = r["c"]
        elif r["status"] == "queued":
            queued = r["c"]
    return {"concurrency": concurrency(), "parsing": parsing, "queued": queued}


def requeue_pending() -> int:
    """启动恢复：将 queued/parsing 状态的文档重新入队（服务重启场景）。返回恢复数。"""
    doc_ids = Store().list_pending_ids()
    for doc_id in doc_ids:
        _QUEUE.put(doc_id)
    return len(doc_ids)
