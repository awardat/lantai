# 兰台（lantai）· 本地 RAG 知识库

> 版本 **0.1.9** ｜ 平台 **Windows x64**（MVP）｜ 单机部署 ｜ 无构建步骤，两步启动

## 起名意境

**兰台**，汉代皇家档案馆。史载兰台令史典校秘书、掌图籍秘书之事，班固曾为兰台令史，后世遂以"兰台"代指国家藏书与档案之府，亦为史官之别称。

本产品以"兰台"为名，取意于此：它是**你自己的档案之府**——把散落的文档收拢入库、典藏有序，再以 AI 为"令史"，随时为你检索、整理、答疑。数据留在本地，如同兰台藏于宫禁，不外传、不流失。

## 用途

兰台是一个**本地运行的 RAG（检索增强生成）知识库演示系统**：

- 上传文档（txt / md / pdf / docx / 图片），系统自动解析、切块、向量化、入库；
- 用自然语言提问，系统检索最相关的切片，交给 AI 生成**带引用来源**的答案；
- 展示检索结果的**相似度分数**，并可**在 Web 内直接预览命中的源文件**；
- 按文件类型（文字文档 / Office / 文字 PDF / 图片 / 图片 PDF·OCR）**分别配置不同的 AI 模型**：图片走视觉模型、扫描件走 OCR 模型、文字走文本模型；
- 支持 **Ollama（本地）** 与 **OpenAI 兼容 API（云端）** 双 Provider，配置即时生效。

适合：个人知识管理、本地资料问答演示、企业内网离线知识库原型。

## 功能一览（v0.1.9）

| 模块 | 功能 |
|------|------|
| 文档管理 | 上传（≤20MB）、解析状态、文档列表、删除（连同向量与源文件） |
| 知识问答 | 提问 → top-k 检索 → AI 生成答案；展示相似度分数、引用来源、源文件预览 |
| 文件类型 AI | 五类文件各自配置 provider / 模型 / 提示词；问答与 embedding 全局配置 |
| 配置功能 | 设置图标进入（**密码门禁**，默认 `Admin#123`，可修改）：AI 配置（**输入框焦点离开自动保存**）、API token 生成/吊销、修改密码、关于 |
| 错误提示 | 全部中文友好提示（Ollama 未启动、模型未拉取、API Key 缺失等场景） |

## 环境配置

### 1. Python（必需）

本机已验证 **Python 3.14.7** 可用（全部依赖均有兼容版本）。如未安装：

```powershell
winget install --id Python.Python.3.14 -e --scope machine   # 需要管理员权限
```

### 2. AI 后端（二选一，按需）

**A. Ollama（本地，推荐演示）** —— 需要管理员权限时由你手工执行：

```powershell
winget install --id Ollama.Ollama -e            # 安装 Ollama（如提示权限不足加 --scope machine）
ollama pull qwen2.5:7b                          # 问答模型（文本）
ollama pull bge-m3                              # embedding 模型
ollama pull llava:7b                            # 图片理解模型（可选；或 qwen2.5vl:7b）
```

> Ollama 服务默认监听 `http://127.0.0.1:11434`，安装后需在兰台设置页确认。

**B. OpenAI 兼容云端 API**：在设置页填入 base_url 与 API Key 即可，例如：

| 用途 | 可选服务 | 示例 |
|------|----------|------|
| 问答 | DeepSeek / OpenAI / 通义 / 智谱等 | `https://api.deepseek.com/v1`（模型 `deepseek-v4-flash`） |
| embedding | OpenAI / 通义等（**DeepSeek 官方无 embedding 接口**） | `https://api.openai.com/v1`（模型 `text-embedding-3-small`）或通义 `text-embedding-v3` |

## 模型推荐（优先国产）

| 用途 | 文件类型 / 功能 | 本地（Ollama） | 云端推荐（国产优先） |
|------|----------------|----------------|----------------------|
| 文字理解 | 文字文档 / Office / 文字 PDF 处理、知识问答 | `qwen2.5:7b` | DeepSeek `deepseek-v4-flash` ｜ 通义 `qwen-plus` ｜ 智谱 `glm-4-plus` |
| 图片理解 | 图片（视觉描述入库） | `qwen2.5vl:7b`（或 `llava:7b`） | 通义 `qwen-vl-plus` ｜ 智谱 `glm-4v-plus` ｜ 硅基流动 `Qwen/Qwen2.5-VL-7B-Instruct` |
| OCR | 图片 PDF（扫描件识别） | `qwen2.5vl:7b`（或 `llava:7b`） | 通义 `qwen-vl-plus` ｜ 智谱 `glm-4v-plus` |
| 向量化 | embedding（全局，所有文件入库） | `bge-m3` | 通义 `text-embedding-v3` ｜ 硅基流动 `BAAI/bge-m3` |

