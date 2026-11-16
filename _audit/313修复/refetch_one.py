"""单独抓一个站点正文，打印关键统计，便于比对是否 JS 未渲染完。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures

url = sys.argv[1]
out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
captures, errors = fetch_browser_captures(
    [BrowserFetchSpec(url=url)], timeout=30, max_workers=1
)
cap = captures.get(url)
if not cap:
    print("FAIL", errors.get(url))
    raise SystemExit(1)
body = cap.body or ""
print("final_url", cap.final_url)
print("len", len(body), "lines", body.count("\n"))
for token in ("四字平特", "龙争虎斗", "开？", "00准", "解四字符"):
    print(" ", token, body.count(token))
if out:
    out.write_text(body, encoding="utf-8")
    print("written", out)
