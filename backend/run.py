"""发布入口（PyInstaller one-dir 与源码均可运行）。

源码运行：python run.py
编译版运行：release/lantai-0.1.x-windows-x64/lantai.exe
桌面壳模式：lantai.exe --server（不自动开浏览器，由 lantai-shell 壳内拉起）
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn  # noqa: E402

from app import config  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="兰台（lantai）本地 RAG 知识库服务")
    parser.add_argument(
        "--server",
        action="store_true",
        help="服务模式：不自动打开浏览器（供桌面壳 lantai-shell 无窗口拉起）",
    )
    parser.add_argument(
        "--host",
        default=config.DEFAULT_HOST,
        help=f"监听地址（默认 {config.DEFAULT_HOST}，仅本机回环；远程/局域网访问测试可传 0.0.0.0）",
    )
    args = parser.parse_args()

    # CH-077：通配（0.0.0.0/::）不是可访问地址，提示拆分为本机 + 局域网两个地址
    is_wildcard = args.host in ("0.0.0.0", "::")
    base_url = (
        f"http://{config.DEFAULT_HOST}:{config.DEFAULT_PORT}"
        if is_wildcard
        else f"http://{args.host}:{config.DEFAULT_PORT}"
    )
    if not args.server:
        threading.Timer(1.5, lambda: webbrowser.open(base_url)).start()
        print(f"兰台（lantai）v{config.APP_VERSION} 启动中：{base_url} （Ctrl+C 退出）")
    else:
        if is_wildcard:
            print(
                f"兰台（lantai）v{config.APP_VERSION} 服务已就绪：已监听所有网卡（{args.host}）——"
                f"本机访问 http://127.0.0.1:{config.DEFAULT_PORT}，"
                f"局域网/远程访问 http://<本机IP>:{config.DEFAULT_PORT}（cmd 运行 ipconfig 查看本机 IP）"
            )
        else:
            print(f"兰台（lantai）v{config.APP_VERSION} 服务已就绪：{base_url} （--server 模式）")
    # 直接传应用对象：冻结（PyInstaller）环境下字符串导入不可靠
    uvicorn.run(fastapi_app, host=args.host, port=config.DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
