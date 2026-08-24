# API 说明文档：兰台（lantai）本地 RAG 知识库

| 项目 | 内容 |
|------|------|
| 产品名称 | 兰台（lantai）本地 RAG 知识库 |
| 文档版本 | V1.20（对应应用 0.1.22） |
| 生成时间 | 2026-08-23 |
| 数据来源 | 技术对接方案.md、PRD产品需求文档.md（§6）、数据库设计文档.md |
| 适用范围 | 前端调用与外部程序集成（API token） |

---

## 一、通用约定

### 1.1 Base URL 与编码

- 本地默认地址：`http://127.0.0.1:8000`，所有接口前缀 `/api`。
- 请求/响应一律 JSON（UTF-8）；文件上传为 `multipart/form-data`。

### 1.2 统一响应格式

所有接口返回：`{"code": 0, "message": "ok", "data": <业务数据>}`。

| 字段 | 说明 |
|------|------|
| code | `0` 成功；非 0 时等于 HTTP 状态码 |
| message | 成功为 `ok`；失败为中文提示（含解决建议） |
| data | 业务数据（失败时为 `null`） |

### 1.3 鉴权方式（三种）

| 方式 | 适用接口 | 说明 |
|------|----------|------|
| 免登录 | 业务接口（文档、问答、检索、系统信息） | 单用户演示模式 |
| 会话 Cookie | 配置接口 | `POST /api/settings/verify` 校验密码后发放 `lantai_session`（HTTP-only，24h） |
| Bearer token | `POST /api/chat`（外部调用） | `Authorization: Bearer <token>`，token 在设置页生成；无效/已吊销返回 401 |

### 1.4 错误码速查

| HTTP | 含义 | 常见场景 |
|:---:|------|----------|
| 400 | 参数错误 | 问题为空、文件为空 |
| 401 | 未授权 | 配置密码错误、会话失效、token 无效 |
| 404 | 不存在 | 文档已删除、token 已吊销 |
| 413 | 文件过大 | 超过 20MB |
| 415 | 类型不支持 | 扩展名不在白名单 |
| 422 | 校验失败 | 新密码 <8 位、top_k 越界 |
| 429 | 限流 | 密码连续错 5 次，锁定 1 分钟 |
| 500 | 服务内部错误 | 未捕获异常（详见后端日志） |
| 502 | 上游 AI 失败 | Ollama 未启动、模型未拉取、Key 无效、超时 |

---

## 二、文档管理 API（免登录）

### 2.1 上传文档

`POST /api/docs/upload`（`multipart/form-data`，字段名 `file`）

| 参数 | 说明 |
|------|------|
| file | 文件；白名单：`.txt .md .pdf .docx .png .jpg .jpeg .webp .bmp .gif`；≤20MB |

**请求示例**：

```bash
curl -F "file=@./兰台简介.txt" http://127.0.0.1:8000/api/docs/upload
```

**响应示例**（上传成功即返回，解析为**队列异步任务**，0.1.18 起）：

```json
{
  "code": 0,
  "message": "上传成功，已加入解析队列。",
  "data": {
    "id": 1, "name": "兰台简介.txt", "category": "text", "ext": ".txt",
    "size": 548, "status": "queued", "error": null,
    "chunk_count": 0, "created_at": "2026-08-22 23:05:09"
  }
}
```

> **文档状态机（0.1.18 起）**：`queued`（排队中）→ `parsing`（解析中）→ `ready`（已就绪）／`failed`（失败，error 含原因）；服务重启自动恢复排队/解析中的文档重新入队。解析并发默认 10，可在设置「解析」调整（1~50，即时生效）。

**错误示例**：`415` `{"code":415,"message":"不支持的文件类型（.exe）。支持：txt / md / pdf / docx / 图片（png、jpg、jpeg、webp、bmp、gif）。","data":null}`

### 2.2 文档列表

`GET /api/docs` → `data` 为 DocumentOut 数组（按上传时间倒序）。

### 2.3 文档详情

`GET /api/docs/{doc_id}` → `data` 为单个 DocumentOut；不存在返回 404。

