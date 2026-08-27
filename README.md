# 兰台（lantai）· 本地 RAG 知识库

> 版本 **0.1.42** ｜ 平台 **Windows x64**（MVP）｜ 单机部署 ｜ 无构建步骤，两步启动

## 起名意境

**兰台**，汉代皇家档案馆。史载兰台令史典校秘书、掌图籍秘书之事，班固曾为兰台令史，后世遂以"兰台"代指国家藏书与档案之府，亦为史官之别称。

本产品以"兰台"为名，取意于此：它是**你自己的档案之府**——把散落的文档收拢入库、典藏有序，再以 AI 为"令史"，随时为你检索、整理、答疑。数据留在本地，如同兰台藏于宫禁，不外传、不流失。

## 用途

兰台是一个**本地运行的 RAG（检索增强生成）知识库演示系统**：

- 上传文档（txt / md / pdf / docx / doc / wps / xls / xlsx / ppt / pptx / 图片），系统自动解析、切块、向量化、入库；
- 用自然语言提问，系统检索最相关的切片，交给 AI 生成**带引用来源**的答案；
- 展示检索结果的**相似度分数**，并可**在 Web 内直接预览命中的源文件**；
- 按文件类型（文字文档 / Office / 文字 PDF / 图片 / 图片 PDF·OCR）**分别配置不同的 AI 模型**：图片走视觉模型、扫描件走 OCR 模型、文字走文本模型；
- 支持 **Ollama（本地）** 与 **OpenAI 兼容 API（云端）** 双 Provider，配置即时生效。

适合：个人知识管理、本地资料问答演示、企业内网离线知识库原型。

## 功能一览（v0.1.39）

| 模块 | 功能 |
|------|------|
| 文档管理 | 上传（≤20MB）、解析状态（**文件计数 + 状态筛选联动**）、文档列表、**失败原因悬停 + 失败重试（可指定文件大类兜底）**、删除（连同向量与源文件） |
| 检索增强 | **混合检索（BM25 关键词 + 向量语义，RRF 融合）**；**提问自动改写为检索友好查询**；embedding 不可用时自动降级关键词检索；**可选交叉编码器重排**（设置页「重排」开启） |
| 知识问答 | 提问 → top-k 检索 → AI 生成答案；展示相似度分数、引用来源、源文件预览 |
| **外部集成** | **Dify 外部知识库**：`POST /api/external/retrieval` 实现 Dify External Knowledge API 协议（Bearer 鉴权复用 API token） |
| 文件类型 AI | 五类文件各自配置 provider / 模型 / 提示词；问答与 embedding 全局配置 |
| 配置功能 | 设置图标进入（**密码门禁**，默认 `Admin#123`，可修改）：AI 配置（**输入框焦点离开自动保存**）、API token 生成/吊销、修改密码、关于 |
| 错误提示 | 全部中文友好提示（Ollama 未启动、模型未拉取、API Key 缺失等场景） |
| **桌面壳** | `lantai-shell.exe` 单机应用形态：自动拉起服务（无 cmd 窗口）、内嵌页面、终端浮层；直接运行 `lantai.exe` 保持原控制台模式 |

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
| 文字理解 | 文字文档 / Office / 文字 PDF 处理、知识问答 | `qwen2.5:7b` | DeepSeek `deepseek-v4-flash` ｜ 通义 `qwen-plus` ｜ 智谱 `glm-4-plus` ｜ 小米 MiMo `mimo-v2.5-pro` |
| 图片理解 | 图片（视觉描述入库） | `qwen2.5vl:7b`（或 `llava:7b`） | 通义 `qwen-vl-plus` ｜ 智谱 `glm-4v-plus` ｜ 小米 MiMo `mimo-v2.5-pro` ｜ 硅基流动 `Qwen/Qwen2.5-VL-7B-Instruct` |
| OCR | 图片 PDF（扫描件识别） | `qwen2.5vl:7b`（或 `llava:7b`） | 通义 `qwen-vl-plus` ｜ 智谱 `glm-4v-plus` |
| 向量化 | embedding（全局，所有文件入库） | `bge-m3` | 通义 `text-embedding-v3` ｜ 硅基流动 `BAAI/bge-m3` |
| 重排（可选） | 检索结果精排（设置页「重排」开启后生效） | （Rerank 系模型，Ollama 支持有限） | **硅基流动 `BAAI/bge-reranker-v2-m3`（首选，多语言效果好，与 bge-m3 同族）** ｜ `Qwen/Qwen3-Reranker-0.6B`（更轻更快） ｜ 通义 `qwen-rerank` 等 |

> **提示**：DeepSeek、Kimi、小米 MiMo 官方 API **无 embedding 接口**，向量化请选通义 / 硅基流动 / 本地 `bge-m3`。
> **重排（可选增强）**：默认关闭（系统为 BM25+向量混合检索）。启用需配置 rerank 模型（如硅基流动，Base URL `https://api.siliconflow.cn/v1`，模型 `BAAI/bge-reranker-v2-m3`），勾选「启用重排」即对检索候选精排；重排服务不可用时自动回退混合检索，不影响问答。
> 设置页「AI 配置」的**供应商下拉**已预置以上供应商与 Base URL（Ollama、DeepSeek、OpenCode Go、通义、智谱、Kimi、小米 MiMo、硅基流动、OpenAI），选择后自动填充推荐模型，可手动修改；填入 API Key 后点击**「测试」**可验证连通性并获取模型清单（点击模型名自动填入）。

