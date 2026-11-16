"""抓取当前失败清单里所有站点的正文到 bodies/，逐站串行，低并发。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures

HERE = Path(__file__).resolve().parent
OUT = HERE / "bodies"
OUT.mkdir(exist_ok=True)

text = (HERE / "failure.txt").read_text(encoding="utf-8")
items = re.findall(r"失败 (\S+) (\S+) 方向", text)
print("站点数", len(items))

for name, url in items:
    captures, errors = fetch_browser_captures(
        [BrowserFetchSpec(url=url)], timeout=25, max_workers=1
    )
    capture = captures.get(url)
    if not capture:
        print("FAIL", name, errors.get(url))
        continue
    body = capture.body or ""
    (OUT / f"{name}.txt").write_text(body, encoding="utf-8")
    print("OK", name, len(body), "lines", body.count("\n"))
