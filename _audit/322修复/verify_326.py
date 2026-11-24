import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac
ROOT = Path(__file__).resolve().parents[2]
rt = build_runtime(ROOT)
cache = json.load(open(ROOT/"recent_10_cache.json", encoding="utf-8-sig"))
cmap = {s["name"]: s["values"] for s in cache["sites"]}
B = ROOT/"_audit/322修复/bodies"
for name, body in [("气冲牛斗","气冲牛斗.txt"),("大公无私","大公无私.txt"),("澳门资料库","澳门资料库.txt")]:
    t=[x for x in rt.targets if x.name==name][0]
    rule=rt.registry.rules.rule_for(t)
    text=(B/body).read_text(encoding="utf-8")
    print("=====",name,t.position,t.keyword,"rule rv",rule.get("rule_version"))
    for issue in ("326","325","324","323","322"):
        lines=rt.registry.parse_issue_lines(text,t,issue)
        vals=sorted({extract_target_zodiac(l,t,rule) for l in lines})
        print(f"  {issue}: 候选={len(lines)} 值={vals} 缓存={cmap.get(name,{}).get(issue)}")
        for l in lines[:2]: print("      ",l[:100])
