# 兰台 MCP Server 方案（细化设计）

| 项目 | 内容 |
|------|------|
| 文档版本 | V0.1（方案稿，未实施） |
| 登记 | 需求变更记录 CH-095（待实施） |
| 生成时间 | 2026-08-28 |
| 来源 | 用户提出"做个 MCP 协议怎样，把 MCP 方案细化一下"；衔接 CH-086 备忘⑤（MCP 按分析场景封装）、0.1.38 Dify 外部知识库经验 |
| 目标 | 把兰台暴露为标准 **MCP Server**，供 Claude Desktop / Cursor / Dify Agent（MCP 节点）等客户端直接检索与问答 |

---

## 一、背景与定位

- **MCP（Model Context Protocol）**：Anthropic 2024 发布的标准工具调用协议（JSON-RPC 2.0），客户端（Claude/Cursor/支持 MCP 的 Agent）经 server 声明 tools/resources/prompts 后即可调用。
- 兰台已有 `POST /api/external/retrieval`（Dify 外部知识库专用协议，0.1.38）；**MCP 是通用工具协议**——两者共存，MCP 覆盖更多客户端形态。
- 定位：**只读知识服务**优先（检索/问答/盘点文档），管理类工具（上传/删除/重解析）默认不暴露（企业安全口径：只读为主，管理走原 Web UI）。

## 二、使用的技术 / 软件清单

| 项 | 选型 | 说明 |
|----|------|------|
| 协议 | MCP（JSON-RPC 2.0 / Streamable HTTP、stdio） | 官方规范，2025-06 standardized |
| SDK | **官方 `mcp` python-sdk（FastMCP 封装）** | 轻量、含 FastMCP server 与 stdio/http 传输；备选 `fastmcp`（jlowin，量更小）——实施前先验证 Python 3.14 wheel 可用性（PyPI 不稳，用镜像） |
| 传输 | **stdio**（本机客户端）+ **Streamable HTTP**（远程/局域网，Dify MCP 节点） | 挂现有 uvicorn（新增 `/mcp` 路由），无需新进程（HTTP）；stdio 走独立脚本 |
| 鉴权 | HTTP 模式复用 **API token**（Bearer，设置页生成） | 与 Dify external 同一套 token；stdio 本地免鉴权（默认连本机） |
| 依赖新增 | `mcp`（或 `fastmcp`） | 1 个轻依赖 + 打包验证（PyInstaller `_internal` 检查） |

## 三、Tools 设计（v1 范围：只读）

| Tool | 入参 | 返回 | 内部接线 |
|------|------|------|----------|
| `search_knowledge` | `query: str`（必）、`top_k: int = 8` | `[{doc_id, doc_name, category, chunk_text, score}]` | **直接调 `retriever.retrieve`**（含改写/RRF/重排/降级全链） |
| `ask_lantai` | `question: str`（必）、`top_k: int = 8` | `{answer, sources:[...]}` | **复用 chat 核心流水线**（检索→build_context→LLM；提为内部 service 函数供 router 与 MCP 共用，避免重复实现） |
| `list_documents` | `status?`, `page=1`, `page_size=20` | `{total, items:[DocumentOut]}` | 复用 `store.list_documents` / `_doc_out` |
| `get_document` | `doc_id: int` | DocumentOut 元信息（含 chunk_count/category） | 复用 `store.get_document` |

- 命名规范：工具名清晰、description 中文+英文关键、入参 pydantic 校验（非法中文报错）。
- **管理类（v2 可选，默认不开）**：`upload_document`/`delete_document`/`reparse_document`——挂设置页开关（"MCP 开放管理工具"）后再启用；默认只读。

## 四、传输与会话

| 模式 | 形态 | 用途 |
|------|------|------|
| **stdio** | `python mcp_stdio.py`（内部调 FastMCP.run(transport="stdio")） | Claude Desktop / Cursor 配置 `command` 指向本机脚本；免鉴权（回环本机） |
| **Streamable HTTP** | FastAPI 挂 `/mcp`（POST，MCP streamable-http 协议） | Dify MCP 节点（URL= `http://<host>:8000/mcp` + API token）、远程客户端 |

- HTTP 鉴权中间件：校验 `Authorization: Bearer <token>`（复用 `security.validate_api_token` 逻辑），无效 401 + 中文；会话以 token 归属记录（agent_log slot=mcp_tool 便于审计）。
- 幂等与错误：工具异常返回 `{"error": "中文说明"}`（不抛未封装异常）；搜索/问答失败沿用现有容错（降级/回退）。

## 五、客户端接入示例

**Claude Desktop（claude_desktop_config.json）**：

```json
{
  "mcpServers": {
    "lantai": { "command": "python", "args": ["C:/code/lantai/scripts/mcp_stdio.py"], "cwd": "C:/code/lantai" }
  }
}
```

**Dify（Agent 工作流 → MCP 节点）**：类型 Streamable HTTP，URL `http://192.168.19.1:8000/mcp`，Bearer 填兰台设置页 API token；节点可调 `search_knowledge`/`ask_lantai`。

## 六、实施里程碑（CH-095）

| # | 内容 | 验收 |
|---|------|------|
| 1 | 依赖验证（mcp/fastmcp 在 Python 3.14 安装可用） | pip 安装 + import 通过 |
| 2 | chat 核心抽 `service_chat(question, top_k, st)`（router 与 MCP 共用） | /api/chat 行为不变 |
| 3 | `mcp_tools.py`：FastMCP + 4 只读工具 + stdio/HTTP 双入口 + Bearer 鉴权 | 本地 mcp 客户端联调（stdio）+ Dify/curl 冒烟（HTTP） |
| 4 | 文档同步：API 说明文档 MCP 章节（V+1）、测试方案 TC（stdio/HTTP/鉴权/中文错误）、README、CH-095 完成、打包验证（mcp 依赖进 `_internal`） | 发版前完整自测清单 |

## 七、风险与边界

- **SDK 兼容性**：本机 Python 3.14.7（Ahead-of-time）——官方 mcp python-sdk 若依赖版本不稳，备选 `fastmcp` 或自实现 JSON-RPC（仅 4 工具，协议面窄，可手写兜底）。
- **只读边界**：默认不暴露写操作，避免恶意客户端（HTTP 开放场景）篡改知识库。
- **性能**：HTTP 模式复用 uvicorn 线程池，检索/问答耗时与现有接口一致（重排/改写会触发，同 /api/chat 行为）。
- **不新建进程**：HTTP 挂现有服务（零端口占用）；stdio 才需脚本进程（由客户端拉起）。

---

**文档状态**: MCP-Server 方案 V0.1（细化稿；对应 CH-095 待实施；实施时随代码升版同步更新 API 说明文档 / 测试方案 / README）