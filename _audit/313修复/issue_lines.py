"""打印正文里所有含指定期数的行（行号 + 内容），用于定位真实数据区。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
sys.stdout.reconfigure(encoding="utf-8")


def lines_of(name: str) -> list[str]:
    path = BODIES / (re.sub(r"[^\w\-]", "_", name) + ".txt")
    raw = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in raw if ln]


name = sys.argv[1]
issue = sys.argv[2] if len(sys.argv) > 2 else "317"
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 200
lines = lines_of(name)
hits = [(i + 1, ln) for i, ln in enumerate(lines) if issue in ln]
print(f"{name}: 共 {len(lines)} 行，含 {issue} 的 {len(hits)} 行")
for no, ln in hits[:limit]:
    print(f"  {no}: {ln[:130]}")
