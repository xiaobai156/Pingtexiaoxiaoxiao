"""单站重抓：确认页面当前正文与解析结果（排查抖动/多版本页面）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime  # noqa: E402
from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures  # noqa: E402

HERE = Path(__file__).resolve().parent
name = sys.argv[1]
issue = sys.argv[2] if len(sys.argv) > 2 else "317"
rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 2

runtime = build_runtime(ROOT)
target = next(t for t in runtime.targets if t.name == name)
rule = runtime.registry.rules.rule_for(target)
print(f"{name} [{target.target_id}] url={target.url}")

for index in range(rounds):
    caps, errs = fetch_browser_captures(
        [BrowserFetchSpec(url=target.url)], timeout=40, max_workers=1
    )
    capture = caps.get(target.url)
    if not capture:
        print(f"第{index + 1}轮 抓取失败 {errs.get(target.url)}")
        continue
    body = capture.body or ""
    out = HERE / "bodies" / f"{name}-r{index + 1}.txt"
    out.write_text(body, encoding="utf-8")
    lines = runtime.registry.parse_issue_lines(body, target, issue)
    print(f"第{index + 1}轮 长度={len(body)} 候选={len(lines)}")
    for line in lines[:3]:
        print("    行:", line[:110])
    hits = [l for l in body.splitlines() if issue in l and "开" in l]
    for line in hits[:4]:
        print("    本期行:", line.strip()[:110])
