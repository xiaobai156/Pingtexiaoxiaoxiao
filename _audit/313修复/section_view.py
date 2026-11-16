"""对每个失败站点打印锚点/尾锚点原始行号与其后若干行，判断区块是否为空。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

fail_text = (HERE / "failure.txt").read_text(encoding="utf-8")
items = re.findall(r"失败 (\S+) (\S+) 方向: (\S+) 期数: (\d+)", fail_text)
cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
by_name = {e["name"]: e for e in cache["sites"]}

AFTER = int(sys.argv[1]) if len(sys.argv) > 1 else 8

for name, url, pos, issue in items:
    path = BODIES / f"{name}.txt"
    if not path.exists():
        continue
    tid = by_name[name]["target_id"]
    rule = json.loads((ROOT / "config" / "sites" / f"{tid}.json").read_text(encoding="utf-8-sig"))["parser"]
    anchor = rule.get("section_anchor", "")
    end = rule.get("section_end", "")
    lines = path.read_text(encoding="utf-8").splitlines()
    a_hits = [i for i, ln in enumerate(lines) if anchor and anchor in ln]
    e_hits = [i for i, ln in enumerate(lines) if end and end in ln]
    print("=" * 78)
    print(f"{name} ({tid}) mode={rule['mode']} anchor={anchor!r}@{ [i+1 for i in a_hits[:6]] } end={end!r}@{ [i+1 for i in e_hits[:6]] }")
    for i in a_hits[:3]:
        print("  锚点后：")
        for j in range(i, min(len(lines), i + AFTER + 1)):
            print(f"    {j + 1}: {lines[j][:100]!r}")
