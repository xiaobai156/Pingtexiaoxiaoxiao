from pathlib import Path
import sys
sys.path.insert(0, str(Path(".").resolve()))
from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac

r = build_runtime(Path(".").resolve())
name = sys.argv[1] if len(sys.argv) > 1 else "智能平特"
target = [t for t in r.targets if t.name == name][0]
rule = r.registry.rules.rule_for(target)
print("规则:", rule)
text = Path(f"_audit/314修复/bodies/{name}.txt").read_text(encoding="utf-8")
for issue in ("318", "317", "316", "315"):
    lines = r.registry.parse_issue_lines(text, target, issue)
    print(f"--- {issue}: {len(lines)} 行")
    for line in lines:
        print("   ", repr(line), "->", extract_target_zodiac(line, target, rule))
