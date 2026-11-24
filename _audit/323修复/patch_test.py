import sys, json
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pingte.application.runtime import build_runtime
from pingte.parse.context import RuleBook
from pingte.parse.registry import DedicatedParserRegistry

runtime = build_runtime(ROOT)
target = next(t for t in runtime.targets if t.name == "一点红")
text = Path("_audit/323修复/bodies/一点红.txt").read_text(encoding="utf-8")
base = dict(runtime.pipeline.registry.rules.rule_for(target))
issues = ["327","326","325","324","323","322","321","320","319","316","315"]

def run(rule):
    rb = RuleBook([rule], runtime.pipeline.registry.rules.followup_labels if hasattr(runtime.pipeline.registry.rules,'followup_labels') else {})
    reg = DedicatedParserRegistry(rb, runtime.pipeline.registry.hooks)
    out = {}
    for i in issues:
        lines = reg.parse_issue_lines(text, target, i)
        out[i] = lines[0][:40] if lines else "-"
    return out

for cand in ["买港澳六合彩就上76.cc 特码58倍","澳门永利APP","买港澳六合彩就上","特码58倍","来源：澳门永利","授权：免费软件","全国彩民首选娱乐软件"]:
    rule = dict(base); rule["section_end"] = cand
    print(f"{cand!r:34}", run(rule))
