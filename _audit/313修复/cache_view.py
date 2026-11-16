"""打印指定站点的缓存 values 与历史期数。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")

cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
names = set(sys.argv[1:])
print("缓存期数:", cache["issues"])
for entry in cache["sites"]:
    if entry["name"] in names:
        print(entry["target_id"], entry["name"], entry["keyword"], entry["position"])
        print("   ", entry["values"])
