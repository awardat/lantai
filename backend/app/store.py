"""SQLite 存储层：业务表 + 向量检索（numpy 暴力余弦）+ 配置键值 + API token。

VectorStore 为向量检索的抽象入口；替换向量库（ChromaDB/Milvus，R108）时
实现相同接口即可，业务代码不感知。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from . import config

# ---------------------------------------------------------------- 默认 AI 配置

_DEFAULT_CHAT_PROMPT = (
    "你是「兰台」知识库助手。请严格依据给定的参考资料回答用户问题；"
    "若参考资料中没有相关内容，请明确说明「无法从知识库中找到答案」，不要编造。"
    "回答使用中文，条理清晰。"
)
_DEFAULT_IMAGE_PROMPT = "请详细描述这张图片的内容，包括其中的文字与版式。"
_DEFAULT_OCR_PROMPT = "请识别图片中的全部文字，保持原文顺序；图片中没有文字则说明图片内容。"

DEFAULT_AI_CONFIG: dict[str, dict[str, Any]] = {
    "text": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "", "temperature": 0.2},
    "office": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "", "temperature": 0.2},
    "pdf_text": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "", "temperature": 0.2},
    "image": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "llava:7b", "prompt": _DEFAULT_IMAGE_PROMPT, "temperature": 0.2},
    "pdf_image": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "llava:7b", "prompt": _DEFAULT_OCR_PROMPT, "temperature": 0.2},
    "chat": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": _DEFAULT_CHAT_PROMPT, "temperature": 0.3},
    "embedding": {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "bge-m3", "prompt": "", "temperature": 0.0},
}

AI_CONFIG_KEYS = ("text", "office", "pdf_text", "image", "pdf_image", "chat", "embedding")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  ext TEXT NOT NULL,
  size INTEGER NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  text TEXT NOT NULL,
  char_count INTEGER NOT NULL,
  embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  prefix TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tokens_revoked ON api_tokens(revoked);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL DEFAULT '新对话',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """SQLite 存储（文档 / 切片 / 设置 / token）+ numpy 向量检索。"""

    def __init__(self, db_path: Path = config.DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            # 用 user_version 标记 schema 版本，避免每次实例化重复建表（L7）；
            # v2：新增 conversations / messages（对话历史，0.1.5）
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 2:
                conn.executescript(_SCHEMA)
                conn.execute("PRAGMA user_version=2")

    # ------------------------------------------------------------ 基础连接
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")  # N-L10：启用外键约束（与数据库设计文档一致）
        return conn

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            with self._connect() as conn:
                return conn.execute(sql, params).fetchall()

    def _execute(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.lastrowid

    # ------------------------------------------------------------ 文档
    def add_document(self, name: str, category: str, ext: str, size: int) -> int:
        return self._execute(
            "INSERT INTO documents (name, category, ext, size, status, created_at) VALUES (?,?,?,?,?,?)",
            (name, category, ext, size, "parsing", _now()),
        )

    def set_document_status(self, doc_id: int, status: str, error: Optional[str] = None, chunk_count: Optional[int] = None) -> None:
        sql = "UPDATE documents SET status=?, error=?"
        params: list = [status, error]
        if chunk_count is not None:
            sql += ", chunk_count=?"
            params.append(chunk_count)
        sql += " WHERE id=?"
        params.append(doc_id)
        with self._lock:
            with self._connect() as conn:
                conn.execute(sql, params)
                conn.commit()

    def set_document_category(self, doc_id: int, category: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("UPDATE documents SET category=? WHERE id=?", (category, doc_id))
                conn.commit()

    def get_document(self, doc_id: int) -> Optional[dict]:
        rows = self._query("SELECT * FROM documents WHERE id=?", (doc_id,))
        return dict(rows[0]) if rows else None

    def list_documents(self) -> list[dict]:
        rows = self._query("SELECT * FROM documents ORDER BY id DESC")
        return [dict(r) for r in rows]

    def list_pending_ids(self) -> list[int]:
        """排队/解析中的文档 ID（服务重启恢复解析队列用）。"""
        rows = self._query("SELECT id FROM documents WHERE status IN ('queued','parsing')")
        return [r["id"] for r in rows]

    def delete_document(self, doc_id: int) -> Optional[dict]:
        doc = self.get_document(doc_id)
        if doc is None:
            return None
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
                conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
                conn.commit()
        return doc

    # ------------------------------------------------------------ 切片与向量
    def add_chunks(self, doc_id: int, texts: list[str], embeddings: np.ndarray) -> int:
        """批量写入切片；embeddings 形状 (n, dim) float32。"""
        rows = [
            (doc_id, i, t, len(t), np.asarray(embeddings[i], dtype=np.float32).tobytes())
            for i, t in enumerate(texts)
        ]
        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT INTO chunks (document_id, seq, text, char_count, embedding) VALUES (?,?,?,?,?)",
                    rows,
                )
                conn.commit()
        return len(rows)

    def search(self, query_vec: np.ndarray, top_k: int = config.DEFAULT_TOP_K) -> list[dict]:
        """向量余弦检索（全表扫描 + numpy）。返回按分数降序的命中列表。"""
        rows = self._query(
            "SELECT c.id AS chunk_id, c.document_id, c.text, c.embedding, d.name AS doc_name, d.category "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status = 'ready' ORDER BY c.document_id, c.seq"
        )
        if not rows:
            return []
        # L9 修复：检测向量维度一致性，避免 np.vstack 维度不一时裸抛异常
        q_vec32 = np.asarray(query_vec, dtype=np.float32)
        q_dim = int(q_vec32.size)
        dims = {np.frombuffer(r["embedding"], dtype=np.float32).size for r in rows}
        if len(dims) > 1 or q_dim not in dims:
            raise RuntimeError(
                "检测到知识库切片向量维度不一致（可能更换过 embedding 模型）："
                "请删除旧文档后重新上传，或在设置中恢复原 embedding 模型。"
            )
        mat = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
        q = q_vec32.reshape(1, -1)
        # 余弦相似度
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat_n = mat / norms
        q_norm = np.linalg.norm(q)
        q_n = q / q_norm if q_norm > 0 else q
        scores = (mat_n @ q_n.T).flatten()
        k = min(top_k, len(rows))
        idx = np.argsort(-scores)[:k]
        out = []
        for i in idx:
            r = rows[i]
            out.append(
                {
                    "chunk_id": r["chunk_id"],
                    "doc_id": r["document_id"],
                    "doc_name": r["doc_name"],
                    "category": r["category"],
                    "chunk_text": r["text"],
                    "score": round(float(scores[i]), 4),
                }
            )
        return out

    # ------------------------------------------------------------ 配置键值
    def get_setting(self, key: str, default: Any = None) -> Any:
        rows = self._query("SELECT value FROM settings WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
                conn.commit()

    # ------------------------------------------------------------ AI 配置
    def get_ai_config(self) -> dict[str, dict[str, Any]]:
        """读取 AI 配置，与默认值合并（未配置项回退默认）；api_key 返回解密后的明文。

        S1 修复：所有调用路径（chat/retriever/pipeline）直接使用本方法返回值，
        故在此统一解密，避免各调用处遗漏。
        """
        from . import security  # 延迟导入，避免与 security 模块循环依赖

        raw = self.get_setting("ai_config")
        saved = json.loads(raw) if raw else {}
        out: dict[str, dict[str, Any]] = {}
        for key in AI_CONFIG_KEYS:
            item = dict(DEFAULT_AI_CONFIG[key])
            item.update(saved.get(key, {}))
            if item.get("api_key"):
                item["api_key"] = security.decrypt_api_key(item["api_key"])
            out[key] = item
        return out

    def save_ai_config(self, cfg: dict[str, dict[str, Any]]) -> None:
        """保存 AI 配置（M1 修复：与现有值合并，未提交的槽位保留原值）。"""
        current = self.get_ai_config()
        for key, value in cfg.items():
            if key in AI_CONFIG_KEYS:
                current[key] = value
        self.set_setting("ai_config", json.dumps(current, ensure_ascii=False))

    # ------------------------------------------------------------ API token
    def create_api_token(self, name: str, token_plain: str) -> int:
        import hashlib

        token_hash = hashlib.sha256(token_plain.encode("utf-8")).hexdigest()
        prefix = token_plain[:10] + "…"
        return self._execute(
            "INSERT INTO api_tokens (name, token_hash, prefix, created_at) VALUES (?,?,?,?)",
            (name, token_hash, prefix, _now()),
        )

    def list_api_tokens(self) -> list[dict]:
        rows = self._query("SELECT * FROM api_tokens ORDER BY id DESC")
        return [dict(r) for r in rows]

    def revoke_api_token(self, token_id: int) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("UPDATE api_tokens SET revoked=1 WHERE id=? AND revoked=0", (token_id,))
                conn.commit()
                return cur.rowcount > 0

    def validate_api_token(self, token_plain: str) -> bool:
        import hashlib

        token_hash = hashlib.sha256(token_plain.encode("utf-8")).hexdigest()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE api_tokens SET last_used_at=? WHERE token_hash=? AND revoked=0",
                    (_now(), token_hash),
                )
                conn.commit()
                return cur.rowcount > 0

    # ------------------------------------------------------------ 对话历史（0.1.5）
    def create_conversation(self, title: str = "新对话") -> int:
        now = _now()
        return self._execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?,?,?)",
            (title, now, now),
        )

    def list_conversations(self) -> list[dict]:
        rows = self._query("SELECT * FROM conversations ORDER BY updated_at DESC")
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: int) -> Optional[dict]:
        rows = self._query("SELECT * FROM conversations WHERE id=?", (conv_id,))
        return dict(rows[0]) if rows else None

    def delete_conversation(self, conv_id: int) -> bool:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
                cur = conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
                conn.commit()
                return cur.rowcount > 0

    def rename_conversation(self, conv_id: int, title: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
                conn.commit()
                return cur.rowcount > 0

    def add_message(self, conv_id: int, role: str, content: str) -> int:
        now = _now()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                    (conv_id, role, content, now),
                )
                conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
                conn.commit()
                return cur.lastrowid

    def list_messages(self, conv_id: int, limit: int = 200) -> list[dict]:
        rows = self._query(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id ASC LIMIT ?",
            (conv_id, limit),
        )
        return [dict(r) for r in rows]

    def recent_messages(self, conv_id: int, max_count: int = 6) -> list[dict]:
        """最近 max_count 条历史消息（升序），用于拼入问答上下文。"""
        rows = self._query(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
            (conv_id, max_count),
        )
        return [dict(r) for r in reversed(rows)]
