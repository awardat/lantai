# API 说明文档：兰台（lantai）本地 RAG 知识库

| 项目 | 内容 |
|------|------|
| 产品名称 | 兰台（lantai）本地 RAG 知识库 |
| 文档版本 | V1.47（对应应用 0.1.49） |
| 生成时间 | 2026-08-23 |
| 数据来源 | 技术对接方案.md、PRD产品需求文档.md（§6）、数据库设计文档.md |
| 适用范围 | 前端调用与外部程序集成（API token） |

---

## 一、通用约定

### 1.1 Base URL 与编码

- 本地默认地址：`http://127.0.0.1:8000`，所有接口前缀 `/api`。
- **外部调用地址**：服务默认仅监听本机回环 `127.0.0.1:8000`（不对外网开放）；如需局域网/远程调用，以 `lantai.exe --host 0.0.0.0`（源码 `python run.py --host 0.0.0.0`）启动，外部地址为 `http://<服务机IP>:8000`，接口前缀同上。演示级产品 HTTP 无 TLS，远程使用建议置于内网或反向代理后。
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
| 会话（**双通道，0.1.25**） | 配置接口 | `POST /api/settings/verify` 校验密码后：① 响应体返回 `data.session`（明文仅此一次）+ ② 设置 `lantai_session` Cookie（HTTP-only，24h，浏览器直开用）。**调用方任选其一**：`X-Lantai-Session: <token>` 请求头（桌面壳 iframe 场景，localStorage 存储）或 Cookie（浏览器直开） |
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
| file | 文件；白名单（0.1.30 扩展）：`.txt .md .pdf .docx .doc .wps .xls .xlsx .ppt .pptx .png .jpg .jpeg .webp .bmp .gif`；≤20MB |

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

**错误示例**：`415` `{"code":415,"message":"不支持的文件类型（.exe）。支持：doc / docx / md / pdf / ppt / pptx / txt / wps / xls / xlsx / 图片（bmp、gif、jpeg、jpg、png、webp）。","data":null}`（0.1.35 起文案由 `ALLOWED_EXTS` 动态生成，此处示例与代码输出一致）

### 2.2 文档列表

`GET /api/docs` → 不带分页参数时 `data` 为 DocumentOut 数组（按上传时间倒序，兼容脚本/轮询）。

**可选分页（V1.47 新增，0.1.49，CH-094）**：`GET /api/docs?page=1&page_size=20&status=` →

- `page_size` ∈ `{20,50,100}`（默认 20），非法 400 `page_size 仅支持 20 / 50 / 100。`
- `status` ∈ `ready/queued/parsing/failed`（可空=全部），非法 400
- `data` = `{"total": 总数, "page": 页码, "page_size": 每页条数, "items": [DocumentOut...], "stats": {"ready":n,"queued":n,"parsing":n,"failed":n}}`（stats 为**全量**各状态计数，供前端筛选按钮显示；total/items 按 status 过滤后分页）

### 2.3 文档详情

`GET /api/docs/{doc_id}` → `data` 为单个 DocumentOut；不存在返回 404。

### 2.4 删除文档

`DELETE /api/docs/{doc_id}` → 级联删除全部切片与源文件；成功返回 `{"code":0,"message":"已删除文档：<名称>","data":null}`。

### 2.4b 失败文档重试（V1.32 新增；V1.34 补手动指定类型；V1.35 补文件大类）

`POST /api/docs/{doc_id}/retry` → 仅 `failed` 状态可重试：置 `queued` 重新入队解析；非失败返回 400 `仅失败状态的文档可以重新解析。`；不存在返回 404。0.1.35 起"校验+置 queued"合并为 store 层原子条件 UPDATE（`WHERE status='failed'`），并发重试不会双次入队。

**可选 body（二选一，同时传返回 400 `ext 与 category 不可同时指定，请只传其一。`）**：

