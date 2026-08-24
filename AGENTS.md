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
docs/02-方案设计/      # PRD、技术对接方案、API说明文档、数据库设计、原型设计方案、开发环境要求
docs/03-增长迭代/      # 版本记录等（版本号+修改内容，不放入 README）
docs/04-风控管理/      # （预留：需求变更记录等）
docs/05-质量评审/      # 质量评审报告、测试报告、验收记录等
backend/               # FastAPI 后端（纯 API，/api/*）
frontend/              # 手写原生 HTML/CSS/JS 前端（无构建步骤，FastAPI 托管）
shell/                 # 桌面壳工程（Tauri 2，复用 C:\code\dsh-ui；src-tauri + ui + 壳文档）
release/               # 编译发布目录（见"版本与发布"）
scripts/               # 开发自测脚本（make_sample_docs.py 等）
docs/演示文档/          # 用户演示文档目录（用户提供，import_docs.py 默认导入此目录）
sample/                # 测试样本 PDF（用户提供：扫描件 / Asperger 论文 OCR 样本，不入库）
knowledge/             # 独立知识备忘（与本项目无关，用户要求沉淀，不参与项目流程）
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
- **桌面壳**：`release/lantai-shell-0.1.x-windows-x64/` 绿色便携目录（壳 exe + WebView2Loader.dll + portable.marker + 兰台服务 one-dir 内容），不建 setup；壳与兰台同版本号体系（第三段 +1）。
- **发行版不得包含测试数据（硬性）**：release 目录与 zip **一律不含 data/**（rag.db、uploads/、logs/ 均不打包；首次启动自动创建）；发布前核对发行物清单（教训：0.1.19 壳 zip 误含自测空库与日志，用户解压后误判"数据库被重置"，CH-039）。

## 技术栈与关键约束

- 本机仅 Python 3.14.7（已验证全部依赖均有 cp314 兼容版本，**无需更换 Python**）；仍**避免 torch / chromadb / onnxruntime** 等重依赖（本机网络访问 PyPI 不稳定，安装失败可重试或用镜像）。
- 依赖清单（锁定于 `backend/requirements.txt`）：`fastapi, uvicorn, pydantic, httpx, python-multipart, numpy, pypdf, python-docx`；开发/发布另加 `pyinstaller`。
- 向量存储：SQLite + numpy 暴力余弦检索，抽象 `VectorStore` 接口（演示级数据量毫秒级；为档位 3 的向量库替换预留）。
- LLM/Embedding：双 Provider——`ollama`（本地）/ OpenAI 兼容 API（云端），设置页按文件类型配置，即时生效。
- 注意：DeepSeek 官方 API 无 embedding 接口；云端 embedding 需选 OpenAI/通义等支持 embeddings 的厂商，或 embedding 走本地 Ollama（如 bge-m3）。
- 启动：`cd backend && python -m uvicorn app.main:app --port 8000`，浏览器打开 `http://127.0.0.1:8000`。
- 所有文件读写显式 UTF-8（规避 Windows GBK 问题）。

## 执行约束（硬性）

- **所有代码/文档变更执行前必须等待用户明确确认**：先说明方案（改什么、怎么改、影响范围），用户确认后方可动手；用户未确认前不得执行任何实施动作。
- 评审报告指出的问题（docs/05-质量评审/）按用户确认的优先级与范围修复，不擅自扩大范围。
- 每次修复/变更后按版本规则升级版本号（第三段 +1），并同步代码、README、相关文档与 release。

## 自测规范（硬性）

### 1. 自测基线工具
- `scripts/mock_ai_server.py`：全链路 Mock AI（chat/流式/思维链/embeddings/视觉消息兼容），无真实 AI 也可回归
- `scripts/make_sample_docs.py`：样例文档生成（txt/md/docx/pdf/图片）
- `scripts/analyze_pdf.py`：PDF 质量诊断（页密度/变音/页眉页脚/流序 vs 几何序/栏分布）
- `sample/`：真实样本（Asperger 56 页文字 PDF、单页扫描件 PDF）——解析/预览回归基准

### 2. 每轮变更必测清单
1. **版本号同步**：config.py / README / requirements / API说明文档 / 版本记录 / release 目录名逐项核对一致
2. **依赖声明核对**：新增 import 必须写入 requirements.txt 并验证打包（含 PyInstaller 产物检查）
3. **Mock 全链路回归**：上传 → 解析 → 检索 → 流式问答 → 对话历史
4. **分支覆盖**：异常与降级路径——AI 不可用（中文提示）、视觉模型不可用（扫描件降级）、无效会话 404、白名单/超限拒绝
5. **敏感路径**：API Key 加密往返（落库密文 → 调用路径明文）与脱敏展示
6. **真实样本**：sample/ 两个 PDF 的解析（分类/顺序/OCR）与预览（原生渲染）
7. **前端静态检查**：新页面元素/交互逻辑在打包资源中存在（grep 验证）
8. **关键响应行为**：响应头（如 Content-Disposition: inline）、SSE 事件序列（sources→delta→done）

### 3. 历史教训条款（防止重蹈覆辙）
- 批量文本替换后**必须语法检查 + 应用导入验证**（教训：H1 `_ocr_pdf` doc_id NameError）
- edit 失败必须重读文件重试，不得静默跳过（教训：H2 pdfminer.six 依赖漏声明）
- 发布前逐项过版本号清单（教训：H3 config 落后一版）
- 测试前检查 8000 端口占用（外部旧进程干扰），避免误测
- 新依赖/新资源必须验证**打包产物**（_internal 检查）与**响应行为**（如 attachment→inline）
- 发布前核对**发行物清单**：release 目录与 zip 不得包含 data/、日志、测试残留（教训：CH-039 壳 zip 误含测试 data）
- 自测结论在交付说明中明示：通过项、覆盖到的分支、未覆盖项（如依赖真实视觉模型的部分）

### 4. 测试文档
- 人工测试按 `docs/05-质量评审/测试方案.md` 执行，产出测试报告（docs/05-质量评审/测试报告.md）
- 发现缺陷按流程：记录 → 登记需求变更（CH）→ 方案确认 → 实施升版 → 回归

## 状态（截至 2026-08-23）

- ✅ 已确认：产品决策与细化需求（见上），版本 0.1.1、release 目录、文档规范。
- ✅ 已执行：文档体系（docs/01-需求调研、docs/02-方案设计）、README.md、本文件更新。
- ✅ 已执行：可运行原型 v0.1.1（前后端分离、按文件类型 AI 配置、配置密码门禁、API token、源文件 Web 预览、SQLite+numpy 向量检索），自测通过（上传/解析/检索/问答/预览/门禁/token/改密/限流/错误提示），编译版 `release/lantai-0.1.1-windows-x64/` 验证可运行。
- ✅ 已执行：代码与文档评审（docs/05-质量评审/代码与文档评审报告-v0.1.1.md），用户确认后按报告修复并升版 **0.1.2**：S1 API Key 解密、H1 阻塞端点线程池化、M1 配置合并保存、L1-L9 文档与代码同步、维度保护、temperature 校验、spec 入库（scripts/build/）、lifespan 迁移；回归自测通过，`release/lantai-0.1.2-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.3（用户确认后实施）：AI 供应商预置（参考 dsh，7 个供应商预置 URL 与推荐模型，国产优先）、AI 配置界面固定尺寸+滚动条、需求变更记录（docs/04-风控管理/需求变更记录.md）、README 模型推荐表；`release/lantai-0.1.3-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.4（用户确认后实施）：供应商新增 OpenCode Go（本地代理，http://127.0.0.1:8787/v1）、DeepSeek 默认模型 deepseek-v4-flash、"测试"功能（连通性+模型清单可点击填入）、后端日志文件输出（每次启动新文件，保留 20 个）；0.1.4 修订（并入）：配置窗口尺寸修正（进入配置后大窗口固定、密码门禁小窗口自适应）、版本记录文件（docs/03-增长迭代/版本记录.md）。
- ✅ 已执行：0.1.5（用户确认档位 3 开工后实施）：**SSE 流式输出**（/api/chat/stream：sources → delta → done，前端打字机渲染）、**对话历史**（conversations/messages 表 schema v2、会话 CRUD、携带最近 6 条历史上下文并入库、前端会话管理）、scripts/mock_ai_server.py 开发自测 Mock AI；全链路自测通过（Mock AI：上传→解析→流式问答→多轮历史），`release/lantai-0.1.5-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.6（用户确认整改方案后实施，N-M2 模型名经用户决策保留）：评审整改（代码与文档评审报告-v0.1.5.md）——N-M1 流式无效会话预校验 404、N-M3 文档描述修正、N-L1~N-L8 文档与代码同步、N-L9 会话重命名、N-L10 启用外键；N-L11/N-L12 延后；`release/lantai-0.1.6-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.7（用户确认后实施）：配置功能**自动保存**（AI 配置输入框焦点离开即保存、串行化提交、轻提示"已自动保存"、保留手动按钮）；OpenCode Go 默认 URL 改为官方端点 `https://opencode.ai/zen/go/v1`；`release/lantai-0.1.7-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.8（用户确认后实施）：**前端排版重构**（左右两栏：左栏固定宽=logo+会话历史+底部导航，右栏=消息流+底部输入框、提问后清空；会话标题首轮自动生成；改名/删除小图标；标题截断悬停；来源小字内嵌）；**R117 ①②③**（PDF 几何排序提取 pdfminer.six+页眉页脚过滤+页码碎片+基础双栏检测、页级文本密度判定混合 PDF 自动 OCR、文字 PDF 页内图片抽取+视觉描述+页码绑定；④跨页表格列下一轮）；`release/lantai-0.1.8-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.9（用户提出后实施）：**PDF 预览改用浏览器原生查看器**（iframe 加载源文件，支持缩放/翻页/搜索；文本提取降级；扫描件直接渲染原始页面，不再提示"无文本内容"）；`release/lantai-0.1.9-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.10（用户提出后实施）：**智能体日志**——独立文件 `data/logs/agent-<时间戳>.log`（JSON 行，保留 20 个）记录每次 AI 调用的提示词（图片占位）、思维链 reasoning_content、答案截断、token 用量、耗时、槽位/会话/文档上下文；流式与非流式均记录；`release/lantai-0.1.10-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.11（用户报告扫描件解析失败后修复）：安装 Pillow（pypdf 图片提取依赖）恢复扫描件页图提取与 OCR 通道；含 OCR 内容的 PDF 分类归 `pdf_image`（单页扫描件不再显示"文字 PDF"，失败时也先更新分类）；Mock 视觉回复不再拼入 base64；`release/lantai-0.1.11-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.12（用户确认整改方案后实施）：H1 `_ocr_pdf` 补 doc_id（扫描件+视觉不可用 NameError 修复）、H2 requirements 补 pdfminer.six、H3 config 版本同步、M1 日志挂载幂等提前返回、M2 数据库文档预留表清理、L1-L5 文档同步、L8 §9.2 复核；L6/L7 延后；`release/lantai-0.1.12-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.13（用户报告 PDF 预览触发下载后修复）：`preview/raw` 改为 `content_disposition_type="inline"`（iframe 浏览器原生查看器内联显示，不再触发下载）；`release/lantai-0.1.13-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.14 logo 变更（繁体"蘭臺"横排回纹 SVG）**已按用户指示暂时撤销**，代码与文档回退至 0.1.13（CH-028 标注已撤销）。
- ✅ 已执行：0.1.15（用户提出后实施）：左上角品牌文字"兰台"改为繁体"**蘭臺**"（仅文字，其余不变）；`release/lantai-0.1.15-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.16（用户报告 GBT 43052 PDF 误判后修复）：`text_readability` 可读性检测（CJK/英文占比-字符码惩罚）＋pdfminer 空/不可读回退 pypdf（可读才采用，防伪文本入库）＋`pdf_image` 预览 note 说明"文本层编码不可映射（缺 ToUnicode），经 OCR 识别"；GBT 样本仍走 OCR（判定正确）、Asperger/扫描件回归不变；`release/lantai-0.1.16-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.17（用户确认整改方案后实施）：评审文档整改（代码与文档评审报告-v0.1.16.md）——M1 测试方案升 0.1.17 并补 GBT 用例、M2 技术对接方案补 inline/可读性/双引擎、L1-L5 文档同步（原型方案两栏布局、变更详情、版本记录 0.1.14 撤销行等）、L8 阈值注释；L6/L7/L9 延后；`release/lantai-0.1.17-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.18（用户提出后实施）：**批量上传浮层**（点击"上传文档"展开，拖拽即传+保留选择文件按钮，前端小并发上传、列表实时状态）；**解析队列**（FIFO + 固定并发 worker 默认 10，设置页「解析」可调 1~50 即时生效；文档新增"排队中"状态；重启自动恢复排队文档）；`release/lantai-0.1.18-windows-x64/` 验证可运行。
- ✅ 已执行：0.1.19（用户确认壳方案后实施，CH-037/R119）：**桌面壳（lantai-shell）**——复用 C:\code\dsh-ui 的 Tauri 2 壳工程至 `shell/`：ConPTY 无窗口拉起兰台服务（`lantai.exe --server` 新增参数不开浏览器）、就绪探测 8000 后 iframe 内嵌页面、终端浮层（日志/重启/停止）、Job Object 关闭清理、单实例、缩放、便携模式；直接运行 `lantai.exe` 保持原控制台模式；绿色便携 `release/lantai-shell-0.1.19-windows-x64/`（不建 setup）；文档：桌面壳方案（docs/02）、R119、CH-037、版本记录、README。
- ✅ 已执行：0.1.20（用户报告缺陷后修复，CH-039）：**壳"localhost 拒绝连接"**——裸 cargo build 缺 `tauri/custom-protocol` feature 导致 release exe 处于 dev 模式加载 devUrl（localhost:1420）；修复：显式启用 custom-protocol（Cargo.toml 注释说明 + 壳文档）；**发行版不含测试数据**（绿色目录/zip 不再打包 data/，AGENTS.md 增硬性条款）；CDP 实测主窗口加载 tauri:// 本地资产 + iframe 显示兰台页面。
- ⏳ **等待用户确认**后再进入后续迭代（RBAC、多平台、Docker、档位 3 等均只入需求与文档）。

## 会话注意事项

- 用户在意：先讲方案/文档、等确认；**任何代码执行前必须等待用户明确确认**，不擅自扩大范围。
- 演示规模：几十~几百切片，不需要 GPU/分布式。
- 需要管理员权限的安装（如 Ollama 等）由用户手工执行（winget 命令见 README / 开发环境要求）。
