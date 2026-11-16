"""按站名查看指定关键词/邻近文本的上下文，辅助判定栏目是否改名或未发布。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

site = sys.argv[1]
needles = sys.argv[2:]
lines = (BODIES / f"{site}.txt").read_text(encoding="utf-8").splitlines()
print(f"{site}: {len(lines)} 行")
for needle in needles:
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    print(f"\n### {needle!r} 命中 {len(hits)} 处")
    for idx in hits[:6]:
        print(f"--- 行 {idx + 1}")
        for j in range(max(0, idx - 3), min(len(lines), idx + 8)):
            text = lines[j].strip()
            if text:
                print(f"   {j + 1}: {text[:100]}")
