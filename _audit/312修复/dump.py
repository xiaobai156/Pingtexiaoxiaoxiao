"""打印各失败站正文的关键区间，便于人工核对锚点/数据行。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

SPANS = {
    "慕名喜欢": (1, 40),
    "满堂红第二": (1, 40),
    "满堂红第三": (1, 105),
    "满堂红第四": (1, 70),
    "大器晚成": (1, 30),
    "上官盐翼": (1, 20),
}

for name, (start, end) in SPANS.items():
    lines = (BODIES / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    print("=" * 70)
    print(name, "总行数", len(lines))
    print("站长宣言 出现行", [i + 1 for i, l in enumerate(lines) if "站长宣言" in l][:10])
    for i in range(start - 1, min(end, len(lines))):
        print(f"{i + 1:>4} | {lines[i]}")
