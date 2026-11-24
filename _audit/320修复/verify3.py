"""独立复核：真实浏览器重抓 3 站，按各自规则解析 324 并与已写入值比对。"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from pingte.application.runtime import build_runtime
from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures
from pingte.validation.issue import extract_target_zodiac

ROOT = Path(__file__).resolve().parents[2]
runtime = build_runtime(ROOT)
by = {t.name: t for t in runtime.targets}
names = ["凉风有信", "雄霸六合", "相思入骨"]
specs = [BrowserFetchSpec(url=by[n].url) for n in names]
expect = {"凉风有信": "狗", "雄霸六合": "猴狗", "相思入骨": "牛马"}
for rnd in (1, 2):
    caps, errs = fetch_browser_captures(specs, timeout=25, max_workers=1)
    print(f"--- 第{rnd}轮")
    for n in names:
        t = by[n]
        cap = caps.get(t.url)
        if not cap:
            print("  ERR", n, errs.get(t.url)); continue
        lines = runtime.registry.parse_issue_lines(cap.body or "", t, "324")
        rule = runtime.registry.rules.rule_for(t)
        got = sorted({extract_target_zodiac(l, t, rule) for l in lines})
        ok = got == [expect[n]]
        print(f"  {'OK ' if ok else '!! '}{n} 候选={got} 期望={expect[n]!r} 行={[l[:48] for l in lines]}")