## 用法

> **监听地址**：服务默认仅监听本机回环地址 `127.0.0.1:8000`（不对外网开放、不接受局域网访问）。如需远程调用/局域网访问测试，用启动参数即可：`lantai.exe --host 0.0.0.0`（源码 `python run.py --host 0.0.0.0`），无需改代码——演示产品默认不开放远程（安全考虑）。

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

### 方式二：桌面壳（编译版，唯一发布形态）

解压 `release/lantai-shell-0.1.x-windows-x64.zip`，双击目录内 `lantai-shell.exe`——壳自动在内部拉起兰台服务（**无独立 cmd 窗口**），就绪后直接显示兰台界面；右下角「终端」按钮可查看服务日志/重启/停止；关闭窗口即退出并结束服务。数据保存在壳目录的 `data/` 下。

> 壳目录内的 `lantai.exe` 为内嵌服务（供壳拉起），也可直接运行作为调试/直跑入口：`lantai.exe` 自动打开浏览器；`lantai.exe --server` 不自动打开（供壳使用）。
> 历史版本（0.1.21 及更早）曾双轨发布独立服务版 `lantai-0.1.x-windows-x64/`，保留可回滚；0.1.22 起仅发布壳单轨。

> 数据（`rag.db`、上传源文件）保存在运行目录的 `data/` 下，整体拷贝目录即可迁移。

### 首次使用三步

1. **配置智能体（AI）**：点右上角**设置图标** → 输入默认密码 `Admin#123` → 「AI 配置」Tab。这里共 8 组模型（7 组处理模型 + 可选重排），每项可选择 Ollama（本地）或 OpenAI 兼容云端（DeepSeek / 通义 / 智谱 / Kimi / 硅基流动 / OpenAI），默认指向本机 Ollama（`http://127.0.0.1:11434`），输入框焦点离开即自动保存，修改立即生效：

   | 模型组 | 用途 | 默认（Ollama） | 备注 |
   |--------|------|----------------|------|
   | **问答模型**（chat） | 回答你的提问 | `qwen2.5:7b` | 也可换云端 DeepSeek 等 |
   | **向量化模型**（embedding） | 文档入库时生成向量 | `bge-m3` | **必须配置，否则文档无法入库**（DeepSeek 官方无 embedding 接口，云端请用通义/硅基流动） |
   | 文字文档 / Office / 文字 PDF | 文本类解析 | `qwen2.5:7b` | 三类可各自独立配置 |
   | 图片 / 图片 PDF·OCR | 视觉理解与扫描件识别 | `llava:7b` | 需要视觉模型（如 `qwen2.5vl:7b`） |
   | **重排（rerank，可选）** | 检索结果精排（增强问答相关性） | 关闭 | **默认不启用**；需要时填 rerank 模型（推荐硅基流动 `BAAI/bge-reranker-v2-m3`，Base URL `https://api.siliconflow.cn/v1`）并勾选「启用重排」 |

   填好每组后点「**测试**」可验证连通性并获取模型清单（点击模型名自动填入）；云端服务需先在「API Token」或对应卡片填入 API Key。完成后回到首页。

2. **上传文档**：「文档管理」Tab 点击「上传文档」上传文件，等待解析完成（状态变为"已就绪"）；
3. **提问**：「问答」Tab 输入问题，查看答案、相似度分数与引用来源，点击来源卡片可**预览源文件**。

## 版本与发布

- 版本规则：首个版本 **0.1.1**，每次变更**第三段 +1**（0.1.1 → 0.1.2 → …）。
- **各版本号与修改内容见 `docs/03-增长迭代/版本记录.md`**（不在此罗列）。
- 发布物：`release/lantai-shell-0.1.x-windows-x64/`（桌面壳绿色便携版：壳 exe + 服务 one-dir + WebView2Loader.dll，双击即用，**不制作 setup 安装包**），随附 zip 压缩包；**0.1.22 起为唯一发布形态**（此前双轨的独立服务版目录保留可回滚）。
- 路线图与档位 3 方案（流式 SSE、对话历史、**rerank 与 hybrid 检索（0.1.39 已实现）**、向量库替换、多跳聚合、RBAC、多平台）见 `docs/01-需求调研/需求池管理表.md` 与 `docs/02-方案设计/技术对接方案.md`。

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
| `docs/02-方案设计/桌面壳方案.md` | 桌面壳（lantai-shell）方案：架构、状态机、构建发布 |
| `LICENSE` | MIT 许可证（开放源码，允许自由使用/修改/再分发） |

## 常见问题

- **问答报"无法连接 Ollama"**：确认 Ollama 已启动（托盘图标存在），或改配云端 API。
- **日志位置**：每次启动生成新的日志文件 `backend/data/logs/lantai-<时间戳>.log`（编译版在运行目录 `data/logs/`），保留最近 20 个；**智能体日志**（每次 AI 调用的提示词/思维链/用量）在 `data/logs/agent-<时间戳>.log`；排查问题时可查看。
- **报"模型不存在/未拉取"**：执行 `ollama list` 检查，缺少则 `ollama pull <模型名>`。
- **云端 embedding 报 404**：DeepSeek 官方 API 无 embeddings 接口，请将 embedding 换为 OpenAI/通义等或本地 bge-m3。
- **忘记配置密码**：删除 `data/rag.db` 中 settings 表的密码记录或直接删除数据目录重新初始化（演示数据可重建）。
