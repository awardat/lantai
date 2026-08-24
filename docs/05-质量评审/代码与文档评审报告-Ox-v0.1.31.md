# 兰台 v0.1.31 代码与文档综合评审报告（Ox）

| 项目 | 内容 |
|------|------|
| 评审对象 | 兰台（lantai）本地 RAG 知识库 v0.1.31 工作区变更（未提交，含桌面壳 lantai-shell） |
| 评审范围 | backend/app/ 全部源码、frontend/ 三文件全量、shell/src-tauri 全部 Rust 源码（8 文件）+ capabilities + ui、scripts/（build_release.ps1 / mock_ai_server.py 等）、docs/ 全部文档；回归验证 v0.1.31 报告 L1~L4 整改 |
| 评审方式 | 子代理分域深读 + 全部关键发现逐条人工复核（行号级核实）+ git diff / git ls-files 实证 |
| 评审口径 | **本轮为全量深度审核**：首次对壳工程 Rust 源码逐文件精读、后端与前端全量复审；区别于此前各轮以当版增量为焦点的审核，问题数上升主要来自历史遗留首次暴露，不代表质量趋势恶化 |
| 评审时机 | 发版前审核（0.1.31 变更已完成待确认提交；上一已发布版本 0.1.30） |
| 生成时间 | 2026-08-24 |
| 结论 | 上轮 L1~L4 整改全部到位；CH-056 未登录 401 已修复但"Tab 可见"条件无效（M2）。本次新发现 **0 严重、4 高危、8 中危、19 低危**（含 3 项文档滞后）。高危集中在：解析并发缩容失效、Office 新类型预览必 500、壳关闭对话框分支反转、发布脚本陈旧默认版本 |

---

## 一、上轮（v0.1.31 报告）问题回归验证

| 编号 | 问题 | 整改状态 | 证据 |
|------|------|:---:|------|
| L1 | 技术对接方案 §4.3 分类表 / §2 技术栈未补办公文档 | ✅ 已修复 | 本轮 diff 确认两处均已补（olefile/xlrd/openpyxl/python-pptx + 各扩展名解析方式） |
| L2 | API说明文档白名单与错误示例未补新增扩展名 | ✅ 已修复 | §2.1 白名单与 415 错误示例均含 `.doc .wps .xls .xlsx .ppt .pptx` |
| L3 | README 用途行未补新增扩展名 | ✅ 已修复 | 用途行已含全部新扩展名，功能一览升 v0.1.31 |
| L4 | 测试方案无办公文档用例 | ✅ 已修复 | TC-021b（xlsx）/TC-021c（doc/wps 含损坏容错断言）/TC-021d（pptx 与 .ppt 提示）已补 |

**回归结论**：上轮 4 项低危全部整改到位。

---

## 二、0.1.31 变更实现质量

变更内容：CH-056 轮询 401 修复（frontend/app.js 一处）+ CH-057 文档整改（上轮 L1~L4）+ 版本号五处同步（config.py / README / shell 三处）。

| 项 | 评估 |
|----|------|
| 未登录 401 刷日志 | ✅ 已修复：`app.js:190` 登录态检查（`localStorage.lantai_session`）生效，未登录时 0 次调用 `/api/settings/parse`；设置浮层关闭/门禁态也被 `closest(".hidden")` 正确拦截 |
| 「仅解析 Tab 可见时刷新」 | ❌ 条件无效（详见 M2）：`.stab-body` 的显隐走 `display:none/.active`（style.css:238-239），从不携带 `.hidden` 类，`closest(".hidden")` 判不出当前是否停在「解析」Tab |
| 版本号同步 | ✅ 五处主体一致（config.py / README / package.json / Cargo.toml / tauri.conf.json 均 0.1.31）；遗漏两处见 L15/L16（Cargo.lock、requirements 注释头） |
| CH 登记 | ✅ CH-056/CH-057 已登记，版本记录 0.1.31 行完整 |

---

## 三、本次新发现问题

### 🔴 严重

**无。**

### 🟠 高危（4 项）

