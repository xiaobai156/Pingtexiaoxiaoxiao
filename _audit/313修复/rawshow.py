"""打印正文原始行（不过滤空行）中锚点附近的区块，便于看真实结构。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
sys.stdout.reconfigure(encoding="utf-8")


def raw_lines(name: str) -> list[str]:
    path = BODIES / (re.sub(r"[^\w\-]", "_", name) + ".txt")
    return path.read_text(encoding="utf-8").splitlines()


def main() -> None:
    name = sys.argv[1]
    pattern = sys.argv[2]
    before = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    after = int(sys.argv[4]) if len(sys.argv) > 4 else 40
    limit = int(sys.argv[5]) if len(sys.argv) > 5 else 3
    lines = raw_lines(name)
    hits = [i for i, ln in enumerate(lines) if re.search(pattern, ln)]
    print(f"{name}: 原始 {len(lines)} 行，命中 {len(hits)}，显示前 {limit}")
    for i in hits[:limit]:
        print("-" * 70)
        lo = max(0, i - before)
        hi = min(len(lines), i + after + 1)
        for j in range(lo, hi):
            mark = "*" if j == i else " "
            print(f"{mark}{j + 1:5}: {lines[j][:110]!r}")


if __name__ == "__main__":
    main()
