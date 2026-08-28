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
- **不建立 setup 安装包**；**发布单轨（0.1.22 起，CH-041/CH-044）**：只发布 `release/lantai-shell-0.1.x-windows-x64/` 绿色便携目录（壳 exe + WebView2Loader.dll + portable.marker + 兰台服务 one-dir 内容，可整体拷贝运行），随附 zip；**不再单独发布** `lantai-0.1.x-windows-x64/` 服务版目录/zip，**开发过程同样单轨**：服务 one-dir 为构建中间产物，**release 下不留服务版目录**（发布统一走 `scripts/build_release.ps1` 一键流程：PyInstaller → 组装 → 清理中间产物 → zip → 发行物校验）；历史双轨版本 0.1.1~0.1.21 保留可回滚；壳与兰台同版本号体系（第三段 +1）。
- **壳目录内 `lantai.exe` 与 `--server` 模式保留**：壳拉起服务依赖；同时兼作调试/直跑入口（运行说明保留其用法）。
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
- **变更实施过程中必要的文本必须保存到文档**（方案/结论/中间记录写入 docs/ 与变更记录，不留存于会话）；实施完成后先交付说明（变更登记、版本同步、自测结论），**不自动构建发布、不自动 git 提交**。
- **测试后提交前等待确认（CH-049/CH-054）**：变更完成并自测通过后，先登记 CH、同步版本号与文档、完成自测并交付说明；**等待用户明确确认后再 git 提交推送，并随即执行 `scripts/build_release.ps1` 构建发布**（release 目录与 zip），发布后汇报。
- **文档同步前置（CH-062，用户指示）**：版本号 / CH / API 说明文档 / 测试方案 / README 等文档同步必须在交付说明（等待提交）之前全部完成；等待提交期间不遗留任何文档工作，用户确认后只执行提交 + 构建发布。
- **GitHub Release 手动发布（CH-055）**：release 构建产物（zip）由用户手动发布到 GitHub Releases（首个 v0.1.30 已建）；agent 不自动创建 GitHub Release。

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
9. **分类表核对（0.1.38 审核 M1 教训，CH-074；0.1.43 审核 M1 升级，CH-087）**：技术对接方案 §4.3 分类表/风险对策表/注释必须反映本期新机制（落地状态而非"评估/备选"表述），杜绝机制行漏补（曾连续多轮漏网）。**每次登记 CH 时必答自查项「该变动是否影响 §4.3 分类表/技术栈表？是→已同步修改 / 否」**——把记忆义务变为登记模板字段（0.1.43 审核 M1 即在表格 NL 落地轮再次漏网，故升级为硬性检查点）

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

