"""对失败站点逐页诊断：区块候选行、生肖抽取结果，定位 zodiac_missing 的确切原因。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
ISSUE = "309"

runtime = build_runtime(ROOT)
registry = runtime.registry
by_name = {target.name: target for target in runtime.targets}

for body in sorted(BODIES.glob("*.txt")):
    name = body.stem
    target = by_name.get(name)
    if target is None:
        print(name, "不在活跃目标")
        continue
    text = body.read_text(encoding="utf-8")
    rule = registry.rules.rule_for(target)
    lines = registry.parse_issue_lines(text, target, ISSUE)
    print(f"--- {name} mode={rule['mode']} 候选行数={len(lines)}")
    for line in lines[:6]:
        print("    ", line[:70])
    for raw in text.splitlines():
        if ISSUE in raw and rule["keyword"] in raw:
            try:
                zodiac = extract_target_zodiac(raw, target, rule)
            except Exception as exc:  # noqa: BLE001
                zodiac = f"<{type(exc).__name__}: {exc}>"
            print(f"     抽取 {zodiac!r} <- {raw[:70]}")
