"""扫描所有正文，找 317 期相关行与结果形态行，供判定是否已发布。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

ZODIAC = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
result_pat = re.compile(r"开\s*[:：]?\s*[\d.,]{0,20}\s*[准中對对错]?")
issue317 = re.compile(r"(?<!\d)317\s*期")

for path in sorted(BODIES.glob("*.txt")):
    lines = path.read_text(encoding="utf-8").splitlines()
    hits_317 = [(i + 1, ln.strip()) for i, ln in enumerate(lines) if issue317.search(ln)]
    res = [
        (i + 1, ln.strip())
        for i, ln in enumerate(lines)
        if result_pat.search(ln) and any(z in ln for z in ZODIAC)
    ]
    print("=" * 70)
    print(f"{path.stem}: {len(lines)} 行；含317行 {len(hits_317)}；带生肖的结果行 {len(res)}")
    for no, ln in hits_317[:12]:
        print(f"  317→ {no}: {ln[:95]}")
    for no, ln in res[:12]:
        print(f"  res→ {no}: {ln[:95]}")
