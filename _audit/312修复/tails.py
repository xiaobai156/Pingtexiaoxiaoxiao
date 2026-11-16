"""查看缓存历史值与正文尾部，确定稳定尾锚点。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
print("cache 顶层键", list(cache)[:6])

sites = cache.get("sites") or cache.get("targets") or cache
for tid in ["PT-0087", "PT-0172", "PT-0173", "PT-0174", "PT-0205", "PT-0231"]:
    entry = sites.get(tid) if isinstance(sites, dict) else None
    if entry is None:
        print(tid, "缓存中未找到")
        continue
    values = entry.get("values") if isinstance(entry, dict) else entry
    print(tid, entry.get("name") if isinstance(entry, dict) else "", values)

for name in ["满堂红第二", "满堂红第三", "满堂红第四", "大器晚成", "上官盐翼"]:
    lines = (BODIES / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    print("=" * 60)
    print(name, "总行数", len(lines))
    for i in range(max(0, len(lines) - 30), len(lines)):
        print(f"{i + 1:>4} | {lines[i]}")
