"""离线验证 大器晚成 改用 anchored_section + line_keyword 后能否取到 317。"""
from __future__ import annotations
import json, sys
from pathlib import Path
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pingte.application.runtime import build_runtime
from pingte.parse.context import RuleBook, ParserHooks
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import extract_target_zodiac, zodiac_chars, dedupe_zodiac, strict_extract_zodiac

runtime = build_runtime(ROOT)
target = next(t for t in runtime.targets if t.name == "大器晚成")
body = (Path(__file__).resolve().parent / "bodies" / "大器晚成.txt").read_text(encoding="utf-8")

hooks = ParserHooks(
    extract_zodiac=strict_extract_zodiac,
    extract_target_zodiac=extract_target_zodiac,
    zodiac_chars=zodiac_chars,
    dedupe_zodiac=dedupe_zodiac,
)

base = dict(runtime.registry.rules.rule_for(target))
variants = {
    "改动前": {},
    "anchored+line_keyword": {
        "mode": "anchored_section",
        "data_structure": "confirmed_result_line",
        "section_boundary": "explicit_anchors",
        "section_anchor": "平特贴{issue}期:【平特三肖】大器晚成",
        "section_end": "站长宣言",
        "line_keyword": "平特三肖",
        "allow_many_zodiac_candidate": True,
    },
    "anchored无allow_many": {
        "mode": "anchored_section",
        "data_structure": "confirmed_result_line",
        "section_boundary": "explicit_anchors",
        "section_anchor": "平特贴{issue}期:【平特三肖】大器晚成",
        "section_end": "站长宣言",
        "line_keyword": "平特三肖",
    },
}
rules = list(runtime.registry.rules.rules)
for label, patch in variants.items():
    merged = {**base, **patch}
    patched = [merged if r.get("target_id") == target.target_id else r for r in rules]
    book = RuleBook(patched, runtime.registry.rules.followup_labels)
    reg = DedicatedParserRegistry(book, hooks)
    out = {}
    for issue in ("317", "316", "315"):
        lines = reg.parse_issue_lines(body, target, issue)
        out[issue] = [(l[:60], extract_target_zodiac(l, target)) for l in lines]
    print(f"--- {label}")
    for issue, rows in out.items():
        print("  ", issue, rows)
