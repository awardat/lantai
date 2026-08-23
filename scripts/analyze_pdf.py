"""PDF 质量与布局分析工具（开发自测 / 样本诊断用）。

对给定 PDF 输出：
1. 页级文本密度与可读性（乱码字符、替换符）
2. 德文等变音字符/关键词统计（检测"英文字形集 OCR 损坏德文字母"类问题）
3. 页眉页脚模式（跨页重复文本）与页码碎片
4. 流序（内容流顺序）vs 几何序（按 y/x 坐标重排）对比——检测顺序错乱
5. 归一化 x 分布——辅助判断单/双栏

用法：python analyze_pdf.py <pdf路径> [--json <输出路径>]
示例：python analyze_pdf.py ..\sample\Autistic-psychopathy-in-childhood-Hans-Asperger.pdf
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

# 变音字符与常见德文词（可扩展）
DIACRITICS = "äöüßÄÖÜ"
GERMAN_WORDS = ["kindlichen", "Autismus", "kindheit", "Gefühl", "Grundlagen", "für", "über"]


def _blocks_of(page):
    blocks: list[tuple[float, float, str]] = []

    def visitor(text, cm, tm, font_dict, font_size):
        t = text.strip()
        if t:
            blocks.append((round(tm[4], 1), round(tm[5], 1), t))

    page.extract_text(visitor_text=visitor)
    return blocks


def analyze(path: str) -> dict:
    reader = PdfReader(path)
    pages_text = [(p.extract_text() or "") for p in reader.pages]
    full = "\n".join(pages_text)

    stats: dict = {"页数": len(reader.pages), "总字符": len(full)}
    for ch in DIACRITICS:
        stats[f"变音 {ch}"] = full.count(ch)
    for w in GERMAN_WORDS:
        stats[f"德文词 {w}"] = full.count(w)
    stats["替换符 U+FFFD"] = full.count("\ufffd")

    # 跨页重复文本（页眉/页脚模式）：每页前 1 行与末 1 行
    head_lines: dict[str, int] = {}
    tail_lines: dict[str, int] = {}
    for t in pages_text:
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        if lines:
            head_lines[lines[0][:40]] = head_lines.get(lines[0][:40], 0) + 1
            tail_lines[lines[-1][:40]] = tail_lines.get(lines[-1][:40], 0) + 1
    repeated_heads = {k: v for k, v in head_lines.items() if v >= 3}
    repeated_tails = {k: v for k, v in tail_lines.items() if v >= 3}

    pages = []
    for i, (p, t) in enumerate(zip(reader.pages, pages_text), 1):
        blocks = _blocks_of(p)
        if not blocks:
            continue
        xs = [b[0] for b in blocks]
        xmin, xmax = min(xs), max(xs)
        w = max(xmax - xmin, 1)
        bands = {"左(<33%)": 0, "中(33-66%)": 0, "右(>66%)": 0}
        for x in xs:
            pct = (x - xmin) / w * 100
            bands["左(<33%)" if pct < 33 else ("右(>66%)" if pct > 66 else "中(33-66%)")] += 1
        geom = sorted(blocks, key=lambda b: (-b[1], b[0]))
        pages.append(
            {
                "页": i,
                "字符数": len(t),
                "块数": len(blocks),
                "x范围": [round(xmin, 1), round(xmax, 1)],
                "归一化x分布": bands,
                "流序首5块": [b[2][:20] for b in blocks[:5]],
                "几何序首5块": [b[2][:20] for b in geom[:5]],
                "页码碎片": [b[2][:16] for b in blocks if re.fullmatch(r"[\d\s]{1,6}", b[2])][:3],
            }
        )

    return {
        "文件": str(path),
        "统计": stats,
        "疑似页眉(跨页重复)": list(repeated_heads.items())[:5],
        "疑似页脚(跨页重复)": list(repeated_tails.items())[:5],
        "页分析(前12页)": pages[:12],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF 质量与布局分析")
    parser.add_argument("path", help="PDF 文件路径")
    parser.add_argument("--json", help="结果写入 JSON 文件（UTF-8）")
    args = parser.parse_args()

    result = analyze(args.path)
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"分析完成，已写入 {args.json}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
