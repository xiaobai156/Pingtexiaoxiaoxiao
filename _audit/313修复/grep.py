"""在某正文里按关键字搜索行，显示行号与上下文。"""
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


def main() -> None:
    name = sys.argv[1]
    pattern = sys.argv[2]
    ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 40
    lines = lines_of(name)
    hits = [i for i, ln in enumerate(lines) if re.search(pattern, ln)]
    print(f"{name} 共 {len(lines)} 行，命中 {len(hits)} 行（显示前 {limit}）")
    shown: set[int] = set()
    for i in hits[:limit]:
        lo, hi = max(0, i - ctx), min(len(lines), i + ctx + 1)
        for j in range(lo, hi):
            if j in shown:
                continue
            shown.add(j)
            print(f"  {j + 1}: {lines[j][:120]}")
        print("  ---")


if __name__ == "__main__":
    main()
