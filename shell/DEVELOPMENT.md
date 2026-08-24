# 开发文档（lantai-shell）

面向开发者的内容：环境搭建、开发运行、构建打包、调试、架构。用户使用说明见 [README.md](README.md)，原始设计见 [方案.md](方案.md)。

## 环境要求

- Windows 10/11（系统自带 WebView2）
- Node.js ≥ 20、npm
- Rust 工具链（rustup，stable-x86_64-pc-windows-gnu）+ mingw-w64（GCC，位于 `C:\code\dsh-ui\.tools\mingw64`）

> 本机无 Visual Studio/MSVC，采用 **GNU 工具链**。rustup default 已为 `stable-x86_64-pc-windows-gnu`；
> 构建时需把 `mingw64\bin` 加入 PATH。

## 开发运行

```powershell
cd C:\code\lantai\shell
npm run build:ui          # 前端构建（vite → ui/dist）
$env:CARGO_TARGET_DIR = 'C:\code\dsh-ui\src-tauri\target'   # 复用 dsh-ui 编译缓存（可选但强烈建议）
$env:PATH = "C:\code\dsh-ui\.tools\mingw64\bin;$env:PATH"
cd src-tauri
cargo build --release
```

产物：`target\release\lantai-shell.exe`（CARGO_TARGET_DIR 指向 dsh-ui 时在 `C:\code\dsh-ui\src-tauri\target\release\lantai-shell.exe`）。

> **注意**：发布必须 release 构建。`tauri dev`（调试热更）会解析到 vite dev server，需要同时跑 `npm run dev:ui`；壳工程以 release 验证为准。

## 版本号约定

每次功能改动版本号第三段 +1（当前 0.1.19，与兰台本体同版本体系）。同步修改三处：
`src-tauri/tauri.conf.json`、`src-tauri/Cargo.toml`、`package.json`（另：README「更新记录」、本文件、方案.md）。

## 构建绿色便携目录（发布）

```powershell
# 1. 前端 + Rust（见上）
# 2. 组装 release/lantai-shell-<版本>-windows-x64/
#    - lantai-shell.exe（壳）
#    - WebView2Loader.dll（target/release/ 下，webview2-com-sys 构建时生成）
#    - portable.marker（空文件，便携模式标记）
#    - 兰台服务 one-dir 全部内容（lantai.exe + _internal/ + frontend/ 等，来自
#      release/lantai-<版本>-windows-x64/）
# 3. 压缩 zip
```

> 壳与兰台服务同版本号（0.1.19）：壳目录内嵌同版本服务 one-dir，双击 lantai-shell.exe 即单机应用。

## 打包相关坑（沿用 dsh-ui 经验）

1. **WebView2Loader.dll**：构建后检查 `target/release/WebView2Loader.dll` 是否存在（webview2-com-sys
   构建时从 crate 拷贝到 OUT_DIR，tauri 链接需要）；绿色目录必须包含它，否则启动报找不到 WebView2 loader。
2. **换图标后 exe 资源不更新**：`src-tauri/build.rs` 已显式声明 `cargo:rerun-if-changed=icons/icon.ico`；
   改图标后如未生效，touch 一下 `tauri.conf.json` 强制重跑。
3. **GNU 链接警告** `.rsrc merge failure: multiple non-default manifests`：无害，可忽略。
4. **bundle.active=false**：不产生 NSIS setup（兰台规则：不建 setup）；如需安装包再评估（dsh-ui 有
   nsis 模板可恢复）。

## 调试

```powershell
$env:DSH_DEBUG_DEVTOOLS = '1'   # 启动后自动打开主窗口 DevTools + --remote-debugging-port=9222
```

> iframe 是独立 CDP target（OOPIF）：兰台 UI 与 shell 页跨源，WebView2 将 iframe 放入独立进程，
> `/json` 里会出现 `type: "iframe"` 的 target——可直接连接它在 127.0.0.1:8000 同源上下文执行 JS。

## 架构速览

```
src-tauri/src/
├─ main.rs / lib.rs     # 入口；主窗口（WebviewWindowBuilder，标题「兰台」）、单实例、IPC 注册
├─ server.rs            # 生命周期状态机：boot/ready/failed/stopped、HTTP 就绪探测、keep-alive、
│                       # 重启/手动停止（Job Object + 按端口杀兜底）、退出清理
├─ terminal.rs          # ConPTY 会话（portable-pty）：cmd.exe + 进程树 Job Object
├─ zoom.rs              # 缩放（50–300%）：应用/持久化
├─ download.rs          # WebView2 下载支持（下载起始/权限/完成事件）
├─ job.rs               # Windows Job Object（KILL_ON_JOB_CLOSE 退出清树）
├─ settings.rs          # settings.json 读写（默认：lantai.exe --server / 8000）
└─ commands.rs          # IPC 命令层（get_state / terminal_* / zoom_* / restart / stop / settings）

ui/                     # 前端（Vite + 原生 TS + xterm.js），单页面
└─ index.html / shell.ts # 主窗口 shell：iframe 内嵌兰台 UI + 启动遮罩（兰台 logo + 内嵌只读
                          # xterm 实时显示启动输出）+ 右下角终端小按钮 + 终端面板 + 设置弹窗
```

关键行为：

- **单窗口架构**：主窗口 webview 加载 shell 页面，兰台 UI 通过 iframe 加载
  （`http://127.0.0.1:8000/`，该服务无 X-Frame-Options 限制）；右下角固定按钮点击呼出/隐藏
  终端面板。**不创建第二个窗口**——Windows 上第二个 WebView2 窗口的合成不可靠。
- **便携模式**：程序目录存在 `portable.marker` 时，`settings.json` 存程序同目录（绿色便携发布用）。
- **工作目录**：`working_dir` 留空时 = 壳程序所在目录（兰台冻结模式数据目录基于 exe 位置，与 cwd 无关）。
- **就绪判定**：端口 TCP 有监听即「直连」；启动路径以 HTTP 200 为准，终端输出扫失败特征快速失败。
- **退出清理**：应用退出时 Job Object 句柄关闭 → cmd/lantai.exe 整树终止；`keep_alive_on_exit`
  时关闭弹询问框（默认「保持运行」脱离进程，下次启动直连；「结束服务」则按端口杀）。
- **单实例**：`tauri-plugin-single-instance`，双开只唤起已有实例。
- **无 cmd 窗口**：ConPTY 承载 cmd.exe，窗口不可见，输出经 IPC 到前端 xterm.js。

## 已知问题

- **Windows 第二个 WebView2 窗口合成不可显示**：因此采用单窗口 + iframe 架构。
- **GNU 链接警告** `.rsrc merge failure: multiple non-default manifests`：无害，可忽略。
- **`cargo test` 在 Windows GNU 工具链下无法运行**（`0xc0000139 STATUS_ENTRYPOINT_NOT_FOUND`）：
  tauri/webview2 依赖与 test harness 的已知问题（[tauri#11028](https://github.com/tauri-apps/tauri/issues/11028)）。
  单元测试代码已保留（`#[cfg(test)]`），可在 MSVC/CI 环境运行；本机以端到端验证替代。
