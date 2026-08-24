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
    args = parser.parse_args()

    url = f"http://{config.DEFAULT_HOST}:{config.DEFAULT_PORT}"
    if not args.server:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        print(f"兰台（lantai）v{config.APP_VERSION} 启动中：{url} （Ctrl+C 退出）")
    else:
        print(f"兰台（lantai）v{config.APP_VERSION} 服务已就绪：{url} （--server 模式）")
    # 直接传应用对象：冻结（PyInstaller）环境下字符串导入不可靠
    uvicorn.run(fastapi_app, host=config.DEFAULT_HOST, port=config.DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
