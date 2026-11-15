#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 prompts/ 下的分册合并成 PROMPTS.md（仓库根目录），并生成目录。

用法（在仓库根目录）：python3 tools/build_prompts.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "prompts"
OUT = ROOT / "PROMPTS.md"

HEADER = """# PROMPTS · 提示词总库（P0 – P15 + F1 – F4）

> 由 `tools/build_prompts.py` 从 `prompts/` 自动合并生成，**不要手改本文件**；改分册后重跑脚本。
> 用法：`Ctrl+F` 搜 `## P7` 直接跳到需要的提示词；每条都在 ```text 围栏里，整段复制。

"""


def main() -> int:
    files = sorted(SRC.glob("*.md"))
    if not files:
        print("× prompts/ 下没有 .md 文件", file=sys.stderr)
        return 1

    parts, toc = [], []
    for f in files:
        body = f.read_text(encoding="utf-8").strip()
        parts.append((f, body))
        for line in body.splitlines():
            m = re.match(r"^##\s+((?:P|F)[\d.]+.*)$", line.strip())
            if m:
                toc.append((f.stem, m.group(1).strip()))

    out = [HEADER, "## 目录\n"]
    cur = None
    for stem, title in toc:
        if stem != cur:
            out.append("\n**%s**\n" % stem)
            cur = stem
        out.append("- %s\n" % title)
    out.append("\n---\n")
    for f, body in parts:
        out.append("\n<!-- source: prompts/%s -->\n" % f.name)
        out.append(body)
        out.append("\n\n---\n")

    OUT.write_text("".join(out), encoding="utf-8")
    print("√ 合并 %d 个分册 → %s（%d 条提示词，%d 字节）"
          % (len(files), OUT.name, len(toc), OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