### 2.4 删除文档

`DELETE /api/docs/{doc_id}` → 级联删除全部切片与源文件；成功返回 `{"code":0,"message":"已删除文档：<名称>","data":null}`。

### 2.5 预览源文件（文本）

`GET /api/docs/{doc_id}/preview` → `data` 结构：

| 字段 | 说明 |
|------|------|
| type | `text`（txt/md/docx/pdf 渲染文本）或 `image`（图片类） |
| doc | DocumentOut |
| content | 渲染文本（image 类无此字段） |
| note | 可选说明（如扫描件 PDF 无文本层提示） |
| raw_url | image 类的源文件直出地址 |

**示例**：

```json
{
  "code": 0, "message": "ok",
  "data": {
    "type": "text",
    "doc": {"id": 1, "name": "兰台简介.txt", "category": "text", "ext": ".txt", "size": 548, "status": "ready", "error": null, "chunk_count": 3, "created_at": "2026-08-22 23:05:09"},
    "content": "兰台是本地运行的 RAG 知识库演示系统。\n\n兰台之名取自汉代皇家档案馆。……",
    "format": "plain"
  }
}
```

### 2.6 预览源文件（原始内容）

`GET /api/docs/{doc_id}/preview/raw` → 按 MIME 直出文件（图片 `image/png` 等，浏览器直接显示；其他类型可另存）。

---

## 三、问答与检索 API

### 3.1 问答（RAG）

`POST /api/chat`

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| question | string | 是 | 问题（1~2000 字） |
| top_k | int | 否 | 检索切片数，默认 5（1~20） |
| conversation_id | int | 否 | 会话 ID（0.1.5）：携带该会话最近 6 条消息作为上下文，回答后自动入库 |

**请求示例**（外部程序调用，携带 token）：

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer lt-xxxx…" \
  -d '{"question": "什么是兰台？", "top_k": 5}'
```

**响应示例**：

```json
{
  "code": 0, "message": "ok",
  "data": {
    "answer": "兰台是本地运行的 RAG 知识库演示系统……",
    "sources": [
      {
        "chunk_id": 12, "doc_id": 1, "doc_name": "兰台简介.txt",
        "category": "text", "chunk_text": "兰台是本地运行的 RAG 知识库演示系统。……",
        "score": 0.8731
      }
    ]
  }
}
```

`data.sources[]`：命中切片，按相似度降序；`score` 为余弦相似度（0~1，4 位小数）；前端可凭 `doc_id` 调预览接口。

**错误示例**（AI 未就绪）：`502` `{"code":502,"message":"AI 服务不可用（503）：本地 AI 服务未就绪或未启动（如 Ollama / OpenCode Go 代理），请确认服务已运行，或检查 Base URL 与网络。","data":null}`

### 3.2 流式问答（SSE，0.1.5 新增）

`POST /api/chat/stream` —— 请求体同 3.1（`question` / `top_k` / `conversation_id`）。

响应为 `text/event-stream`，事件格式（每行 `data: <json>`，空行分隔）：

| 事件类型 | 时机 | data 内容 |
|----------|------|-----------|
| `sources` | 检索完成后（首个事件） | `{"type":"sources","sources":[...]}` 命中切片列表 |
| `delta` | 生成过程中（多个） | `{"type":"delta","content":"<文本片段>"}` 逐字/逐片段 |
| `error` | 生成失败 | `{"type":"error","message":"<中文原因>"}` |
| `done` | 结束（最后事件） | `{"type":"done"}` |

**示例**：

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "什么是兰台？", "conversation_id": 1}'
```

```text
data: {"type": "sources", "sources": [{"chunk_id": 1, "doc_id": 1, "doc_name": "兰台简介.txt", "category": "text", "chunk_text": "…", "score": 0.8731}]}

data: {"type": "delta", "content": "兰"}

data: {"type": "delta", "content": "台是…"}

data: {"type": "done"}
```