| 字段 | 说明 | 示例 |
|------|------|------|
| `ext` | 指定具体扩展名（0.1.36，伪装扩展名纠正）：白名单内自动更新扩展名与分类后按新类型解析；白名单外 400 `不支持的文件类型：<ext>` | `{"ext":".docx"}` |
| `category` | 指定文件大类（0.1.37，识别问题手工兜底）：枚举 `text / office / pdf_text / pdf_image / image`，非法值 400 `不支持的文件大类：<值>（可选：text / office / pdf_text / pdf_image / image）`；**大类联动扩展名**——pdf_text/pdf_image→`.pdf`、image→`.png`、text→`.txt`（已是 txt/md 保持）、office→保持原扩展名 | `{"category":"pdf_image"}` |

### 2.4e 文档重新解析（V1.43 新增，0.1.45，CH-089/A）

`POST /api/docs/{doc_id}/reparse` → 任意**非解析中**状态的文档（含 `ready`）清除既有切片后按当前版本方法重新入队解析（版本升级后按新方法重造产物，源文件与 doc_id 不变，不产生重复文档）：`parsing` 状态返回 400 `文档正在解析中，请稍后（解析完成后再重新解析）。`；不存在返回 404；成功返回 `data` 为最新文档对象、`message` 提示已提交重新解析。全库批量用法：`python scripts/reparse_all.py`（遍历 ready/failed 逐个调用；`--host`/`--ids` 可指定）。

不传 body → 按原类型重试（行为不变）。示例：扫描件被误判为文字 PDF → 解析失败 → `POST /api/docs/{id}/retry {"category":"pdf_image"}` → 按 OCR 通道重新解析。

### 2.4c Dify 外部知识库检索（V1.36 新增，0.1.38，CH-071）

