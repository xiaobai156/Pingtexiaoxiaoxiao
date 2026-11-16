"""对当前失败站点逐页诊断：区块候选行、生肖抽取结果（离线，读 bodies）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
ISSUE = "317"

runtime = build_runtime(ROOT)
registry = runtime.registry
by_name = {target.name: target for target in runtime.targets}

for body in sorted(BODIES.glob("*.txt")):
    if body.stem.endswith("_retry"):
        continue
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
        print("    ", line[:100])