### 3.3 对话历史（0.1.5 新增）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/conversations` | POST | body `{"title": "新对话"}` → 创建会话 |
| `/api/conversations` | GET | 会话列表（按更新时间倒序） |
| `/api/conversations/{id}/messages` | GET | 会话消息列表（role: user/assistant） |
| `/api/conversations/{id}` | DELETE | 删除会话（级联消息） |

### 3.4 仅检索（调试/演示）

`GET /api/search?q=<检索词>&top_k=<n>` → `data` 为 sources 数组（同 3.1，无 answer）。

---

## 四、配置 API（除注明外需会话 Cookie）

### 4.1 密码验证（免会话）

`POST /api/settings/verify`，body `{"password": "Admin#123"}`

- 成功：`{"code":0,"message":"验证通过.","data":null}`，响应头 `Set-Cookie: lantai_session=…; HttpOnly; SameSite=lax`；
- 密码错误：401 `配置密码错误。`；连续 5 次错误：429 `尝试次数过多，请 1 分钟后再试。`

### 4.2 读取 AI 配置

`GET /api/settings/ai` → `data` 为 7 组配置（API Key 脱敏，仅尾 4 位）：

```json
{
  "code": 0, "message": "ok",
  "data": {
    "text":       {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "", "temperature": 0.2},
    "office":     {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "", "temperature": 0.2},
    "pdf_text":   {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "", "temperature": 0.2},
    "image":      {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "llava:7b", "prompt": "请详细描述这张图片的内容，包括其中的文字与版式。", "temperature": 0.2},
    "pdf_image":  {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "llava:7b", "prompt": "请识别图片中的全部文字，保持原文顺序；图片中没有文字则说明图片内容。", "temperature": 0.2},
    "chat":       {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "qwen2.5:7b", "prompt": "你是「兰台」知识库助手。……", "temperature": 0.3},
    "embedding":  {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "bge-m3", "prompt": "", "temperature": 0.0}
  }
}
```

### 4.3 保存 AI 配置

`PUT /api/settings/ai`，body `{"items": {"<key>": {...}, ...}}`（key ∈ text/office/pdf_text/image/pdf_image/chat/embedding，可只提交部分）

| 字段 | 说明 |
|------|------|
| provider | `ollama` 或 `openai-compatible` |
| base_url | 如 `http://127.0.0.1:11434`；接口调用时自动补 `/v1` |
| api_key | 留空或 `****` 开头 = 保持不变；新值加密存储、返回脱敏 |
| model | 模型名（如 `qwen2.5:7b` / `llava:7b` / `bge-m3`） |
| prompt | 提示词；留空用默认 |
| temperature | 0~2 |

保存立即生效（后续解析与问答按新配置执行）。

### 4.4 测试连接

`POST /api/settings/ai/test`，body `{"key": "<槽位>", "config": {...}}` → 调用 `GET {base}/v1/models` 列出模型：

```json
{"code":0,"message":"连接成功，共 3 个模型。","data":{"models":["llava:7b","bge-m3","qwen2.5:7b"]}}
```

失败返回 502 中文原因（连接拒绝/401/404/超时等）。

### 4.5 修改密码

`POST /api/settings/password`，body `{"old_password": "...", "new_password": "..."}`（新密码 ≥8 位）

- 成功：清空全部会话（旧 Cookie 失效），需重新 `verify`；
- 旧密码错误：401；过短：422。

### 4.6 API Token 管理

| 接口 | 说明 |
|------|------|
| `GET /api/settings/tokens` | 列表（名称/前缀/创建时间/最后使用/吊销状态，无明文） |
| `POST /api/settings/tokens` | body `{"name": "<名称>"}` → 返回 `plaintext`（**仅此一次**，服务端只存 SHA-256 哈希） |
| `DELETE /api/settings/tokens/{token_id}` | 吊销，立即失效 |

**生成示例**：

```json
{
  "code": 0,
  "message": "Token 已生成，明文仅展示这一次，请立即复制保存。",
  "data": {
    "id": 1, "name": "演示脚本", "prefix": "lt-5jsc_TL…",
    "created_at": "2026-08-22 23:06:37", "last_used_at": null, "revoked": 0,
    "plaintext": "lt-5jsc_TLVqKkxvNZKJtpH3sV1f5dvigTBCchQDAw7YDw"
  }
}
```

