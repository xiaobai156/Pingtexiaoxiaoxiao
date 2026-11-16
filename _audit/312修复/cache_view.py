"""查看缓存中指定 target 的历史值（自动适配 sites 结构）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")

cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
sites = cache["sites"]
print("sites 类型", type(sites).__name__, "数量", len(sites))
sample = sites[0] if isinstance(sites, list) else next(iter(sites.items()))
print("样例", json.dumps(sample, ensure_ascii=False)[:300])

wanted = {"PT-0087", "PT-0172", "PT-0173", "PT-0174", "PT-0205", "PT-0231"}

def show(entry: dict) -> None:
    tid = entry.get("target_id") or entry.get("id")
    if tid in wanted:
        print(tid, entry.get("name"), json.dumps(entry, ensure_ascii=False)[:400])

if isinstance(sites, list):
    for entry in sites:
        show(entry)
else:
    for key, entry in sites.items():
        if isinstance(entry, dict):
            entry.setdefault("target_id", key)
            show(entry)
