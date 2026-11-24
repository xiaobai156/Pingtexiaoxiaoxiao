import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from pingte.application.runtime import build_runtime
ROOT = Path(__file__).resolve().parents[2]
runtime = build_runtime(ROOT)
by = {t.name: t for t in runtime.targets}
names = sys.argv[1:] or ["凉风有信","雄霸六合","相思入骨"]
for name in names:
    t = by[name]
    text = (Path(__file__).parent/"bodies"/f"{name}.txt").read_text(encoding="utf-8")
    for issue in ("324","323","322"):
        lines = runtime.registry.parse_issue_lines(text, t, issue)
        print(f"--- {name} {issue}期 候选 {len(lines)}")
        for l in lines[:4]: print("    ", l[:90])
    rule = runtime.registry.rule_book.rule_for(t)
    print("    规则:", {k: rule.get(k) for k in ("mode","section_name","section_anchor","section_end","keyword","line_keyword","position")})
