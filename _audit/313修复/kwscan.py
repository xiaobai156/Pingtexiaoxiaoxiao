"""对失败站点：统计关键词出现位置，判断区块内容是否为空/未发布。"""
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

for name, url, pos, issue in items:
    path = BODIES / f"{name}.txt"
    if not path.exists():
        print(f"== {name}: 无正文（同 URL 其他站点共用）")
        continue
    tid = by_name[name]["target_id"]
    rule = json.loads((ROOT / "config" / "sites" / f"{tid}.json").read_text(encoding="utf-8-sig"))["parser"]
    kw = rule.get("keyword", "")
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [(i + 1, ln.strip()) for i, ln in enumerate(lines) if kw and kw in ln]
    print(f"== {name} ({tid}) mode={rule['mode']} keyword={kw!r} 共 {len(lines)} 行，关键词命中 {len(hits)}")
    for no, ln in hits[:10]:
        print(f"   {no}: {ln[:100]}")
