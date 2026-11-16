"""编译后用离线正文校验 316/315/314 的解析结果，与缓存对照。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

runtime = build_runtime(ROOT)
by_name = {target.name: target for target in runtime.targets}
cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
cached = {entry["target_id"]: entry["values"] for entry in cache["sites"]}

for name in ["慕名喜欢", "满堂红第二", "满堂红第三", "满堂红第四"]:
    target = by_name[name]
    rule = runtime.registry.rules.rule_for(target)
    text = (BODIES / f"{name}.txt").read_text(encoding="utf-8")
    values = cached.get(target.target_id, {})
    print("=" * 66)
    print(name, target.target_id, "mode", rule["mode"], "position", target.position)
    for issue in ["316", "315", "314", "313"]:
        lines = runtime.registry.parse_issue_lines(text, target, issue)
        got = []
        for line in lines:
            zodiac = extract_target_zodiac(line, target, rule)
            got.append((line[:60], zodiac))
        print(f"  {issue}: 候选 {len(lines)} 缓存={values.get(issue)!r}")
        for line, zodiac in got[:4]:
            print(f"      {zodiac!r} <- {line}")
