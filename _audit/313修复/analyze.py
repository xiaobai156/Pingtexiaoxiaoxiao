"""分析失败站点：锚点/尾锚点是否存在于正文，317 期数据行在哪。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

ZODIAC = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
fail_text = (HERE / "failure.txt").read_text(encoding="utf-8")
items = re.findall(r"失败 (\S+) (\S+) 方向: (\S+) 期数: (\d+)", fail_text)

cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
by_name = {e["name"]: e for e in cache["sites"]}

for name, url, pos, issue in items:
    body_path = BODIES / (re.sub(r"[^\w\-]", "_", name) + ".txt")
    print("=" * 78)
    print(name, pos, issue, "缓存:", by_name.get(name, {}).get("values", {}).get(issue, "-"))
    if not body_path.exists():
        print("  (无正文)")
        continue
    lines = [ln.strip() for ln in body_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]
    tid = by_name.get(name, {}).get("target_id")
    rule_path = ROOT / "config" / "sites" / f"{tid}.json"
    rule = json.loads(rule_path.read_text(encoding="utf-8-sig"))["parser"]
    anchor = rule.get("section_anchor", "")
    end = rule.get("section_end", "")
    a_hits = [i + 1 for i, ln in enumerate(lines) if anchor and anchor in ln]
    e_hits = [i + 1 for i, ln in enumerate(lines) if end and end in ln]
    print(f"  anchor={anchor!r} 命中行 {a_hits}")
    print(f"  end={end!r} 命中行 {e_hits}")
    dat = [(i + 1, ln) for i, ln in enumerate(lines) if re.match(rf"^{issue}期", ln) or f"{issue}期" in ln[:8]]
    print(f"  含 {issue}期 的行 {len(dat)} 条，前 6：")
    for no, ln in dat[:6]:
        print(f"    {no}: {ln[:110]}")
