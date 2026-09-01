# Changelog

本文件记录兰台（lantai）本地 RAG 知识库的重大变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与[语义化版本](https://semver.org/lang/zh-CN/)。

- **Added**：新增功能
- **Changed**：变更/改进
- **Fixed**：缺陷修复
- **Security**：安全
- 版本号规则：每次变更第三段 +1（0.1.1 → 0.1.50）；发布单轨 `release/lantai-shell-0.1.x-windows-x64/`（壳 + 服务一体绿色便携版，随附 zip）。

使用的标记约定：`半角空格、破折号开头`；条目按用户价值描述，不是代码细节。

---

## [Unreleased]

计划中（已登记，待实施）：

- Added：兰台 MCP Server（标准工具协议，Claude/Dify 等客户端可检索问答；含 UI 开关/安装到 agent/卸载）— CH-095
- Added：S3 存储支持（企业应用备忘）— CH-096

## [0.1.50] - 2026-08-28

### Fixed

- 文档清单**翻页/筛选被轮询覆盖**：解析队列轮询不再把列表覆盖回全量（筛选与页码在轮询期间保持）— CH-097
- 技术对接方案 R110 专用 OCR 引擎口径更正（Tesseract 已部分落地 / PaddleOCR 仍评估）— CH-098

### Changed

- 归档 MCP-Server 细化方案（`docs/02-方案设计/MCP-Server方案.md`）与 S3 企业应用备忘

[0.1.50]: https://github.com/awardat/lantai/compare/v0.1.49...v0.1.50

## [0.1.49] - 2026-08-28

### Added

- **文档清单分页**：每页 20/50/100（默认 20），状态筛选服务端化、全量计数，删除/筛选/轮询联动、页码越界自动回退 — CH-094
- **启动自动清理孤儿切片**（文档已删但切块残留的历史脏数据；实测 2 万+ 条清零）

### Fixed

- **删除一致性**：切片删除收敛唯一出口（clear/delete/reparse 三路径一致，chunks 与 BM25 索引同步清除）— CH-094

[0.1.49]: https://github.com/awardat/lantai/compare/v0.1.48...v0.1.49

## [0.1.48] - 2026-08-28

### Added

- **本地 OCR 结果进智能体日志**（`slot=ocr_local`：识别文字、耗时、成功/失败均可查）— CH-093

### Fixed

- OCR 噪声清洗对"多空格分隔行"的误杀（Tesseract 常见输出），此前会致正常页解析失败

[0.1.48]: https://github.com/awardat/lantai/compare/v0.1.47...v0.1.48

## [0.1.47] - 2026-08-28

### Added

- **OCR 噪声清洗 + 切片去重**：公式/水印类扫描件的噪声伪文本不入库、同文档重复段落去重（案例切片 163 → 22，重复归零）— CH-092

### Fixed

- 本地 OCR 单页超时/解码失败不再中断整份解析（坏页跳过）— CH-091

[0.1.47]: https://github.com/awardat/lantai/compare/v0.1.46...v0.1.47

## [0.1.46] - 2026-08-28

### Added

- **本地 OCR（Tesseract）可选通道**：设置页「图片 PDF（OCR）」可勾选「使用本地 OCR」——扫描件离线识别（中文 chi_sim+eng）、免云端免费用；README 附安装方法 — CH-090

[0.1.46]: https://github.com/awardat/lantai/compare/v0.1.45...v0.1.46

## [0.1.45] - 2026-08-27

### Added

- **文档级「重新解析」**：已就绪文档可按当前方法重造切片（版本升级后老文档升级产物，不产生重复文档）— CH-089
- **全库重解析脚本** `scripts/reparse_all.py`（一键把所有文档按当前方法重解析）

[0.1.45]: https://github.com/awardat/lantai/compare/v0.1.44...v0.1.45

## [0.1.44] - 2026-08-27

### Added

- **电子 PDF 表格结构化**：表格提取转自然语言分块（有线框/无框线调查表类），含单元格换行合并、跨页表头接续、跨页文字打断拼接 — CH-085

[0.1.44]: https://github.com/awardat/lantai/compare/v0.1.43...v0.1.44

## [0.1.43] - 2026-08-27

### Added

- **Office 表格转自然语言分块**：xlsx/xls/docx/pptx 表格"表头为值"逐行入库，数字/指标类检索精准命中（投研报告 V3 方案借鉴）— CH-084

### Changed

- Excel 单元格格式识别：百分比按 number_format、日期按 ctype 转换展示 — CH-087

[0.1.43]: https://github.com/awardat/lantai/compare/v0.1.42...v0.1.43

## [0.1.42] - 2026-08-27

### Changed

- 检索查询改写结果稳定化（温度归零）、默认召回扩宽（top_k 5 → 8）——法律/规范类问题答案稳定命中《网络安全法》 — CH-081

[0.1.42]: https://github.com/awardat/lantai/compare/v0.1.41...v0.1.42

## [0.1.41] - 2026-08-27

### Added

- **检索查询改写**：提问自动改写为检索友好查询（法律依据/规定/制度等上位概念），解决语义层级问题召回不足 — CH-079
- **重排调用进智能体日志**（slot=rerank：候选/耗时/结果/失败原因可查）— CH-080

[0.1.41]: https://github.com/awardat/lantai/compare/v0.1.40...v0.1.41

## [0.1.40] - 2026-08-27

### Fixed

- **重排候选池提前截断**：小 top_k 时法律/长尾文档被 RRF 提前挤掉、重排鞭长莫及——候选池固定 20 再精排 — CH-078
- `--host 0.0.0.0` 启动横幅误导（不再显示不可访问的 0.0.0.0 地址）— CH-077

[0.1.40]: https://github.com/awardat/lantai/compare/v0.1.39...v0.1.40

## [0.1.39] - 2026-08-27

### Added

- **混合检索**：BM25 关键词（内置全文索引，中文子串匹配）+ 向量语义两路召回，RRF 融合 — R107
- **可选交叉编码器重排**：设置页「重排」开启后精排（支持硅基流动 bge-reranker-v2-m3 等）— R106
- **embedding 断线自动降级**：关键词检索兜底，问答不中断 — CH-075

### Fixed

- 删除/重解析后 BM25 索引残留、score 三种量纲混排、维度不一致被静默降级 — CH-076

[0.1.39]: https://github.com/awardat/lantai/compare/v0.1.38...v0.1.39

## [0.1.1] ~ [0.1.38] - 2026-08-22 ~ 2026-08-26

早期版本合并概览（详细见 `docs/03-增长迭代/版本记录.md` 与各审核报告）：

- Added：文档上传/解析/检索/流式问答/对话历史、按文件类型 AI 配置、API token、源文件 Web 预览、设置项（0.1.1~0.1.5）
- Added：PDF 文本层几何排序提取、混合 PDF 自动 OCR、浏览器原生预览、智能体日志（0.1.8~0.1.10）
- Added：批量上传与解析队列、常见办公文档支持（doc/wps/xls/xlsx/ppt/pptx）、失败重试（0.1.18/0.1.30/0.1.34/0.1.36）
- Added：桌面壳（Tauri 2 绿色便携版）、发布单轨、Dify 外部知识库 API、矢量 PDF 整页渲染 OCR 兜底、pdfminer 容错回退、OCR 字间空格规整（0.1.19~0.1.38）
- Fixed：壳跨站会话/拖放、图标缓存、依赖与打包一致性、评分可读性等若干缺陷（各版详见审核报告）

---

## Reference Links

- [Unreleased]: https://github.com/awardat/lantai/compare/v0.1.50...HEAD
- 各版本对比链接见对应版本条目（`v0.1.x` tag 随 GitHub Release 创建后有效）

**生成时间**: 2026-08-28 ｜ 依据：Keep a Changelog 1.1.0 / SemVer ｜ 项目约束：工作区根仅允许 AGENTS.md 与 README.md，故本文件置于 `docs/03-增长迭代/`