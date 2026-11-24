"""离线验证候选配置改动：克隆规则并打补丁，重建 registry 后跑解析，与缓存对照。"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime  # noqa: E402
from pingte.domain.models import TargetProfile  # noqa: E402
from pingte.parse.context import ParserHooks, RuleBook  # noqa: E402
from pingte.parse.registry import DedicatedParserRegistry  # noqa: E402
from pingte.validation.issue import (  # noqa: E402
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

runtime = build_runtime(ROOT)
active = runtime.targets
cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
cached = {entry["target_id"]: entry["values"] for entry in cache["sites"]}

PATCHES: dict[str, dict] = json.loads((HERE / "patch.json").read_text(encoding="utf-8"))

hooks = ParserHooks(
    extract_zodiac=strict_extract_zodiac,
    extract_target_zodiac=extract_target_zodiac,
    zodiac_chars=zodiac_chars,
    dedupe_zodiac=dedupe_zodiac,
)

for name, patch in PATCHES.items():
    target = next(t for t in active if t.name == name)
    rules = list(runtime.registry.rules.rules)
    patched_rules = []
    for rule in rules:
        if str(rule.get("target_id", "")) == target.target_id:
            merged = dict(rule)
            merged.update(patch)
            patched_rules.append(merged)
        else:
            patched_rules.append(rule)
    rule_book = RuleBook(
        patched_rules,
        runtime.registry.rules.followup_labels,
        dedicated_names=runtime.registry.rules.dedicated_names,
        dedicated_url_parts=runtime.registry.rules.dedicated_url_parts,
    )
    registry = DedicatedParserRegistry(rule_book, hooks)
    prof = target
    if "keyword" in patch:
        prof = replace(target, keyword=patch["keyword"])
    print("=" * 70)
    print(name, target.target_id, "patch:", patch)
    text = (BODIES / f"{name}.txt").read_text(encoding="utf-8")
    values = cached.get(target.target_id, {})
    for issue in ["324", "323", "322", "321"]:
        lines = registry.parse_issue_lines(text, prof, issue)
        merged_rule = rule_book.rule_for(prof)
        got = [extract_target_zodiac(line, prof, merged_rule) for line in lines]
        expect = values.get(issue)
        flag = "OK " if len(got) == 1 and got[0] == expect else "!! "
        print(f"  {flag}{issue}: 候选={got} 缓存={expect!r}")
        for line in lines[:3]:
            print("        ", line[:110])
