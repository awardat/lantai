# """全库重新解析（0.1.45，CH-089/A）——版本升级后把既有文档按当前方法重造产物。"""
# -*- coding: utf-8 -*-
"""全库重新解析（0.1.45，CH-089/A）：遍历 ready/failed 文档逐个调用
`POST /api/docs/{id}/reparse`，让老文档按当前版本方法（如 0.1.44 表格 NL）重新解析。

与上传无关（上传逻辑不变）；源文件保留、doc_id 不变、旧切片被替换，
不会产生"同一文件新旧方法各一份"的重复入库。

用法（服务须已运行，默认 http://127.0.0.1:8000）：
    python scripts/reparse_all.py
    python scripts/reparse_all.py --host http://192.168.19.1:8000
    可选仅重解析指定 id：python scripts/reparse_all.py --ids 1,2,3
"""
from __future__ import annotations

import argparse
import sys

import httpx


def main() -> None:
    ap = argparse.ArgumentParser(description="兰台全库重新解析（按当前方法重造文档切片）")
    ap.add_argument("--host", default="http://127.0.0.1:8000", help="兰台服务地址（默认 http://127.0.0.1:8000）")
    ap.add_argument("--ids", default="", help="仅重解析指定文档 id（逗号分隔），缺省=全部 ready/failed")
    args = ap.parse_args()

    try:
        docs = httpx.get(f"{args.host}/api/docs", timeout=10).json()["data"]
    except Exception as exc:  # noqa: BLE001
        print(f"无法访问 {args.host}/api/docs：{exc}\n请确认兰台服务已运行（lantai.exe --server）。")
        sys.exit(1)

    only = {int(x) for x in args.ids.split(",") if x.strip()}
    targets = [d for d in docs if (d["status"] in ("ready", "failed")) and (not only or d["id"] in only)]
    if not targets:
        print(f"没有可重新解析的文档（共 {len(docs)} 个文档，目标状态 ready/failed）。")
        return
    print(f"文档共 {len(docs)} 个，将重新解析 {len(targets)} 个（ready/failed）：")
    okc = 0
    for d in targets:
        try:
            r = httpx.post(f"{args.host}/api/docs/{d['id']}/reparse", timeout=15)
        except Exception as exc:  # noqa: BLE001
            print(f"  [x] {d['id']} 请求失败：{exc}")
            continue
        if r.status_code == 200:
            okc += 1
            print(f"  [{okc}/{len(targets)}] 已入队 {d['id']}：{d['name'][:42]}（原切片 {d['chunk_count']}）")
        else:
            print(f"  [!] {d['id']} 未入队（{r.status_code}）：{(r.text or '')[:90]}")
    print(f"完成：{okc}/{len(targets)} 已入队，解析队列将按当前方法处理；处理中状态轮询文档列表可查看进度。")


if __name__ == "__main__":
    main()