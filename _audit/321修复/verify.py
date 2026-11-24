import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from pingte.application.runtime import build_runtime
from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures
from pingte.validation.issue import extract_target_zodiac
rt = build_runtime(Path(__file__).resolve().parents[2])
t = [x for x in rt.targets if x.name == "一個好人"][0]
rule = rt.registry.rules.rule_for(t)
ok = 0
for i in range(1, 7):
    caps, errs = fetch_browser_captures([BrowserFetchSpec(url=t.url)], timeout=25, max_workers=1)
    cap = caps.get(t.url)
    if not cap:
        print(i, "ERR", errs.get(t.url)); continue
    body = cap.body or ""
    lines = rt.registry.parse_issue_lines(body, t, "325")
    got = sorted({extract_target_zodiac(l, t, rule) for l in lines})
    good = got == ["兔"]
    ok += good
    print(f"{i} {'OK ' if good else '!! '}命中{body.count('「平特一肖」独家提供')} 候选={got} 行={[l[:44] for l in lines]}")
print("成功", ok, "/6")
