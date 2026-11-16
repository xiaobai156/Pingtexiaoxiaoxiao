"""离线复现：对指定站点正文跑真实解析链，打印候选与生肖。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime  # noqa: E402
from pingte.validation.issue import extract_target_zodiac  # noqa: E402

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

name = sys.argv[1]
issues = sys.argv[2:] or ["317"]
runtime = build_runtime(ROOT)
by_name = {target.name: target for target in runtime.targets}

target = by_name[name]
rule = runtime.registry.rules.rule_for(target)
print(name, target.target_id, "mode", rule.get("mode"), "position", target.position)
text = (BODIES / f"{name}.txt").read_text(encoding="utf-8")
for issue in issues:
    lines = runtime.registry.parse_issue_lines(text, target, issue)
    print(f"  {issue}: 候选 {len(lines)}")
    for line in lines[:6]:
        print("     ", extract_target_zodiac(line, target, rule), "<-", line[:110])
