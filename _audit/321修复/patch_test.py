import dataclasses, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from pingte.application.runtime import build_runtime
from pingte.parse.context import RuleBook
from pingte.parse.registry import DedicatedParserRegistry
from pingte.parse.context import ParserHooks
from pingte.validation.issue import (dedupe_zodiac, extract_target_zodiac,
                                     strict_extract_zodiac, zodiac_chars)
ROOT = Path(__file__).resolve().parents[2]
rt = build_runtime(ROOT)
NAME = "一個好人"
t = [x for x in rt.targets if x.name == NAME][0]
base = dict(rt.registry.rules.rule_for(t))
hooks = ParserHooks(extract_zodiac=strict_extract_zodiac,
                    extract_target_zodiac=extract_target_zodiac,
                    zodiac_chars=zodiac_chars, dedupe_zodiac=dedupe_zodiac)
SN = "「平特一肖」独家提供"
variants = {
  "A_named+section_name": {**base, "section_name": SN},
  "B_header+section_name+ctx": {**base, "mode": "header_section",
     "section_boundary": "target_header_section", "section_name": SN,
     "header_context_required": "平特一肖《"},
  "C_named_only": base,
}
bodies = sorted(Path('_audit/321修复/bodies').glob('一個好人-*.txt'))
cache = {'325': '兔', '324': '羊', '323': '虎'}
for label, rule in variants.items():
    reg = DedicatedParserRegistry(RuleBook([rule], {}), hooks)
    print("==", label)
    for body in bodies:
        text = body.read_text(encoding='utf-8')
        out = []
        for issue in ("325", "324", "323"):
            lines = reg.parse_issue_lines(text, t, issue)
            vals = [extract_target_zodiac(l, t, rule) for l in lines]
            out.append((issue, vals))
        print("  ", body.name, out)
