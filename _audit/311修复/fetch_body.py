"""抓取 PT-0231 页面并保存正文，打印 315 期与成语平特相关行。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures

HERE = Path(__file__).resolve().parent
OUT = HERE / "bodies"
OUT.mkdir(exist_ok=True)

URL = "https://w4shq9.47598676.app/topic/228617.html"
captures, errors = fetch_browser_captures([BrowserFetchSpec(url=URL)], timeout=25, max_workers=1)
capture = captures.get(URL)
if capture is None:
    print("FAIL", errors.get(URL))
    raise SystemExit(1)

body = capture.body or ""
(OUT / "上官盐翼.txt").write_text(body, encoding="utf-8")
lines = body.splitlines()
print("len", len(body), "lines", len(lines))
hits = [i for i, line in enumerate(lines) if "315" in line or "成语平特" in line]
for i in hits[:40]:
    print(i, repr(lines[i][:110]))
