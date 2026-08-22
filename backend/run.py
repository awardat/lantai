"""发布入口（PyInstaller one-dir 与源码均可运行）。

源码运行：python run.py
编译版运行：release/lantai-0.1.x-windows-x64/lantai.exe
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn  # noqa: E402

from app import config  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


def main() -> None:
    url = f"http://{config.DEFAULT_HOST}:{config.DEFAULT_PORT}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"兰台（lantai）v{config.APP_VERSION} 启动中：{url} （Ctrl+C 退出）")
    # 直接传应用对象：冻结（PyInstaller）环境下字符串导入不可靠
    uvicorn.run(fastapi_app, host=config.DEFAULT_HOST, port=config.DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
