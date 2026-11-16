"""打印正文指定行区间，用于人工核对区块结构。"""
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


def show(name: str, start: int, end: int) -> None:
    lines = lines_of(name)
    print("=" * 78)
    print(f"{name} 行 {start}-{end} (共 {len(lines)} 行)")
    for i in range(start - 1, min(end, len(lines))):
        print(f"  {i + 1}: {lines[i][:120]}")


if __name__ == "__main__":
    name = sys.argv[1]
    start = int(sys.argv[2])
    end = int(sys.argv[3])
    show(name, start, end)
