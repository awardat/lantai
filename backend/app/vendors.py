"""预置 AI 供应商目录（参考 deepseek-harness-master llm-pi-ai 的模型目录模式）。

- 每个供应商预置 base_url 与推荐模型（**优先国产**）；
- capabilities 声明能力（chat / vision / embedding），供配置界面提示
  （如 DeepSeek、Kimi 无 embedding 接口）；
- 仅作为配置界面辅助数据，实际请求仍由用户保存的
  {provider, base_url, api_key, model} 决定（向后兼容，不改变存储结构）。
"""
from __future__ import annotations

VENDORS: list[dict] = [
    {
        "id": "ollama",
        "name": "Ollama（本地）",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "capabilities": ["chat", "vision", "embedding"],
        "models": {"chat": "qwen2.5:7b", "vision": "qwen2.5vl:7b", "embedding": "bge-m3"},
        "note": "本地运行、数据不出机；需先安装 Ollama（winget install Ollama.Ollama）并拉取模型",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek（深度求索）",
        "provider": "openai-compatible",
        "base_url": "https://api.deepseek.com/v1",
        "capabilities": ["chat"],
        "models": {"chat": "deepseek-v4-flash"},
        "note": "国产；官方 API 无 embedding 接口，向量化请用通义/硅基流动或本地 bge-m3",
    },
    {
        "id": "dashscope",
        "name": "阿里云通义千问（DashScope）",
        "provider": "openai-compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "capabilities": ["chat", "vision", "embedding"],
        "models": {"chat": "qwen-plus", "vision": "qwen-vl-plus", "embedding": "text-embedding-v3"},
        "note": "国产；OpenAI 兼容模式，含视觉与 embedding",
    },
    {
        "id": "zhipu",
        "name": "智谱 AI（GLM）",
        "provider": "openai-compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "capabilities": ["chat", "vision", "embedding"],
        "models": {"chat": "glm-4-plus", "vision": "glm-4v-plus", "embedding": "embedding-3"},
        "note": "国产；含视觉与 embedding",
    },
    {
        "id": "opencode-go",
        "name": "OpenCode Go（官方）",
        "provider": "openai-compatible",
        "base_url": "https://opencode.ai/zen/go/v1",
        "capabilities": ["chat"],
        "models": {"chat": "deepseek-v4-flash"},
        "note": "OpenCode Go/Zen 官方 OpenAI 兼容端点；需 OpenCode 账户 API Key（本地代理可自行改回 http://127.0.0.1:8787/v1）",
    },
    {
        "id": "moonshot",
        "name": "月之暗面（Kimi）",
        "provider": "openai-compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "capabilities": ["chat"],
        "models": {"chat": "moonshot-v1-8k"},
        "note": "国产；无 embedding 接口",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动（SiliconFlow）",
        "provider": "openai-compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "capabilities": ["chat", "vision", "embedding"],
        "models": {
            "chat": "Qwen/Qwen2.5-7B-Instruct",
            "vision": "Qwen/Qwen2.5-VL-7B-Instruct",
            "embedding": "BAAI/bge-m3",
        },
        "note": "国产；开源模型托管，含 embedding",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "provider": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "capabilities": ["chat", "vision", "embedding"],
        "models": {"chat": "gpt-4o", "vision": "gpt-4o", "embedding": "text-embedding-3-small"},
        "note": "国际服务，请自行评估合规要求",
    },
]
