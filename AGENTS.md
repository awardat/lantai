# AGENTS.md — 兰台 (lantai) 本地 RAG 知识库演示系统

## 项目定位

本地运行的 RAG（检索增强生成）知识库**演示产品**：FastAPI 后端 + 原生 Web 前端（无构建步骤），单机部署，浏览器即用。工作区根目录即项目根目录：`C:\code\lantai`。

## 目录与文件策略（硬性约束）

- **工作区根目录只允许放 `AGENTS.md` 与 `README.md` 两个文件**；其他一切文件均放入对应目录。
- **工程相关约束**（本文件、开发约定）与**应用相关说明**（README：用途/用法/环境配置/起名意境）分离。
- 需求、方案、设计等一律落到 `docs/` 文档（目录结构见下），**文档格式参考 docs-sample 样例风格**（表头信息、来源标注、表格化需求、验收标准），按上下文只生成必要文档，不追求数量。
- **方案文档必须包含使用的技术、软件清单**。

```
docs/01-需求调研/      # 需求池管理表等
docs/02-方案设计/      # PRD、技术对接方案、数据库设计、原型设计方案、开发环境要求
docs/03-增长迭代/      # （预留）
docs/04-风控管理/      # （预留：需求变更记录等）
backend/               # FastAPI 后端（纯 API，/api/*）
frontend/              # 手写原生 HTML/CSS/JS 前端（无构建步骤，FastAPI 托管）
release/               # 编译发布目录（见"版本与发布"）
scripts/               # 开发自测脚本（make_sample_docs.py 等）
docs/                  # 用户演示文档目录（用户提供）
backend/data/          # 运行时生成 rag.db、uploads/（gitignore）
```

## 已确认的产品决策（2026-08-22 确认，2026-08-23 细化）

- **产品名**：兰台（汉代皇家档案馆之名）；代码/目录用拼音 `lantai`。
- **前后端分离**：后端 FastAPI 纯 API；前端原生单页，分**业务功能**与**配置功能**两块——**业务功能为首页**（问答、文档管理两个 Tab），右上角**设置图标进入配置功能**；**进入配置功能需密码**，默认 `Admin#123`，可在设置中修改（密码哈希存储）。
- **RBAC 设计只写入需求文档（首版不做）**；首版为单管理员密码门禁 + API token 调用。
- **设置项**：AI 配置、API token 生成/吊销、修改密码、关于（版本号）等。
- **按文件类型配置不同的 AI**（五类：文字文档、Office 文档、文字 PDF、图片、图片 PDF/OCR），每类可独立配置 provider/模型/提示词；问答模型与 embedding 模型全局配置。AI 接入协议参考 `C:\code\dsh-ui\deepseek-harness-master`（llm-pi-ai：OpenAI 兼容 Chat Completions + Ollama，模型带能力声明）。
- **保留上传源文件**，检索/问答结果可在 Web 内预览对应的源文件。
- **平台与部署**：需求支持 win/linux × x64/arm64，**本期只实现 win+x64（MVP+文件管理）**，其他平台只存在于需求文档；初期**只做单机部署**，Docker 只写入文档。
- **档位 3（只写方案与扩展点，不实现）**：流式输出（SSE）、对话历史、rerank 重排、hybrid 搜索（BM25+向量）、向量库替换（ChromaDB/Milvus）、多跳聚合。
- 演示文档：用户提供，放入 `docs/`；`scripts/make_sample_docs.py` 仅用于开发自测。

## 版本与发布（硬性约束）

- **首个版本号 `0.1.1`**；**每次变更第三段 +1**（0.1.1 → 0.1.2 → 0.1.3 …），版本号同步更新于代码、README 与相关文档。
- **不建立 setup 安装包**；编译版本放在 `release/lantai-0.1.x-windows-x64/` 文件夹（PyInstaller one-dir，含可执行文件 + 前端静态资源 + 数据目录说明），可整体拷贝运行。

## 技术栈与关键约束

- 本机仅 Python 3.14.7（已验证全部依赖均有 cp314 兼容版本，**无需更换 Python**）；仍**避免 torch / chromadb / onnxruntime** 等重依赖（本机网络访问 PyPI 不稳定，安装失败可重试或用镜像）。
- 依赖清单（锁定于 `backend/requirements.txt`）：`fastapi, uvicorn, pydantic, httpx, python-multipart, numpy, pypdf, python-docx`；开发/发布另加 `pyinstaller`。
- 向量存储：SQLite + numpy 暴力余弦检索，抽象 `VectorStore` 接口（演示级数据量毫秒级；为档位 3 的向量库替换预留）。
- LLM/Embedding：双 Provider——`ollama`（本地）/ OpenAI 兼容 API（云端），设置页按文件类型配置，即时生效。
- 注意：DeepSeek 官方 API 无 embedding 接口；云端 embedding 需选 OpenAI/通义等支持 embeddings 的厂商，或 embedding 走本地 Ollama（如 bge-m3）。
- 启动：`cd backend && python -m uvicorn app.main:app --port 8000`，浏览器打开 `http://127.0.0.1:8000`。
- 所有文件读写显式 UTF-8（规避 Windows GBK 问题）。

## 状态（截至 2026-08-23）

- ✅ 已确认：产品决策与细化需求（见上），版本 0.1.1、release 目录、文档规范。
- ✅ 已执行：文档体系（docs/01-需求调研、docs/02-方案设计）、README.md、本文件更新。
- ⏳ 原型（v0.1.1 可运行 MVP）：实现中，完成后**等待用户确认**再进入后续迭代。

## 会话注意事项

- 用户在意：先讲方案/文档、等确认；文档完成后先做原型，**原型完成必须停下等待确认**，不擅自扩大范围。
- 演示规模：几十~几百切片，不需要 GPU/分布式。
- 需要管理员权限的安装（如 Ollama 等）由用户手工执行（winget 命令见 README / 开发环境要求）。
