"""在正文里找「像结果行」的行：含生肖字 + 开/准/中/错 标记。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
Z = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
sys.stdout.reconfigure(encoding="utf-8")


def lines_of(name: str) -> list[str]:
    path = BODIES / (re.sub(r"[^\w\-]", "_", name) + ".txt")
    raw = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in raw if ln]


name = sys.argv[1]
issue = sys.argv[2] if len(sys.argv) > 2 else "317"
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 25
lines = lines_of(name)
pat = re.compile(rf"{issue}")
hits = []
for i, ln in enumerate(lines):
    if not pat.search(ln):
        continue
    if not re.search(rf"[{Z}]", ln):
        continue
    if not re.search(r"开|准|中|错|√|✓|×", ln):
        continue
    hits.append((i + 1, ln))
print(f"{name}: 共 {len(lines)} 行，像结果行的 {len(hits)} 条")
for no, ln in hits[:limit]:
    print(f"  {no}: {ln[:120]}")