**H1. 解析并发下调后再上调永久失效——死线程残留 `_WORKERS` 列表**
`backend/app/task_queue.py:51`（`ensure_workers` 以 `len(_WORKERS)` 比较）、`:57-70`（`set_concurrency` 缩容只投 `None` 哨兵让线程退出，`:67-69`，但不从列表移除）。复现：并发 10 → 改 1（9 个线程退出但 `len(_WORKERS)` 仍为 10）→ 再改 10：`n > cur` 不成立，不补建 worker，实际并发恒为 1，直到进程重启。「设置→解析」的并发调整是 0.1.18 正式交付特性，此为确定性缺陷。建议：比较前过滤 `t.is_alive()`，或缩容时同步移除退出线程。

**H2. Office 预览不分类型一律走 parse_docx——xls/xlsx/pptx/doc/wps 点预览必然 500**
`backend/app/routers/docs.py:99-101`：`category == "office"` 分支硬编码 `filetype.parse_docx(file_path)`，忽略 `doc["ext"]`。0.1.30 新增的 6 类办公文档解析正常，但预览时 python-docx 对非 docx 文件抛异常 → 全局处理器返回 500（且把异常串透出给前端，叠加 L5）。100% 复现，属 0.1.30 功能直接缺口（测试方案 TC-021b~d 只覆盖了解析未覆盖预览）。建议：改用现成分发器 `filetype.parse_office(file_path, doc.get("ext",""))`，`.ppt` 空结果给出明确提示。

**H3. 壳关闭确认对话框分支反转：「保持运行」实际杀服务，「结束服务」实际保活**
`shell/src-tauri/src/server.rs:708`（`if ask_end_service(app) { kill_by_port; return; }`）对照 `:793-796`（`OkCancelCustom("保持运行", "结束服务")`——OK 位即「保持运行」，插件 `blocking_show()` 点击 OK 返回 true）。结果：用户点「保持运行」→ 服务被杀；点「结束服务」（或关闭对话框）→ 前台树被杀后另起 detached 服务继续驻留后台。与函数自身 doc 注释（`:783`「返回 true = 保持后台运行」）及 DEVELOPMENT.md 描述双双相反。建议交换分支；修复后必须真机回归两种选择（含 ESC 关闭对话框分支）。

**H4. build_release.ps1 默认 `-Version "0.1.23"` 陈旧——无参运行会删除并以旧版本号错标重建发行物**
`scripts/build_release.ps1:6`（param 默认值）+ `:17-20`（先删 `$dst/$zip` 后构建）。当前已是 0.1.31，若有人不带参数直接运行：会**删除现有 `release/lantai-shell-0.1.23-windows-x64/` 目录与 zip**，再用当前代码重建并打包成 `*0.1.23*` 名字——版本错标的发行物 + 破坏可回滚历史产物。建议：改为必填参数（`[Parameter(Mandatory=$true)]`），并在构建前断言与 config.py/Cargo.toml/tauri.conf.json 三处一致。

---

### 🟡 中危（8 项）

**M1. esc() 不转义引号，属性上下文系统性误用（XSS 族）**
`frontend/app.js:50-54`：textContent→innerHTML 只转义 `& < >`，引号原样保留；凡 `"${esc(...)}"` 进双引号属性即可逃逸。受影响插值点共约 11 处属性位（app.js:252、262、316、473、475、592、598、606、610、708 等）。**可利用性修正**：主文档名链路已被后端 `sanitize_filename` 阻断（filetype.py:19 将 `"` `\` 替换为 `_`），实际可达向量依次为：① 远端模型清单 `onclick="pickModel('${key}', '${esc(m)}…')"`（app.js:708，恶意/被篡改 AI 端点经 `/v1/models` 返回含 `"` 的模型名即可注入）；② 会话标题/AI 配置字段自注入（316/598/606/610，兼致 DOM 渲染错乱）；③ 失败原因 title（252 ← pipeline.py:136/154，异常串含 `"` 概率低但非零）。文本上下文转义纪律良好无一遗漏，AI 回答流式增量走 textContent 天然免疫。建议：新增 `escAttr()`（补 `"` `'` 转义）用于全部属性位；中期改造为事件委托 + data 属性传参。