> **提示**：DeepSeek、Kimi 官方 API **无 embedding 接口**，向量化请选通义 / 硅基流动 / 本地 `bge-m3`。
> 设置页「AI 配置」的**供应商下拉**已预置以上供应商与 Base URL（Ollama、DeepSeek、OpenCode Go、通义、智谱、Kimi、硅基流动、OpenAI），选择后自动填充推荐模型，可手动修改；填入 API Key 后点击**「测试」**可验证连通性并获取模型清单（点击模型名自动填入）。

## 用法

### 方式一：源码运行（开发/演示）

```powershell
# 1. 安装依赖（首次）
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 2. 启动
python -m uvicorn app.main:app --port 8000
```

浏览器打开 **http://127.0.0.1:8000**。

### 方式二：编译版运行（release）

解压 `release/lantai-0.1.9-windows-x64.zip`，运行目录内 `lantai.exe`，浏览器打开 http://127.0.0.1:8000。

> 数据（`rag.db`、上传源文件）保存在运行目录的 `data/` 下，整体拷贝目录即可迁移。

### 首次使用三步

1. 点右上角**设置图标** → 输入默认密码 `Admin#123` → 在「AI 配置」中确认/填写模型（默认指向本机 Ollama）；
2. 「文档管理」Tab 上传文档，等待解析完成（状态变为"已就绪"）；
3. 「问答」Tab 提问，查看答案、相似度分数与引用来源，点击来源卡片可**预览源文件**。

## 版本与发布

- 版本规则：首个版本 **0.1.1**，每次变更**第三段 +1**（0.1.1 → 0.1.2 → …）。
- **各版本号与修改内容见 `docs/03-增长迭代/版本记录.md`**（不在此罗列）。
- 发布物：`release/lantai-0.1.x-windows-x64/`（PyInstaller one-dir 编译版，**不制作 setup 安装包**），随附 zip 压缩包。
- 路线图与档位 3 方案（流式 SSE、对话历史、rerank、hybrid 检索、向量库替换、多跳聚合、RBAC、多平台）见 `docs/01-需求调研/需求池管理表.md` 与 `docs/02-方案设计/技术对接方案.md`。

## 文档导航

| 文档 | 内容 |
|------|------|
| `docs/01-需求调研/需求池管理表.md` | 需求池（含 RBAC、多平台、Docker 等设计需求） |
| `docs/02-方案设计/PRD产品需求文档.md` | 产品需求 |
| `docs/02-方案设计/技术对接方案.md` | 技术栈、AI 接入、API、版本与发布规范 |
| `docs/02-方案设计/API说明文档.md` | 全部 API 接口说明（请求/响应示例、鉴权、错误码、外部调用示例） |
| `docs/02-方案设计/数据库设计文档.md` | SQLite 表结构 |
| `docs/02-方案设计/原型设计方案.md` | 界面与交互设计 |
| `docs/02-方案设计/开发环境要求.md` | 环境版本清单与管理员安装命令 |

## 常见问题

- **问答报"无法连接 Ollama"**：确认 Ollama 已启动（托盘图标存在），或改配云端 API。
- **日志位置**：每次启动生成新的日志文件 `backend/data/logs/lantai-<时间戳>.log`（编译版在运行目录 `data/logs/`），保留最近 20 个；排查问题时可查看。
- **报"模型不存在/未拉取"**：执行 `ollama list` 检查，缺少则 `ollama pull <模型名>`。
- **云端 embedding 报 404**：DeepSeek 官方 API 无 embeddings 接口，请将 embedding 换为 OpenAI/通义等或本地 bge-m3。
- **忘记配置密码**：删除 `data/rag.db` 中 settings 表的密码记录或直接删除数据目录重新初始化（演示数据可重建）。
