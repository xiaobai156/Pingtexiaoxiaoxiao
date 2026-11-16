"""扫描正文里所有「结果行」形态（含 开/開 + 数字/准中错），用于判断数据是否已发布。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
sys.stdout.reconfigure(encoding="utf-8")

PAT = re.compile(r"开\s*[:：]?\s*[\d０-９]|開\s*[:：]?\s*[\d０-９]|开\s*[:：]\s*$")

names = sys.argv[1:]
for name in names:
    path = BODIES / f"{name}.txt"
    if not path.exists():
        print(f"== {name}: 无正文")
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [(i + 1, ln.strip()) for i, ln in enumerate(lines) if PAT.search(ln)]
    print(f"== {name}: {len(lines)} 行，结果形态 {len(hits)} 条")
    for no, ln in hits[:12]:
        print(f"   {no}: {ln[:110]}")
