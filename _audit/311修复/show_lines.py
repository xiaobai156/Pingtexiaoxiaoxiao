"""打印 PT-0231 正文里 315 期与成语平特相关行。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
lines = (HERE / "bodies" / "上官盐翼.txt").read_text(encoding="utf-8").splitlines()
print("lines", len(lines))
for index, line in enumerate(lines):
    if "315" in line or "成语平特" in line or "314" in line:
        print(index, repr(line[:110]))
