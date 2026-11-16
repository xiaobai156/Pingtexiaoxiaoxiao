"""对指定站点、指定原文行调用统一抽取，比较不同行的结果。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac

runtime = build_runtime(ROOT)
by_name = {target.name: target for target in runtime.targets}

name = sys.argv[1]
target = by_name[name]
rule = runtime.registry.rules.rule_for(target)
print("rule:", {k: v for k, v in rule.items() if k in {
    "mode", "keyword", "position", "data_structure", "section_anchor", "section_end",
    "accepted_result_statuses", "issue_format"}})

for raw in sys.argv[2:]:
    try:
        zodiac = extract_target_zodiac(raw, target, rule)
    except Exception as exc:  # noqa: BLE001
        zodiac = f"<{type(exc).__name__}: {exc}>"
    print(f"{zodiac!r} <- {raw}")
