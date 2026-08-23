"""智能体日志：记录每次 AI 调用的提示词 / 思维链（reasoning_content）/ 用量等。

- 独立日志文件：`data/logs/agent-<启动时间戳>.log`（JSON 行，UTF-8），保留最近 20 个；
- 与 `lantai-*.log`（应用/访问日志）分离：本 logger 不向 root 传播；
- 图片内容（base64）不入日志，替换为字节数占位。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from . import config

AGENT_LOGGER = logging.getLogger("lantai.agent")
ANSWER_TRUNCATE = 2000  # 答案记录截断长度（字符）
REASONING_TRUNCATE = 8000  # 思维链记录截断长度（字符）


def setup_agent_logging() -> None:
    """挂载 agent 日志文件 handler（lifespan 启动时调用；幂等）。"""
    if any(isinstance(h, logging.FileHandler) for h in AGENT_LOGGER.handlers):
        return
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # L5：带微秒，避免同秒重启覆盖
    fh = logging.FileHandler(config.LOGS_DIR / f"agent-{ts}.log", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))  # 纯 JSON 行，便于解析
    AGENT_LOGGER.addHandler(fh)
    AGENT_LOGGER.setLevel(logging.INFO)
    AGENT_LOGGER.propagate = False  # 不进入 lantai-*.log
    # 保留最近 20 个 agent 日志文件
    logs = sorted(config.LOGS_DIR.glob("agent-*.log"))
    for old in logs[:-20]:
        try:
            old.unlink()
        except OSError:
            pass


def _sanitize_messages(messages: Optional[list[dict]]) -> list[dict]:
    """图片内容替换为占位（base64 不入日志）。"""
    if not messages:
        return []
    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            parts: list[dict] = []
            for p in content:
                if p.get("type") == "image_url":
                    url = (p.get("image_url") or {}).get("url", "")
                    parts.append({"type": "image_url", "url": f"[图片数据 {len(url)} 字节，已省略]"})
                else:
                    parts.append(p)
            content = parts
        out.append({"role": m.get("role"), "content": content})
    return out


def log_call(
    slot: str,
    provider: str,
    base_url: str,
    model: str,
    messages: Optional[list[dict]] = None,
    reasoning: Optional[str] = None,
    answer: Optional[str] = None,
    usage: Optional[dict] = None,
    ok: bool = True,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
    conv_id: Optional[int] = None,
    doc_id: Optional[int] = None,
    stream: bool = False,
) -> None:
    """写一条智能体日志（JSON 行）。"""
    record: dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "slot": slot,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "conversation_id": conv_id,
        "doc_id": doc_id,
        "stream": stream,
        "messages": _sanitize_messages(messages),
        "reasoning": (reasoning or "")[:REASONING_TRUNCATE] or None,
        "answer": (answer or "")[:ANSWER_TRUNCATE] or None,
        "usage": usage,
        "ok": ok,
        "error": error,
        "duration_ms": duration_ms,
    }
    AGENT_LOGGER.info(json.dumps(record, ensure_ascii=False))
