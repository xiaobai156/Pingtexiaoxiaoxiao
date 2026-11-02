"""只读探测：对失败列表里的站点逐个用浏览器访问，记录连通性与 305 期可见性。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures

FAIL = Path(
    r"C:/Users/Administrator/.dsh/attachments/v1/files/a1/"
    r"a16c9d0e4598e4cfeba7d0223b84e8684614874dfd8bfa70ee151e11baca46bf/11.1平特肖-失败.txt"
)
OUT = Path(__file__).with_name("probe_report.json")
ISSUE = "305"


def load_failures() -> list[dict]:
    text = FAIL.read_text(encoding="utf-8")
    items = []
    for m in re.finditer(
        r"失败 (\S+) (\S+) 方向: (\S+) 期数: (\S+)\n阶段: (\S+) 原因: (.+)",
        text,
    ):
        items.append(
            {
                "name": m.group(1),
                "url": m.group(2),
                "position": "tail" if m.group(3) == "bottom" else m.group(3),
                "issue": m.group(4),
                "stage": m.group(5),
                "reason": m.group(6),
            }
        )
    return items


def main() -> int:
    items = load_failures()
    specs = [BrowserFetchSpec(url=item["url"]) for item in items]
    captures, errors = fetch_browser_captures(specs, timeout=25, max_workers=5)
    report = []
    for item in items:
        url = item["url"]
        capture = captures.get(url)
        entry = {
            "name": item["name"],
            "url": url,
            "position": item["position"],
            "original_stage": item["stage"],
            "original_reason": item["reason"][:120],
            "reached": capture is not None,
            "error": errors.get(url, ""),
        }
        if capture is not None:
            body = capture.body or ""
            entry["final_url"] = capture.final_url
            entry["body_len"] = len(body)
            entry["has_issue"] = bool(re.search(rf"(?<!\d){ISSUE}(?!\d)", body))
            entry["issue_hits"] = len(re.findall(rf"(?<!\d){ISSUE}(?!\d)", body))
            hits = re.findall(rf".{{0,40}}(?<!\d){ISSUE}(?!\d).{{0,60}}", body)
            entry["issue_context"] = [h.replace("\n", " ") for h in hits[:4]]
            entry["zodiac_mentions"] = sorted(
                set(re.findall("[鼠牛虎兔龙蛇马羊猴鸡狗猪]", body))
            )
        report.append(entry)
    OUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    ok = sum(1 for r in report if r["reached"])
    print(f"可达 {ok}/{len(report)}")
    for r in report:
        print(
            f"{'OK ' if r['reached'] else 'ERR'} {r['name']:<6} "
            f"len={r.get('body_len', 0):<6} 305={r.get('has_issue')} "
            f"{r['error'][:80]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