## 状态（截至 2026-08-24）

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
- ✅ 已执行：0.1.21（用户报告后修复，CH-040）：**壳终端按钮遮挡输入区**——终端浮层按钮固定在窗口右下角遮挡兰台"提问"按钮；修复：输入区 `.chat-composer` 右侧留 88px 占位（padding-right），浏览器直开同样留白保持一致。
- ✅ 已登记：**发布单轨决策（CH-041/R121）**：0.1.22 起只发布 lantai-shell（壳 + 服务一体），不再单独发布服务版目录/zip；壳目录内 lantai.exe 与 `--server` 保留（壳依赖 + 调试直跑入口）；历史双轨（0.1.1~0.1.21）保留可回滚。
- ✅ 已执行：0.1.22（用户确认整改方案后实施，CH-042）：**v0.1.21 评审整改**——H1 字节切片 panic / H2 keep-alive 端口竞态（高危）；S-M1~S-M7（前台代理、设置透传、失败扫描仅 Boot、白名单收窄 8000、stop 重试、iframe url 更新、下载文件名净化）；文档 M3~M5、L1~L6；**单轨发布首版**。
- ✅ 已执行：0.1.23（用户提出后实施，CH-043）：**终端标题栏版本标识**——「兰台终端 · vX.X.X」来自 Rust `CARGO_PKG_VERSION`（编译期常量），经 state 下发前端渲染，升版自动同步。
- ✅ 已登记：**开发过程单轨化（CH-044）**：release 下不保留服务版目录（0.1.22/0.1.23 中间产物已清理）；发布固化为一键脚本 `scripts/build_release.ps1`（PyInstaller → 组装 → 清理 → zip → 发行物校验）。
- ✅ 已执行：0.1.24（用户提出后实施，CH-045）：**README 首次使用引导完善 + MIT 许可证**——「首次使用三步」补智能体配置明细（7 组模型用途/默认值/必须项）；新增 LICENSE（MIT，开放不限制），发布物随附；项目已推送 GitHub（https://github.com/awardat/lantai，公开，main 分支）。
- ✅ 已执行：0.1.25（用户报告后修复，CH-046）：**壳内会话 cookie 丢失**——壳 iframe 跨站上下文 SameSite=Lax cookie 被 WebView2 拒绝；修复：**双通道会话**（verify 返回 session token + localStorage + `X-Lantai-Session` 请求头；后端 header 优先、cookie 兼容）；CDP 实测壳内登录全链路通过。
- ✅ 已执行：0.1.26（用户报告后修复，CH-047）：**Token 复制失败**——壳内跨站 iframe 中 navigator.clipboard 受 Permissions Policy 限制；修复：前端复制降级链（execCommand 兜底）+ 壳自动允许 CLIPBOARD_READ_WRITE 权限。
- ✅ 已执行：0.1.27（用户提出后实施，CH-048）：**监听地址参数化**——`run.py` 新增 `--host`（默认 127.0.0.1 不变），远程/局域网访问测试 `lantai.exe --host 0.0.0.0` 即可，无需改代码重打包。
- ✅ 已登记：**发布需确认（CH-049）**：必要文本保存到文档（不留存于会话）；变更实施完成后先交付说明（变更登记/版本同步/自测结论），**不自动构建发布**；用户确认"发布"后再构建 release 与 zip，再 git 提交推送。
- ✅ 已登记：**等待点前移（CH-054，修订 CH-049）**：测试后提交前等待——变更完成并自测通过后交付说明，**不自动 git 提交、不自动发布**；用户确认后 git 提交推送并随即构建发布（一次确认完成提交+发布）。
- ✅ 已执行：0.1.28（用户报告后修复 + 评审整改，CH-050/CH-051）：**拖放上传失效**——wry/WebView2 默认禁用 OS 文件拖放，壳 `.drag_and_drop(true)` 显式开启（CDP 模拟验证前端逻辑正常）；上传数量确认无限制；v0.1.27 评审整改（M1/M2/M3/L1/L2，L3~L6 沿用延后）。
- ✅ 已执行：0.1.29（0.1.28 拖放修复未生效后继续修复，CH-052）：wry 注册 drag drop handler 时 `SetAllowExternalDrop(false)` 接管拖放、页面收不到 HTML5 drop；修复：保留 `.drag_and_drop(true)` + **`.disable_drag_drop_handler()`**（tauri 官方：Windows 前端用 HTML5 拖放必须禁用该 handler）；E2E 无回归，真机拖放待用户验证。
- ✅ 已执行：0.1.30（用户提出后实施，CH-053）：**常见办公文档支持**——白名单新增 doc/wps/xls/xlsx/ppt/pptx（office 组）；解析：olefile（doc/wps OLE2 UTF-16LE 段提取）、xlrd（xls）、openpyxl（xlsx）、python-pptx（pptx 文本框/表格/分组）；ppt 无纯 Python 提取（提示）；解析器全容错；Mock 全链路回归通过。
- ✅ 已执行：0.1.31（用户查日志发现后修复 + 评审整改，CH-056/CH-057）：**未登录时轮询解析状态 401 刷日志**——首页轮询无条件调用需会话的 `/api/settings/parse`；修复：仅「设置→解析」Tab 可见且已登录时刷新；实测未登录轮询 0 次 401；v0.1.31 评审整改（L1 技术对接方案分类表/技术栈、L2 API 白名单/错误示例、L3 README 用途、L4 测试方案 TC-021b~d，0 代码 bug）。
- ✅ 已执行：0.1.32（用户确认 Ox 全量审核整改，CH-058）：H1 并发缩容后上调失效、H2 Office 预览必 500、H3 壳关闭对话框分支反转、H4 发布脚本陈旧默认版本（必填+断言）；M7 spec 入库、M8 zip 校验加强、M2 Tab 判断修正、M4 解析幂等；D1~D3/L15/L16 文档同步；M1/M3/M5/M6、L1~L14 延后。
- ✅ 已执行：0.1.33（用户提出后实施，CH-059）：**供应商新增小米 MiMo**——官方 OpenAI 兼容端点 `https://api.xiaomimimo.com/v1`、推荐 `mimo-v2.5-pro`（chat/vision，1M 上下文）、无 embedding（提示替代）；README 同步。
- ✅ 已执行：0.1.34（用户提出后实施，CH-060）：**文档清单状态筛选（全部/已就绪/排队中/解析中/失败）+ 失败原因悬停（escAttr 转义）+ 失败重试**（`POST /api/docs/{id}/retry` + 失败行重试按钮）；实测重试链路通过。
- ✅ 已执行：0.1.35（用户确认 Ox-v0.1.34 评审整改，CH-062）：L1 上传 415 文案由 `ALLOWED_EXTS` 动态生成（补 6 种 office 扩展名）；L4 retry"校验+置 queued"合并 store 层原子条件 UPDATE（并发重试不双入队）；D1~D3 文档同步（技术对接方案 §6.1/测试方案 TC-125~127/README 功能一览）；L2/L3（Cargo.lock、requirements 注释头）按 CH-061 规则不计评审项，随版本同步义务刷新；流程固化：**文档同步须在等待提交前完成**（CH-062）。
- ✅ 已执行：0.1.36（用户提出后实施，CH-063）：**失败文件手动指定文件类型重试**——失败行新增类型下拉（按原类型 + 全白名单扩展名），`POST /api/docs/{id}/retry` 可选 body `{"ext":".docx"}`（白名单校验、自动更新 ext/category 后按新类型重新解析；不传行为不变）；实测伪装 .ppt（实为 docx）→ 指定 .docx → 解析成功。
- ✅ 已执行：0.1.37（用户确认四项合并修复 + 文件计数/审核整改，CH-064~068）：**① CH-064** 壳终端标题版本号未同步——`build_release.ps1` 内置壳 release 构建（[1/7] cargo build --release，不再依赖手工前置），发布物壳 exe 版本始终同步；**② CH-065** 失败重试类型下拉改为**文件大类**（文本/Office/文字 PDF/图片 PDF·OCR/图片），识别问题手工兜底，retry 可选 body `{"category":...}`（与 ext 互斥，大类联动扩展名 pdf→.pdf、image→.png、text→.txt）；**③ CH-066** 视觉 400"仅支持 jpg\bmp\webp\gif\png"——GBT 20519 PDF 内嵌 23 张 TIFF 所致，发送前 Pillow 探测并按需统一转码 JPEG（`normalize_image_for_vision`，覆盖 OCR/图片描述/页内图三处）；**④ CH-067** agent 日志失败分支改记 `_friendly_error`（含上游响应体前 200 字符，非 httpx 通用文案）；**⑤ CH-068** 文件管理筛选按钮实时显示各状态文件数（全部/已就绪/排队中/解析中/失败，轮询联动）+ 审核报告 v0.1.37 L1 整改（技术对接方案补 MiMo/TIFF 转码/category 大类）。
- ✅ 已执行：0.1.38（用户确认五项一并做，CH-069~073 + 审核整改 CH-074）：**① CH-071 Dify 外部知识库 API**——新增 `POST /api/external/retrieval`（Dify External Knowledge API 协议：Bearer 鉴权复用设置页 API token、`{knowledge_id,query,retrieval_setting}` → `{records:[{content,score,title,metadata}]}`、knowledge_id 暂不细分、检索复用 `retriever.retrieve`）；**② CH-070 矢量 PDF 整页渲染 OCR 兜底（pymupdf，R110 落地）**——`pdf_render_page_images` 整页渲染 PNG，`_ocr_pdf` 位图 0 时回退（矢量描摹 PDF 商用密码条例实测解析成功，GBT TIFF 路径回归不变）；**③ CH-069 渲染也失败时明确提示**"该 PDF 无内嵌位图且无法整页渲染…请提供位图版文件"；**④ CH-072 pdfminer 打开非标 xref PDF 失败回退 pypdf**——`pdf_text_layers` 捕获异常（国办发 2014 6号 PDF 曾预览 500"No /Root object!"）→ pypdf 逐页提取，解析 ready + 预览 200；**⑤ CH-073 OCR 扫描件文本层字间空格规整（方案 A）**——`chunker.clean_ocr_spacing` 删 CJK 字间空格/换行碎片（英文间距保留），接入入库归一与 pdf_text_layers 全部产出，国办发 PDF 入库/预览零残留；**⑥ CH-074 v0.1.38 审核整改**——技术对接 §4.3/:153/:335 改"整页渲染已落地"口径并补三行机制、`_pypdf_page_text` reader 复用（L1）、AGENTS 自测清单固化"分类表核对"；requirements 新增 `pymupdf>=1.28`。
- ✅ 已执行：0.1.39（用户提出并确认实施，CH-075）：**混合检索（R107）+ 可选重排（R106）+ embedding 降级**——① BM25：SQLite **FTS5 + 中文 bigram** 索引（`chunks_fts` 零新依赖，add/clear/delete 同步、schema v3 回填）；② hybrid：`retriever` 向量 ∪ BM25 经 **RRF** 融合（单路自动退化）；③ 降级：embedding 故障自动 BM25 关键词检索（不再 502）；④ 重排（默认关）：设置页「重排」组（enabled 开关+模型），`llm.rerank`（/v1/rerank）交叉编码器精排，失败容错回退；mock 增 /v1/rerank；实测中文子串命中/RRF/开关切换/断线降级全通过；**⑥ CH-076 审核整改**——`clear_chunks` FTS 清理顺序修正（防重解析孤儿 FTS 行累积）、score 统一 sigmoid 归一 0~1（M2 方案 A：向量/BM25/rerank 同量纲保外部契约）、API 说明文档升 V1.37、维度不一致异常不再静默降级（保留 502 中文自救指引）。
- ✅ 已执行：0.1.40（用户确认两项一起修并直接提交构建，CH-077/CH-078）：**① CH-078 rerank 候选池提前截断缺陷**（用户实测"什么法律要求进行等级保护"top_k=5 不见《网络安全法》、top_k=20 时第 1）——`retriever` **RRF 融合改固定候选池 RECALL_TOP=20**，rerank 对候选池精排后再截取 top_k（未启用 rerank 行为不变）；实测 top_k=5 + rerank 法律文档进 sources 第 1；**② CH-077 `--host 0.0.0.0` 启动横幅更正**——不再打印不可访问的 `http://0.0.0.0:8000`，改"已监听所有网卡 + 本机/局域网双地址提示"。
- ✅ 已执行：0.1.41（用户选定方案 A + 日志改进，CH-079/CH-080）：**① CH-079 检索查询改写（方案 A）**——`retriever.retrieve` 前置 LLM 改写（chat 槽位，口语问题→检索友好查询，补"法律依据/规定/制度"上位概念，解决"什么法律要求等级保护"类问题召回不到《网络安全法》），失败/超时/未配置回退原问题；改写调用进 agent log（query_rewrite 槽位）；**② CH-080 rerank 接入 agent_log**（slot=rerank：query/候选数/top_n/结果/耗时/失败原因），实测 agent 日志含 rerank 行。
- ✅ 已执行：0.1.42（用户选定 A+B，CH-081）：**改写稳定化 + 默认召回扩宽**——A `_rewrite_query` 强制 temperature=0.0（同一问题改写结果稳定，消除"时灵时不灵"）；B `DEFAULT_TOP_K` 5→8 + 前端提问 top_k 同步（法律/长尾文档在 top-5~8 边缘时稳定进资料）；不做 C。
- ✅ 已执行：0.1.43（用户确认实施，CH-084 + 审核整改 CH-087）：**Office 表格转自然语言分块**——`filetype._table_to_nl`：首行作表头、数据行转"表名：表头为值，…"一句（纯规则零 LLM 防幻觉），接入 xlsx/xls/docx/pptx 四类解析，数字/指标类检索精准命中（投研报告 V3 方案借鉴）；**CH-087 整改**——技术对接分类表补表格 NL 机制（M1，CH 登记必答"分类表受影响"流程升格为硬性检查点）、TC-147 不规则表用例（L1）、**xlsx 百分比/日期按 number_format 转换、xls 日期按 ctype 转换**（L2 + 用户提出）。
- ✅ 已执行：0.1.44（用户确认实施 CH-085 并提供调查表样本，CH-085 + 审核整改 CH-088）：**电子 PDF 表格结构化**——`filetype.pdf_extract_tables_nl`（pdfplumber>=0.11.10）：lattice/text 双策略选非空单元最多表单；单元格内换行终止符合并（①，英文跨段补空格）；跨页表头重复（模式 A 丢弃）/列数+节标题接续（模式 B 沿表头表名）、节标题变化=新表；跨页行打断逐列拼接（③）；键值表（2~4 列）"标签为值"（奇数宽度末列落单成句）、列式表（≥5 列）"表头为值"；目录页/None 过滤；表格 NL 按页附加（预览入库同路径）；样本（35 页调查表）260+ NL 行、E2E ready；**CH-088 审核整改**——kv 丢末列修复、"第N页表格"回退名误接续收紧；已知局限（竖排 label 切列等）登记。
- ✅ 已执行：0.1.45（用户提出 A+C 方案、C 改为一次性脚本，CH-089）：**文档重新解析**——A `POST /api/docs/{id}/reparse`（任意非 parsing 状态：清旧切片含 BM25 同步 → 置 queued → 入队；ready 也允许）＋前端 ready 行「重新解析」按钮；B 一次性脚本 `scripts/reparse_all.py`（遍历 ready/failed 调 reparse 接口，--host/--ids；上传逻辑与重名语义不变）；实测 reparse 替换切片 ✅、脚本批量入队 ✅。
- ✅ 已执行：0.1.46（用户提出，CH-090）：**本地 OCR（Tesseract）可选通道**——设置页「图片 PDF（OCR）」新增「使用本地 OCR」开关（AiItem.local_ocr）；`pipeline._ocr_image_tesseract`（chi_sim+eng，探测 PATH/常见路径/`TESSDATA_PREFIX`/用户级 tessdata，PIL 转 PNG 进程调用）；缺 Tesseract/chi_sim 时失败附安装指引；README「本地 OCR」安装方法 A；实测中文图 OCR ✅、图片 PDF local_ocr=true 解析切片 `【第 1 页】网络安全等级保护测评表` ✅；分类表 §4.3 pdf_image 行已补（CH-087 必答=是→改）。
- 📋 已登记待处理（CH-091，v0.1.46 审核 L1，用户"加入队列下次修"）：`_ocr_pdf` 本地 OCR 页循环补 try 容错（TimeoutExpired/PIL 异常转中文 RuntimeError，对齐 `_ocr_pdf_pages`）；备查：agent_log ocr_local 槽位、chi_sim 单语言回退。
- 📋 备忘（CH-086，queue）：**投研 Agent 方案借鉴**——双引擎分离（计算 Python/推理 LLM）、轻量知识图谱 NetworkX（引用/依赖关系）、结构化溯源（source/page/field）、MCP 按分析场景封装；表格不进 Embedding 已由 CH-084 应对。
- ⏳ **等待用户确认**后再进入后续迭代（RBAC、多平台、Docker、档位 3 等均只入需求与文档）。

## 会话注意事项

- 用户在意：先讲方案/文档、等确认；**任何代码执行前必须等待用户明确确认**，不擅自扩大范围。
- 演示规模：几十~几百切片，不需要 GPU/分布式。
- 需要管理员权限的安装（如 Ollama 等）由用户手工执行（winget 命令见 README / 开发环境要求）。
