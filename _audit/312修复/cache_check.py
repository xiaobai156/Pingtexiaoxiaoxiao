"""打印指定目标在缓存中的 values，用于写入后的复核。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")

cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
want = {"PT-0087", "PT-0172", "PT-0173", "PT-0174", "PT-0205", "PT-0231"}
print("issues:", cache["issues"][:12])
for entry in cache["sites"]:
    if entry["target_id"] in want:
        print(entry["target_id"], entry["name"], entry["values"])
