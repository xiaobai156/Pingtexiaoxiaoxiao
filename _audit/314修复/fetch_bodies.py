"""抓取失败清单里站点正文到 bodies/，按 URL 去重、逐站串行。"""
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
print("失败条数", len(items))

seen: dict[str, list[str]] = {}
for name, url in items:
    seen.setdefault(url, []).append(name)
print("去重 URL 数", len(seen))


def safe(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)


for url, names in seen.items():
    captures, errors = fetch_browser_captures(
        [BrowserFetchSpec(url=url)], timeout=25, max_workers=1
    )
    capture = captures.get(url)
    if not capture:
        print("FAIL", url, errors.get(url))
        continue
    body = capture.body or ""
    target = OUT / (safe(names[0]) + ".txt")
    target.write_text(body, encoding="utf-8")
    print("OK", names[0], len(body), "chars", "| 同 URL:", ",".join(names[1:]) or "-")