> 实现 [Dify External Knowledge API](https://docs.dify.ai/zh/self-host/use-dify/knowledge/external-knowledge-api) 协议，供 Dify 以外部知识库方式调用兰台检索。

`POST /api/external/retrieval`，`Authorization: Bearer <API token>`（兰台设置页生成的 API token；无效/吊销返回 401）。

**请求体**：

| 字段 | 必填 | 说明 |
|------|:---:|------|
| `knowledge_id` | 是 | 外部知识库 ID（当前版本不细分，检索全部就绪文档；保留字段供后续路由扩展） |
| `query` | 是 | 检索问题 |
| `retrieval_setting` | 是 | `{top_k: int(1~100，上限受 MAX_TOP_K=20 截断), score_threshold: float(0~1，命中过滤)}`（score 见 §2.3/§2.4c 注：混合检索下三种来源分数统一归一 0~1，阈值语义一致） |
| `metadata_condition` | 否 | 暂不处理（忽略） |

错误：400（参数）、401（鉴权）、502（检索故障——**仅**存储层异常如向量维度不一致；embedding 服务不可用时自动降级 BM25 关键词检索并正常返回结果，0.1.39）。

**响应**：`{"records": [{"content", "score", "title", "metadata"}]}`（records 为空数组表示无命中）：

```json
{
  "records": [
    {
      "content": "……切片文本……",
      "score": 0.81,
      "title": "会议纪要.docx",
      "metadata": {"doc_id": 12, "category": "office"}
    }
  ]
}
```

**请求示例**：

```json
{
  "knowledge_id": "lantai",
  "query": "兰台是什么",
  "retrieval_setting": {"top_k": 3, "score_threshold": 0.5}
}
```

### 2.5 预览源文件（文本）

`GET /api/docs/{doc_id}/preview` → `data` 结构：

| 字段 | 说明 |
|------|------|
| type | `text`（txt/md/office 渲染文本）、`pdf`（浏览器原生查看器，含 note/raw_url）、`image`（图片类） |
| doc | DocumentOut |
| content | 渲染文本（image 类无此字段） |
| note | 可选说明（如扫描件 PDF 无文本层、.ppt 无法提取文本） |
| raw_url | image/pdf 类的源文件直出地址 |

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

`data.sources[]`：命中切片，按相关度降序；**`score` 统一为 0~1（4 位小数，越大越相关）**——向量召回为余弦相似度、BM25 命中为 sigmoid 归一值、启用重排时为交叉编码器相关性分（三者可混排展示）；前端可凭 `doc_id` 调预览接口。0.1.39 起检索为**混合检索**（向量 + BM25 默认开启，RRF 融合），embedding 不可用时自动降级 BM25 关键词检索；0.1.41 起**自动查询改写**（chat 槽位 LLM 把口语问题转成检索友好查询，失败/超时回退原问题，调用记录于 agent 日志 query_rewrite 槽位，不影响外部协议）。

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
| `/api/conversations/{id}` | PUT | 重命名会话（0.1.6，body `{"title": "新标题"}`） |
| `/api/conversations/{id}/messages` | GET | 会话消息列表（role: user/assistant） |
| `/api/conversations/{id}` | DELETE | 删除会话（级联消息） |

### 3.4 仅检索（调试/演示）

`GET /api/search?q=<检索词>&top_k=<n>` → `data` 为 sources 数组（同 3.1，无 answer）。

---

## 四、配置 API（除注明外需会话 Cookie）

### 4.1 密码验证（免会话）

`POST /api/settings/verify`，body `{"password": "Admin#123"}`

- 成功：`{"code":0,"message":"验证通过.","data":{"session":"<token>"}}`，响应头 `Set-Cookie: lantai_session=…; HttpOnly; SameSite=lax`（**双通道**：`data.session` 供桌面壳等跨站 iframe 场景经 `X-Lantai-Session` 请求头传递；Cookie 供浏览器直开）；
- 密码错误：401 `配置密码错误。`；连续 5 次错误：429 `尝试次数过多，请 1 分钟后再试。`

### 4.2 读取 AI 配置

`GET /api/settings/ai` → `data` 为 8 组配置（API Key 脱敏，仅尾 4 位；0.1.39 新增 `rerank` 槽位，含 `enabled` 能力开关，默认 false）：

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
    "embedding":  {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "api_key": "", "model": "bge-m3", "prompt": "", "temperature": 0.0},
    "rerank":     {"provider": "openai-compatible", "base_url": "", "api_key": "", "model": "", "prompt": "", "temperature": 0.0, "enabled": false}
  }
}
```

### 4.3 保存 AI 配置

`PUT /api/settings/ai`，body `{"items": {"<key>": {...}, ...}}`（key ∈ text/office/pdf_text/image/pdf_image/chat/embedding/**rerank**，可只提交部分）

| 字段 | 说明 |
|------|------|
| provider | `ollama` 或 `openai-compatible` |
| base_url | 如 `http://127.0.0.1:11434`；接口调用时自动补 `/v1` |
| api_key | 留空或 `****` 开头 = 保持不变；新值加密存储、返回脱敏 |
| model | 模型名（如 `qwen2.5:7b` / `llava:7b` / `bge-m3`） |
| prompt | 提示词；留空用默认 |
| temperature | 0~2 |
| enabled | 布尔，能力开关（0.1.39；当前仅 `rerank` 槽位使用——true 时检索候选经交叉编码器精排，默认 false） |
| local_ocr | 布尔，本地 OCR 开关（0.1.46；当前仅 `pdf_image` 槽位使用——true 时扫描件 OCR 走本机 Tesseract 离线识别（chi_sim+eng），默认 false） |

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
  "data": {"version": "0.1.49", "platform": "win32 / AMD64", "data_dir": "C:\\…\\data"}
}
```

### 4.7b 解析队列配置（需会话，V1.21 新增）

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

### 5.0 外部调用地址

| 场景 | 地址 | 说明 |
|------|------|------|
| 本机同机调用 | `http://127.0.0.1:8000` | 服务默认监听回环地址即可 |
| 局域网 / 远程调用 | `http://<服务机IP>:8000` | 需以 `lantai.exe --host 0.0.0.0`（或 `python run.py --host 0.0.0.0`）启动 |
| 地址前缀 | `/api/*` | 全部接口位于 `/api` 下；问答外部调用建议带 `Authorization: Bearer <API token>`（设置页生成） |

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

**文档状态**: API 说明 V1.47（与应用 0.1.49 同步）
**生成时间**: 2026-08-23
**前置文档**: 技术对接方案.md、PRD产品需求文档.md、数据库设计文档.md
**变更规则**: 接口变更时本文件随版本同步更新（0.1.1 → 0.1.2 → …）
