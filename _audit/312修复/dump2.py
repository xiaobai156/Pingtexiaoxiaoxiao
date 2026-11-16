"""打印正文指定区间，用于定位稳定尾锚点。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

SPANS = {
    "满堂红第二": (140, 175),
    "满堂红第三": (60, 108),
    "满堂红第四": (40, 76),
    "大器晚成": (1, 25),
}

for name, (start, end) in SPANS.items():
    lines = (BODIES / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    print("=" * 70)
    print(name, "总行数", len(lines))
    for i in range(start - 1, min(end, len(lines))):
        print(f"{i + 1:>4} | {lines[i]}")