**M2. CH-056「仅解析 Tab 可见时刷新」条件无效——登录态任意 Tab 每 2 秒照常轮询**
`frontend/app.js:189-190`：`#parse-status` 位于 `#stab-parse`（index.html:121），其显隐由 `.stab-body{display:none}` / `.stab-body.active` 控制（style.css:238-239），该元素及其祖先在 Tab 切换时不携带 `.hidden` 类；祖先链中只有 `#settings-overlay`/`#settings-body` 使用 `.hidden`。因此已进入配置体后无论停在哪个 Tab 条件都通过。影响：`uvicorn.access` 挂载了同一 FileHandler（main.py:81-84），每次轮询都写访问日志——CH-056 要解决的"刷日志"只解决了未登录一半，登录态开设置仍每 2 秒一行 200 日志。建议：改为判断 `$("#stab-parse").classList.contains("active")` 或 `parseEl.offsetParent !== null`，并同步修正 app.js 注释与 CH-056 描述。

**M3. 前端会话竞态三连**
① 消息串台：`app.js:357-364` 切换会话无请求序号/中止校验，快速连续点击时慢响应的历史消息 append 进后选会话的空白消息区；② 流式标题错挂：`app.js:449-453` 自动命名读取完成时刻的全局 `currentConvId`/`convJustCreated`，流式期间切换/新建会话会把标题写到错误会话，且真正的新会话永远得不到命名；③ Enter 绕过禁用：`app.js:388-390` keydown 直接调 `ask()`，不检查 `btn.disabled`（402-403 仅防点击），流式进行中按 Enter 可叠加第二个请求（双倍消耗上游 token 且同写一会话）。建议：ask() 入口快照局部量 + 增加 `asking` 守卫；加载历史加序号比对。

**M4. 崩溃恢复重解析可能切片重复入库**
`backend/app/task_queue.py:90-95`（重启将 `parsing` 状态文档重新入队）+ `pipeline.py`（`add_chunks` 无前置清理，store.py 纯 INSERT）。若进程在切片入库之后、状态置 ready 之前中断（掉电/强杀），重启重解析后同一文档两份切片并存，检索命中翻倍、分数重复。建议：`process_document` 在 add_chunks 前先 `DELETE FROM chunks WHERE document_id=?`（幂等化）。

**M5. 壳远程页面获全量 IPC 命令面 + boot 直连对端口占用者零身份校验**
`shell/src-tauri/capabilities/default.json`：将 `http://127.0.0.1:8000`/`localhost:8000` 声明为 remote 授权源（windows: main+overlay）；Tauri 2 自定义命令无细粒度 ACL，remote 页面可调用全部注册命令，暴露面包括 `terminal_input`（向 ConPTY 写任意按键 = 以用户身份执行 OS 命令）、`save_settings`（改写 startup_command 并持久化 = 重启驻留）、`open_browser`（无 scheme 白名单）。`server.rs` boot 逻辑对 8000 端口占用者不做兰台特征校验（TCP 可连即直连嵌入 iframe 并授权）：本地低权进程抢占 8000 即可获得上述 IPC 面。本地单机演示下利用前提复杂（需已有本地恶意进程），故定中危而非高危。建议分层缓解：boot/probe 增加兰台特征核对（如已知端点版本字段）；自定义命令做应用级 ACL 拆分，remote 仅保留 zoom；open_browser 加 http/https 白名单。

**M6. 壳 restart 杀树后未等端口释放即喂启动命令**
`shell/src-tauri/src/server.rs:636-650`：`term.kill()` 触发整树终止是异步的，restart 立即 start_session 喂入启动命令；旧监听未释放时新 lantai.exe 绑定失败，且 uvicorn 绑定失败文案（"only one usage of each socket address"）不含 FAIL_PATTERNS 特征（"eaddrinuse" 为 Node 用语），不会快速失败只能等超时。对比 stop() 有等待+兜底、handle_close 有 5s 等待，restart 是三处生命周期操作中唯一无竞态防护者。建议复用 stop 的等待逻辑并补 FAIL_PATTERNS。

**M7. scripts/build/lantai.spec 实际未被 git 跟踪——fresh clone 后一键发布直接失败**
`.gitignore:17` `build/` 将父目录 `scripts/build/` 整体排除，git 不再下探，`:21` 的 `!scripts/build/lantai.spec` 否定规则静默失效（已实证：`git ls-files scripts/build` 为空、check-ignore 命中 `.gitignore:17`）。发布脚本 `build_release.ps1:26` 引用该 spec，新克隆环境发布会报找不到文件。且 `.gitignore:19` 注释声称"spec 已入库"与现实相反。建议：第 17 行改为精确排除（如 `scripts/build/build-work*/`）使 spec 入库，修正注释。

