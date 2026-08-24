"""一次性批量改造脚本：dsh-ui 壳 → 兰台壳（品牌/默认值/端口/配置）。
用法：python scripts/rebrand_shell.py
"""
from __future__ import annotations

import io
from pathlib import Path

SHELL = Path(r"C:\code\lantai\shell")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")


def sub(p: Path, pairs: list[tuple[str, str]], must: bool = True) -> None:
    s = read(p)
    for old, new in pairs:
        if old not in s:
            if must:
                raise SystemExit(f"NOT FOUND in {p}: {old!r}")
            continue
        s = s.replace(old, new)
    write(p, s)


# ---------- settings.rs ----------（已处理）

# ---------- download.rs ----------
sub(SHELL / "src-tauri/src/download.rs", [
    ('eprintln!("[dsh-ui] download: no ICoreWebView2");', 'eprintln!("[lantai-shell] download: no ICoreWebView2");'),
    ('eprintln!("[dsh-ui] download: no ICoreWebView2_4");', 'eprintln!("[lantai-shell] download: no ICoreWebView2_4");'),
    ('eprintln!("[dsh-ui] download handler installed");', 'eprintln!("[lantai-shell] download handler installed");'),
])

# ---------- Cargo.toml ----------
sub(SHELL / "src-tauri/Cargo.toml", [
    ('name = "dsh-ui"', 'name = "lantai-shell"'),
    ('version = "0.1.22"', 'version = "0.1.19"'),
    ('description = "DeepSeek Harness desktop shell: embedded cmd terminal + webview wrapper"',
     'description = "兰台（lantai）本地 RAG 知识库桌面壳：内嵌终端 + WebView 包装"'),
    ('authors = ["dsh-ui"]', 'authors = ["lantai"]'),
])

# ---------- main.rs ----------
sub(SHELL / "src-tauri/src/main.rs", [
    ('dsh_ui_lib::run();', 'lantai_shell_lib::run();'),
])

# ---------- tauri.conf.json ----------
sub(SHELL / "src-tauri/tauri.conf.json", [
    ('"productName": "dsh_shell"', '"productName": "lantai_shell"'),
    ('"version": "0.1.22"', '"version": "0.1.19"'),
    ('"identifier": "com.dsh-ui.app"', '"identifier": "com.lantai.app"'),
    ('"active": true,', '"active": false,'),
])

# ---------- package.json ----------
sub(SHELL / "package.json", [
    ('"name": "dsh-ui"', '"name": "lantai-shell"'),
    ('"version": "0.1.22"', '"version": "0.1.19"'),
    ('"description": "DeepSeek Harness desktop shell: embedded cmd terminal + webview wrapper"',
     '"description": "兰台（lantai）本地 RAG 知识库桌面壳：内嵌终端 + WebView 包装"'),
])

# ---------- ui/src/ipc.ts ----------
sub(SHELL / "ui/src/ipc.ts", [
    ('startupCommand: "pnpm dlx @deepseek-ai/dsh@next web --no-open",',
     'startupCommand: "lantai.exe --server",'),
    ('  port: 3080,', '  port: 8000,'),
])

# ---------- ui/src/shell.ts ----------
sub(SHELL / "ui/src/shell.ts", [
    ('let url = "http://127.0.0.1:3080/";', 'let url = "http://127.0.0.1:8000/";'),
    ('Number(cfgPort.value) || 3080', 'Number(cfgPort.value) || 8000'),
])

# ---------- capabilities ----------
sub(SHELL / "src-tauri/capabilities/default.json", [
    ('description": "主窗口与浮层窗口的默认权限；包含对本机 DSH 服务的远程页面 IPC 授权（用于缩放快捷键注入）"',
     'description": "主窗口与浮层窗口的默认权限；包含对本机兰台服务的远程页面 IPC 授权（用于缩放快捷键注入）"'),
])

print("全部替换完成")
