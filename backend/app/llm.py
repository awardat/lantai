"""LLM 问答调用：OpenAI 兼容 Chat Completions 协议（Ollama 走其 /v1 端点）。

参考 deepseek-harness-master packages/llm/llm-pi-ai：
- Provider 路由配置（base_url + api_key + model）由设置层注入，调用层无状态；
- 视觉输入走 OpenAI 兼容 content 数组（image_url + data URI）；
- 错误统一映射为中文提示（含解决建议）。
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional

import httpx

from . import config
from .schemas import AiItem


def normalize_base_url(base_url: str) -> str:
    """确保 base_url 以 /v1 结尾（Ollama 原生地址自动补 /v1）。"""
    base_url = (base_url or "").strip().rstrip("/")
    if base_url.endswith("/v1"):
        return base_url
    return base_url + "/v1"


def _headers(item: AiItem) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if item.api_key:
        headers["Authorization"] = f"Bearer {item.api_key}"
    return headers


def _friendly_error(exc: Exception, base_url: str) -> str:
    """把连接/鉴权/超时等异常映射为中文提示。"""
    if isinstance(exc, httpx.ConnectError):
        return (
            f"无法连接 AI 服务（{base_url}）：请确认 Ollama 已启动（托盘图标存在），"
            "或检查设置页 Base URL 是否正确。"
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"AI 服务响应超时（{base_url}）：请检查网络或稍后重试。"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        body = ""
        try:
            body = exc.response.text[:300]
        except Exception:
            pass
        if code == 401:
            return "AI 服务鉴权失败（401）：请检查 API Key 是否正确。"
        if code == 404:
            return "AI 服务接口不存在（404）：请检查 Base URL 是否以 /v1 结尾。"
        if code == 503:
            return (
                "AI 服务不可用（503）：本地 AI 服务未就绪或未启动（如 Ollama / OpenCode Go 代理），"
                "请确认服务已运行，或检查 Base URL 与网络。"
            )
        if "model" in body.lower() and ("not found" in body.lower() or "not exist" in body.lower()):
            return f"模型不存在：请先执行 ollama pull <模型名> 拉取模型，或修改模型配置。"
        return f"AI 服务返回错误（HTTP {code}）：{body[:200]}"
    return f"AI 调用失败：{exc}"


def chat(
    item: AiItem,
    messages: list[dict],
    images: Optional[list[tuple[bytes, str]]] = None,
    timeout: int = config.TIMEOUT_CHAT,
    slot: str = "",
    conv_id: Optional[int] = None,
    doc_id: Optional[int] = None,
) -> str:
    """调用 chat/completions。images 为 [(图片字节, MIME)] 列表（视觉输入）。

    智能体日志（0.1.10）：记录提示词、思维链（reasoning_content）、用量、耗时。
    """
    from . import agent_log

    base = normalize_base_url(item.base_url)
    payload: dict[str, Any] = {
        "model": item.model,
        "temperature": item.temperature,
        "stream": False,
    }
    if images:
        # 视觉输入：最后一条 user 消息携带图片
        parts: list[dict] = [{"type": "text", "text": messages[-1]["content"]}]
        for raw, mime in images:
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"}})
        msgs = messages[:-1] + [{"role": messages[-1]["role"], "content": parts}]
        payload["messages"] = msgs
    else:
        payload["messages"] = messages

    import time

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/chat/completions", json=payload, headers=_headers(item))
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]["message"]
        content = choice.get("content") or "（模型返回为空）"
        reasoning = choice.get("reasoning_content")
        usage = data.get("usage")
        agent_log.log_call(
            slot=slot, provider=item.provider, base_url=base, model=item.model,
            messages=messages, reasoning=reasoning, answer=content, usage=usage,
            duration_ms=int((time.monotonic() - t0) * 1000),
            conv_id=conv_id, doc_id=doc_id,
        )
        return content.strip()
    except Exception as exc:  # noqa: BLE001
        agent_log.log_call(
            slot=slot, provider=item.provider, base_url=base, model=item.model,
            messages=messages, ok=False, error=_friendly_error(exc, base),
            duration_ms=int((time.monotonic() - t0) * 1000),
            conv_id=conv_id, doc_id=doc_id,
        )
        raise RuntimeError(_friendly_error(exc, base)) from exc


def chat_stream(
    item: AiItem,
    messages: list[dict],
    timeout: int = config.TIMEOUT_CHAT,
    slot: str = "",
    conv_id: Optional[int] = None,
    doc_id: Optional[int] = None,
):
    """流式调用 chat/completions（stream=true），逐 delta 产出文本片段（生成器）。

    SSE 流：`data: {"choices":[{"delta":{"content": "..."}}]}`，结束为 `data: [DONE]`。
    智能体日志（0.1.10）：累积思维链（delta.reasoning_content）与答案，结束后记录。
    """
    from . import agent_log

    base = normalize_base_url(item.base_url)
    payload: dict[str, Any] = {
        "model": item.model,
        "temperature": item.temperature,
        "stream": True,
        "messages": messages,
    }
    import time

    t0 = time.monotonic()
    full_content: list[str] = []
    full_reasoning: list[str] = []
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{base}/chat/completions", json=payload, headers=_headers(item)) as resp:
                if resp.status_code != 200:
                    exc = httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                    raise exc
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                    except Exception:
                        continue
                    r = delta.get("reasoning_content")  # 思维链（如 DeepSeek-R1 系）
                    if r:
                        full_reasoning.append(r)
                    c = delta.get("content")
                    if c:
                        full_content.append(c)
                        yield c
        agent_log.log_call(
            slot=slot, provider=item.provider, base_url=base, model=item.model,
            messages=messages, reasoning="".join(full_reasoning), answer="".join(full_content),
            duration_ms=int((time.monotonic() - t0) * 1000),
            conv_id=conv_id, doc_id=doc_id, stream=True,
        )
    except Exception as exc:  # noqa: BLE001
        agent_log.log_call(
            slot=slot, provider=item.provider, base_url=base, model=item.model,
            messages=messages, reasoning="".join(full_reasoning), answer="".join(full_content),
            ok=False, error=_friendly_error(exc, base), duration_ms=int((time.monotonic() - t0) * 1000),
            conv_id=conv_id, doc_id=doc_id, stream=True,
        )
        raise RuntimeError(_friendly_error(exc, base)) from exc


def list_models(item: AiItem) -> list[str]:
    """测试连接：GET {base}/models，返回模型 ID 列表。"""
    base = normalize_base_url(item.base_url)
    try:
        with httpx.Client(timeout=config.TIMEOUT_MODELS) as client:
            resp = client.get(f"{base}/models", headers=_headers(item))
            resp.raise_for_status()
            data = resp.json()
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(_friendly_error(exc, base)) from exc


def rerank(item: AiItem, query: str, documents: list[str], top_n: int = 5) -> list[tuple[int, float]]:
    """交叉编码器重排（0.1.39 R106）：POST {base}/rerank（OpenAI 兼容协议，如通义
    qwen-rerank / 硅基流动 / 本地 Ollama rerank 模型）。

    返回 [(documents 索引, relevance_score)]，按 relevance_score 降序。
    失败抛 RuntimeError（中文提示）；调用方决定容错策略。
    0.1.41（CH-080）：成功/失败均写 agent_log（slot=rerank），重排可观测。
    """
    import time

    from . import agent_log

    base = normalize_base_url(item.base_url)
    t0 = time.monotonic()
    msg = [{"role": "user", "content": f"query={query}\n候选数={len(documents)} top_n={top_n}"}]
    try:
        with httpx.Client(timeout=config.TIMEOUT_CHAT) as client:
            resp = client.post(
                f"{base}/rerank",
                json={
                    "model": item.model,
                    "query": query,
                    "documents": documents,
                    "top_n": min(int(top_n or len(documents)), 100),
                },
                headers=_headers(item),
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        agent_log.log_call(
            slot="rerank", provider=item.provider, base_url=base, model=item.model,
            messages=msg, ok=False, error=_friendly_error(exc, base),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        raise RuntimeError(_friendly_error(exc, base)) from exc
    results = sorted(data.get("results", []), key=lambda r: -float(r.get("relevance_score", 0.0)))
    out = [(int(r["index"]), float(r.get("relevance_score", 0.0))) for r in results if "index" in r]
    agent_log.log_call(
        slot="rerank", provider=item.provider, base_url=base, model=item.model,
        messages=msg,
        answer="top" + "|".join(f"#{i}:{s:.3f}" for i, s in out[:10]),
        usage=data.get("usage"),
        duration_ms=int((time.monotonic() - t0) * 1000),
        ok=True,
    )
    return out
