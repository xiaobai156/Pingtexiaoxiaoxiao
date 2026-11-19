"""打印指定站点名对应的 targets 条目与 config/sites 规则文件。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")

data = json.loads((ROOT / "targets.json").read_text(encoding="utf-8"))
entries = data["targets"]

names = sys.argv[1:]
for entry in entries:
    if entry.get("name") not in names:
        continue
    tid = entry.get("target_id")
    print("=" * 70)
    print(tid, entry.get("name"), entry.get("url"), "position:", entry.get("position"))
    site = ROOT / "config" / "sites" / f"{tid}.json"
    print("--- config/sites/" + site.name)
    print(site.read_text(encoding="utf-8") if site.exists() else "(缺失)")