### 4.7 系统信息（免会话）

`GET /api/settings/system/info`：

```json
{
  "code": 0, "message": "ok",
  "data": {"version": "0.1.22", "platform": "win32 / AMD64", "data_dir": "C:\\…\\data"}
}
```

### 4.7b 解析队列配置（需会话，V1.20 新增）

- `GET /api/settings/parse` → 当前并发数：`{"code":0,"message":"ok","data":{"concurrency":10}}`
- `PUT /api/settings/parse` → 请求体 `{"concurrency": 10}`（1~50 校验，即时生效）：动态调整解析队列 worker 数（重启 worker 生效新并发，排队任务不丢）

```bash
curl -X PUT http://127.0.0.1:8000/api/settings/parse \
  -H "Cookie: lantai_session=<会话>" -H "Content-Type: application/json" \
  -d '{"concurrency": 20}'
```

### 4.8 预置 AI 供应商目录（免会话，V1.2 新增）

`GET /api/settings/vendors` → 预置供应商列表（供配置界面下拉选择，自动填充 Base URL 与推荐模型）：

```json
{
  "code": 0, "message": "ok",
  "data": [
    {
      "id": "dashscope", "name": "阿里云通义千问（DashScope）",
      "provider": "openai-compatible",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "capabilities": ["chat", "vision", "embedding"],
      "models": {"chat": "qwen-plus", "vision": "qwen-vl-plus", "embedding": "text-embedding-v3"},
      "note": "国产；OpenAI 兼容模式，含视觉与 embedding"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| id / name | 供应商标识与展示名 |
| provider | 接入类型：`ollama` / `openai-compatible` |
| base_url | 预置地址（OpenAI 兼容，自动补 `/v1`） |
| capabilities | 能力：`chat` / `vision` / `embedding`（如 DeepSeek 仅 chat） |
| models | 各能力推荐模型（chat / vision / embedding） |
| note | 提示（国产标注、无 embedding 说明等） |

---

## 五、外部调用示例

### 5.1 curl（问答，带 token）

```bash
TOKEN="lt-xxxx…"
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question": "知识库中有哪些文档？"}'
```

### 5.2 Python（httpx）

```python
import httpx

TOKEN = "lt-xxxx…"  # 设置页生成
r = httpx.post(
    "http://127.0.0.1:8000/api/chat",
    json={"question": "什么是兰台？", "top_k": 5},
    headers={"Authorization": f"Bearer {TOKEN}"},
    timeout=120,
)
print(r.json()["data"]["answer"])
for s in r.json()["data"]["sources"]:
    print(s["doc_name"], s["score"])
```

### 5.3 Python（httpx，配置会话）

```python
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000") as c:
    c.post("/api/settings/verify", json={"password": "Admin#123"})
    cfg = c.get("/api/settings/ai").json()["data"]
    cfg["chat"]["model"] = "qwen2.5:14b"
    c.put("/api/settings/ai", json={"items": {"chat": cfg["chat"]}})
```

---

## 六、调用注意事项

1. **DeepSeek 官方 API 无 embedding 接口**：embedding 请配置 OpenAI/通义等支持 embeddings 的服务，或本地 Ollama `bge-m3`。
2. **base_url 自动补 `/v1`**：填 `http://127.0.0.1:11434` 或 `https://api.deepseek.com/v1` 均可。
3. **文档解析是异步的**：上传接口立即返回（status=parsing）；轮询 `GET /api/docs` 直到 `ready` 或 `failed` 即可用于问答。
4. **会话 Cookie 仅内存保存**：后端重启后需重新 `verify`。
5. **限流**：密码验证失败 5 次/分钟锁定（429），不影响业务接口。

---

**文档状态**: API 说明 V1.20（与应用 0.1.22 同步）
**生成时间**: 2026-08-23
**前置文档**: 技术对接方案.md、PRD产品需求文档.md、数据库设计文档.md
**变更规则**: 接口变更时本文件随版本同步更新（0.1.1 → 0.1.2 → …）