**M8. 发行物校验正则可能漏检（zip 条目分隔符），且未覆盖 logs 与根级 rag.db**
`scripts/build_release.ps1:70`：`$_.FullName -match '/data/|settings\.json'`——PowerShell 5.1 `Compress-Archive` 生成的 zip 条目名使用反斜杠分隔（知名兼容坑），`\data\` 不匹配 `/data/`，data 断言存在漏检可能；硬性条款中的 logs/（实际位于 data/logs，受同一正则覆盖）与独立 rag.db 未显式检查。当前组装流程确实不会引入它们，属纵深防御失效而非现实泄漏。建议：匹配前归一化分隔符（`-replace '\\','/'`），模式扩为 `(^|/)(data|logs)(/|$)|(^|/)rag\.db$`。

---

### 🟢 低危（16 项，均为代码）

**L1.** `GET /api/search` top_k 无下界校验（chat.py:149 裸 `int = 5`）：负值时 store.py:226-227 `k=-5` → `np.argsort(-scores)[:-5]` 返回除末尾外近全库切片。`/api/chat` 有 `ge=1,le=20` 此处遗漏。
**L2.** 非流式 `/api/chat` 空 sources 分支（chat.py:68-73）跳过会话存在性校验直接 `add_message`，无效 conversation_id 产生孤儿消息行；流式路径有 N-M1 预校验（:102-103），行为不一致。
**L3.** schema 未声明任何 FOREIGN KEY（store.py chunks/messages 表），`PRAGMA foreign_keys=ON` 形同虚设；0.1.6 N-L10"启用外键约束"的表述与实际约束力不符，防孤儿完全靠应用层删除顺序。
**L4.** 流式错误路径响应体未读取即 raise（llm.py:156-160），`_friendly_error` 读 `.text` 抛 ResponseNotRead 被吞 → "模型不存在"等基于 body 的友好文案在流式路径永不命中（非流式正常）。
**L5.** 全局异常处理器回显原始异常串（main.py:128 `f"服务内部错误：{exc}"`），可携带绝对路径等内部信息；H2 场景下用户可直接看到 BadZipFile 异常文本。建议对外通用文案、详情入日志（已有 logger.exception）。
**L6.** PBKDF2 迭代次数 10 万（security.py）低于 OWASP 当前建议（≥600k）；单机离线爆破面下偏弱非致命，升到 300k~600k 需保留旧哈希兼容迁移。
**L7.** `chunk_text` 超长段落窗口步长 `chunk_size - overlap`（chunker.py:39）无守卫，`overlap >= chunk_size` 时死循环；当前常量 400/50 安全，属调参即触发的函数级地雷。
**L8.** `read_text_file`（filetype.py:43-51）无 BOM 检测：UTF-16 txt/md 几乎必然 UTF-8 解码失败后落入 gb18030 成功产出乱码入库（gb18030 极少抛错，errors="replace" 兜底不可达）。
**L9.** 登录限流全局单桶固定键（security.py 失败计数）：`--host 0.0.0.0` 下任何人连发 5 次错密码可循环锁死真管理员入口。建议按来源分桶或指数退避。
**L10.** `parse_xls` 日期单元格按 Excel 序数浮点直出（filetype.py:138-148 float==int 转 int），未结合 `book.datemode` 经 xldate 转换，日期列入库为 "45000" 类数字，检索语义损坏。
**L11.** testAi 在自动保存后拿不到已存 Key：自动保存成功置 `aiConfigCache=null`（app.js:663），:696-698 回填分支依赖 cache 非空，此后点"测试"发送空 api_key；后端仅对 `****` 脱敏值替换存储值（settings.py:120-123），空值不替换 → 云端供应商测出 401 误报配置错误。
**L12.** 上传先整读进内存再校验大小（docs.py `file.file.read()`）：GB 级 body 内存峰值等于 body 大小；默认回环部署缓解，配合 `--host 0.0.0.0` 放大为内存 DoS 面。
**L13.** SQLite 连接从不显式 close（store.py `with self._connect()` 只管事务），依赖 GC 兜底；Windows 下滞留句柄会干扰 delete_document 后目录删除（docs.py 以 ignore_errors 掩盖失败）与文件备份。
**L14.** 前端体验合集：SSE error 只 toast、助手气泡永久留空且不 break（app.js:443-445）；流式无 AbortController 不可取消、切会话后台跑完（413-447）；裸 fetch 网络异常提示英文原文绕过中文话术（455-456）；IME 组合期 Enter 误发送（388-390 缺 `isComposing` 检查，zh-CN 高频踩坑）；delta 不跟随滚动（441-442）。
**L15.** 壳工程合集：Cargo.lock 记录 lantai-shell 仍为 **0.1.28**（:1953），系版本号同步清单之外的第 4 处，0.1.29~0.1.31 三次升版均未刷新；`open_browser` 无 scheme 白名单（commands.rs）；download.rs PWSTR 从不 CoTaskMemFree（确定性小泄漏）；apply_proxy_env 多线程修改进程环境变量；devtools feature 未 cfg 区分进生产包；nsis 安装器模板残留与"不建 setup"决策矛盾（bundle.active=false 兜底未产出）；下载兜底命名残留 dsh 品牌（`dsh-session-{id}.zip`）；shell/README.md:7 示例 zip 与 DEVELOPMENT.md:31 版本引用停在 0.1.20。
**L16.** requirements.txt:1 头注释仍标 "v0.1.30"（0.1.31 后端依赖未变，注释滞后不影响正确性，随下版顺手改）。

---

### 📄 文档滞后专项（3 项，并入低危计）

**D1.** API说明文档.md:106（§2.5）preview `type` 枚举只写 `text|image`，缺后端实际返回且前端已在用的 `pdf`（docs.py:115，附 note/raw_url）。
**D2.** API说明文档.md §3.3 会话接口表（:212-213）缺 `PUT /api/conversations/{id}` 重命名端点（conversations.py 已实现、前端 app.js:342/451 在用、技术对接方案.md:198 已记载）。
**D3.** shell/README.md 快速开始示例 zip 版本与 DEVELOPMENT.md「当前版本」停在 0.1.20（见 L15）。

---

### ℹ️ 提示（非问题）

- **版本号同步核对表**：config.py ✅ / README ✅ / shell 三处 ✅ / API说明文档 V1.29↔0.1.31 ✅ / 版本记录 ✅ / **Cargo.lock ❌（0.1.28，L15）** / requirements 注释头 ❌（v0.1.30，L16）。
- **release/ 目录现状符合单轨约束** ✅：服务版产物止于 0.1.21（历史保留合规），0.1.22 起仅 lantai-shell 目录+zip 一一对应，最新 0.1.30；0.1.31 尚无产物，与"测试后等待确认再发布"流程一致。
- **mock_ai_server.py 契约核对通过** ✅：SSE 流式/非流式/embeddings/视觉消息四类与 llm.py、embeddings.py 调用契约一致；建议换 ThreadingHTTPServer（单线程在 DELAY 期间阻塞并发自测请求）。
- **壳单元测试资产质量好**：UTF-8 边界截断、netstat 解析防误命中、代理解析、文件名穿越净化、IPC 往返均有回归测试；注意开发机 GNU 工具链 cargo test 不可用（DEVELOPMENT.md 已记），建议以 MSVC 定期跑一遍防测试腐化。
- **已知取舍知悉即可**：store.search 全表切片载入内存 + argsort 非稳定排序（演示量级无碍）；token last_used_at 每次校验写库（高频写放大）；PDF 解析/预览多轮重复全文提取（大文件性能）；API Key 为演示级 XOR 加密且密钥同库存放（模块 docstring 已自认）；会话 token 双通道下发（Cookie + body 供壳 localStorage）。
- **requirements 一致性核对通过** ✅：直接 import 全部声明（含 pillow/pdfminer.six/olefile/xlrd/openpyxl/python-pptx），间接依赖（lxml/et_xmlfile 等）由 pip 自动安装，打包核验按自测规范执行。

---

## 四、优点

1. **上轮整改闭环干净**：L1~L4 四项文档同步全部到位，CH-056/057 登记、版本记录、五处版本号主体一致，变更管理流程持续规范。
2. **文本上下文 XSS 防护纪律良好**：前端全部文本插值点均经 esc()/textContent，AI 流式增量天然免疫；问题仅在属性上下文的系统性误用（M1）。
3. **壳工程质量基础扎实**：Job Object 单一所有权设计正确、字节切片 panic 修复带回归测试、netstat PID 防误命中、settings.json 原子写、代次+probe_stop 双保险防线程复活，单测覆盖意识明显优于同类演示项目。
4. **后端安全基本功到位**：SQL 全参数化、路径净化+int 路径参数无可达穿越、恒时比较、PBKDF2 结构正确、Authorization 头不入日志、agent_log 图片 base64 占位化、Key 展示脱敏尾 4 位。
5. **连续 11 个版本（0.1.21~0.1.31）交付侧 0 代码 bug 的纪录**虽在本轮全量深挖下被打破（本轮口径不同），但其增量审核方法论对快速迭代仍然有效。

---

## 五、修复优先级建议

| 批次 | 编号 | 说明 |
|------|------|------|
| 第一批（发版前必修） | H1、H2、H4、M7、M8 | 两处确定性功能缺陷 + 发布链三处地雷（陈旧默认值/spec 未入库/校验漏检），改动小、模式现成 |
| 第一批（附真机回归） | H3 | 一行级分支交换，但必须真机回归「保持运行」「结束服务」与 ESC 关闭三种路径 |
| 第二批（尽快） | M2、M1、M3、M4 | CH-056 补完（Tab 判断+注释+登记修订）、escAttr 属性转义、前端竞态守卫、解析幂等清理 |
| 第二批（需拍板） | M5、M6 | 壳安全架构（boot 特征校验低成本先行）与 restart 等待逻辑 |
| 第三批（择机） | D1~D3、L1~L16 | 文档三处顺手修；低危按风险偏好排期，建议优先 L1/L4/L8/L10/L11（行为确定错误类） |

> 本次发版前审核发现 4 项高危，建议完成第一批修复并升版 0.1.32 后再发布。

---

## 六、质量趋势

| 版本 | 严重 | 高 | 中 | 低 | 代码 bug | 备注 |
|------|:---:|:---:|:---:|:---:|:---:|------|
| v0.1.1 | 1 | 1 | 3 | 9 | 是（S1） | 首次评审 |
| v0.1.11 | 0 | 3 | 2 | 12 | 是（H1 NameError） | |
| v0.1.16 | 0 | 0 | 2 | 9 | 否 | 主代码 0 bug |
| v0.1.21 | 0 | 2 | 10 | 18 | 是（shell H1/H2） | shell 新技术栈引入 bug |
| v0.1.27 | 0 | 0 | 3 | 6 | 否 | 含 shell 全量 0 bug |
| v0.1.29 | 0 | 0 | 0 | 2 | 否 | 发版前审核无中高危 |
| v0.1.31（前次，增量口径） | 0 | 0 | 0 | 4 | 否 | 增量审核，聚焦当版变更 |
| **v0.1.31（Ox，全量口径）** | **0** | **4** | **8** | **19** | **是（H1/H2/H3/H4）** | **首次含壳 Rust 逐文件精读的全量深挖** |

**口径说明**：本轮与前次同为针对 0.1.31，但评审深度不同——首次逐文件精读壳 Rust 源码并对前后端全量复审。H1/H2 属 0.1.18/0.1.30 引入但增量审核未覆盖的组合场景，H3/H4/M5~M8 属壳工程与发布链的历史遗留首次系统排查。数字上升反映评审深度而非质量滑坡；高危 4 项均改动小、模式现成，第一批修复后即可恢复收敛。

---

**文档状态**: 评审报告 v1.0（Ox 全量审核，针对应用 v0.1.31 工作区变更，发版前）
**生成时间**: 2026-08-24
**前置报告**: docs/05-质量评审/代码与文档评审报告-v0.1.1.md ~ v0.1.31.md
**说明**: 本报告仅评审，未修改任何被评审文件。全部高危/中危发现均经人工逐条行号级复核（含 git ls-files/check-ignore、Cargo.lock、capabilities 实证）；低危中标注"待验证"泛化性的项（如双栏检测启发式、非常规网关 SSE 多行 data）未计入问题数。
