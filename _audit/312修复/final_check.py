"""校验成功文件：数据行数、站点名唯一性、与缓存 316 值一致性。"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
OUT = ROOT.parent / "大围杀号生肖数据统一归纳" / "11.12平特肖.txt"

lines = OUT.read_text(encoding="utf-8-sig").splitlines()
head = lines[: lines.index("排行榜")] if "排行榜" in lines else lines
rows = [ln.strip() for ln in head if re.match(r"^[鼠牛虎兔龙蛇马羊猴鸡狗猪]\S* ", ln.strip())]
print("总行", len(lines), "数据行", len(rows))
names = [r.split(" ", 1)[1] for r in rows]
dups = [n for n, c in Counter(names).items() if c > 1]
print("重名站点", dups)

cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
by_id = {e["target_id"]: e for e in cache["sites"]}
want = {"PT-0087": "慕名喜欢", "PT-0172": "满堂红第二", "PT-0173": "满堂红第三", "PT-0174": "满堂红第四"}
for tid, name in want.items():
    got = [r for r in rows if r.endswith(" " + name)]
    print(tid, name, "文件值", got, "缓存316", by_id[tid]["values"].get("316"))
