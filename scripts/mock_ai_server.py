"""开发自测用 Mock AI 服务（OpenAI 兼容，无需 Ollama/云端即可验证全链路）。

支持：
- GET  /v1/models                       → 模型列表（mock-chat / mock-embed）
- POST /v1/chat/completions             → 固定回复（stream=false 时整段返回；
                                           stream=true 时逐字 SSE，模拟流式）
- POST /v1/embeddings                   → 8 维固定向量

用法：python mock_ai_server.py [--port 18000]
自测：设置页把 chat / embedding 指向 http://127.0.0.1:18000，模型填 mock-chat / mock-embed。
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

EMBEDDING = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
DELAY = 0.02  # 流式逐字间隔（秒）


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静默
        pass

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {"id": "mock-chat", "object": "model", "owned_by": "lantai-mock"},
                        {"id": "mock-embed", "object": "model", "owned_by": "lantai-mock"},
                    ],
                }
            )
        else:
            self._send_json({"error": {"message": f"not found: {self.path}"}}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": {"message": "bad json"}}, 400)
            return

        if self.path.endswith("/embeddings"):
            texts = body.get("input", [])
            if isinstance(texts, str):
                texts = [texts]
            self._send_json({"object": "list", "data": [{"object": "embedding", "index": i, "embedding": EMBEDDING} for i in range(len(texts))]})
            return

        if self.path.endswith("/chat/completions"):
            messages = body.get("messages", [])
            last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            reply = f"（Mock 回复）已收到你的问题：「{last_user[:60]}」。这是兰台流式输出的模拟答案，用于开发自测。"
            reasoning = "（Mock 思维链）我正在分析问题，检索到的资料显示这是兰台知识库的自测场景，我将给出基于资料的模拟回答。"
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                # 思维链（reasoning_content）先于内容输出
                for ch in reasoning:
                    chunk = json.dumps({"choices": [{"index": 0, "delta": {"reasoning_content": ch}}]}, ensure_ascii=False)
                    self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(DELAY)
                for ch in reply:
                    chunk = json.dumps({"choices": [{"index": 0, "delta": {"content": ch}}]}, ensure_ascii=False)
                    self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(DELAY)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:
                self._send_json(
                    {
                        "id": "mock-completion",
                        "object": "chat.completion",
                        "choices": [{"index": 0, "message": {"role": "assistant", "reasoning_content": reasoning, "content": reply}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
                    }
                )
            return

        self._send_json({"error": {"message": f"not found: {self.path}"}}, 404)


def main() -> None:
    parser = argparse.ArgumentParser(description="兰台开发自测 Mock AI 服务")
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"Mock AI 服务启动：http://{args.host}:{args.port} （chat=mock-chat / embedding=mock-embed）")
    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
