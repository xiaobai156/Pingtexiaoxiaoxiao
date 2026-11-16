"""用强制渲染后的正文离线跑真实解析，判断每站是真有数据还是确实未发布。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime  # noqa: E402
from pingte.validation.issue import extract_target_zodiac  # noqa: E402

HERE = Path(__file__).resolve().parent
FORCED = HERE / "forced"
ISSUES = ["317", "316", "315"]

runtime = build_runtime(ROOT)
by_name = {target.name: target for target in runtime.targets}
cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
cached = {entry["target_id"]: entry["values"] for entry in cache["sites"]}

text_fail = (HERE / "failure.txt").read_text(encoding="utf-8")
import re  # noqa: E402

names = []
for name in re.findall(r"失败 (\S+) (\S+) 方向", text_fail):
    if name[0] not in names:
        names.append(name[0])

for name in names:
    target = by_name[name]
    forced_path = FORCED / f"{name}-forced.txt"
    plain_path = FORCED / f"{name}-plain.txt"
    forced = forced_path.read_text(encoding="utf-8") if forced_path.exists() else ""
    plain = plain_path.read_text(encoding="utf-8") if plain_path.exists() else ""
    rule = runtime.registry.rules.rule_for(target)
    print("=" * 72)
    print(f"{name} [{target.target_id}] mode={rule.get('mode')} kw={target.keyword}")
    values = cached.get(target.target_id, {})
    for label, text in (("强制渲染", forced), ("普通渲染", plain)):
        row = []
        for issue in ISSUES:
            lines = runtime.registry.parse_issue_lines(text, target, issue)
            zodiacs = [extract_target_zodiac(line, target, rule) for line in lines]
            row.append(f"{issue}={zodiacs or '-'}")
            if issue == "317" and lines:
                for line in lines[:2]:
                    print(f"      行: {line[:100]}")
        print(f"   {label}: " + "  ".join(row))
    print(f"   缓存: " + "  ".join(f"{i}={values.get(i, '-')}" for i in ISSUES))
