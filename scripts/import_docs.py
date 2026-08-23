"""批量导入演示文档（开发自测用）：把指定目录（默认 docs/演示文档/）下的白名单
文件通过上传 API 导入兰台（L6 修复：默认目录不再指向设计文档目录）。

用法：python import_docs.py [目录] [--base http://127.0.0.1:8000]
前置：兰台服务已启动。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import httpx

ALLOWED = {".txt", ".md", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "docs" / "演示文档"


def main() -> None:
    parser = argparse.ArgumentParser(description="导入演示文档到兰台")
    parser.add_argument("dir", nargs="?", default=str(DEFAULT_DIR))
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.exists():
        print(f"目录不存在：{root}\n请把演示文档放入 {DEFAULT_DIR} 或指定目录。")
        return
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in ALLOWED]
    if not files:
        print(f"目录中没有可导入的文件：{root}")
        return
    ok_count = 0
    with httpx.Client(timeout=120) as client:
        for p in files:
            with open(p, "rb") as f:
                resp = client.post(f"{args.base}/api/docs/upload", files={"file": (p.name, f)})
            payload = resp.json()
            if resp.status_code == 200 and payload.get("code") == 0:
                ok_count += 1
                print(f"✅ {p.name}")
            else:
                print(f"❌ {p.name}: {payload.get('message', resp.status_code)}")
    print(f"导入完成：成功 {ok_count}/{len(files)}（解析为异步，稍后在文档管理页查看状态）")


if __name__ == "__main__":
    main()
