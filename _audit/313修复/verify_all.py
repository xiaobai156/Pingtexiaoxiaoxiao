"""逐站复核：真实浏览器重抓 → 列出页面上全部 317 期候选行 → 对照解析结果与已写入值。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime  # noqa: E402
from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures  # noqa: E402
from pingte.validation.issue import extract_target_zodiac  # noqa: E402

HERE = Path(__file__).resolve().parent
ISSUE = "317"
OUT_DIR = Path(
    r"C:/Users/Administrator/Desktop/每天工具/爬虫合集/大围杀号生肖数据统一归纳"
)

runtime = build_runtime(ROOT)
by_name = {t.name: t for t in runtime.targets}

text = (HERE / "failure.txt").read_text(encoding="utf-8")
names: list[str] = []
for name in re.findall(r"失败 (\S+) (\S+) 方向", text):
    if name[0] not in names:
        names.append(name[0])

success_text = (OUT_DIR / "11.13平特肖.txt").read_text(encoding="utf-8")
body = success_text.split("\n排行榜\n", 1)[0]
written = {}
for line in body.splitlines():
    if line.strip():
        zodiac, site = line.split(maxsplit=1)
        written[site] = zodiac

cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
cached = {e["target_id"]: e["values"] for e in cache["sites"]}

urls = list(dict.fromkeys(by_name[n].url for n in names))
specs = [BrowserFetchSpec(url=u) for u in urls]
caps, errs = fetch_browser_captures(specs, timeout=40, max_workers=1)

report = []
for name in names:
    target = by_name[name]
    rule = runtime.registry.rules.rule_for(target)
    capture = caps.get(target.url)
    row = {
        "name": name,
        "target_id": target.target_id,
        "mode": rule.get("mode"),
        "keyword": target.keyword,
        "written": written.get(name, ""),
        "cached_316": cached.get(target.target_id, {}).get("316", ""),
        "cached_315": cached.get(target.target_id, {}).get("315", ""),
    }
    if capture is None:
        row["status"] = "抓取失败"
        row["detail"] = errs.get(target.url, "")
        print(f"ERR  {name:<12} {row['detail'][:80]}")
        report.append(row)
        continue
    page = capture.body or ""
    (HERE / "bodies").mkdir(exist_ok=True)
    (HERE / "bodies" / f"{name}-verify.txt").write_text(page, encoding="utf-8")
    lines = runtime.registry.parse_issue_lines(page, target, ISSUE)
    zodiacs = [extract_target_zodiac(line, target, rule) for line in lines]
    row["parsed"] = zodiacs
    row["parsed_lines"] = [l.strip() for l in lines]
    row["status"] = "解析成功" if len(zodiacs) == 1 else f"候选{len(zodiacs)}条"
    row["match_written"] = bool(zodiacs) and zodiacs[0] == written.get(name)
    # 页面上所有「含 317 且带开奖状态」的行，用于人工核对该期是否唯一
    page_hits = [
        l.strip()
        for l in page.splitlines()
        if re.search(r"(?<!\d)317(?!\d)", l) and re.search(r"开|開", l)
    ]
    row["page_317_lines"] = page_hits[:10]
    print("=" * 74)
    print(
        f"{name} [{target.target_id}] mode={rule.get('mode')} "
        f"写入={written.get(name, '-')!r} 解析={zodiacs} 一致={row['match_written']}"
    )
    for line in row["parsed_lines"]:
        print("   命中:", line[:110])
    if not row["parsed_lines"]:
        for line in page_hits[:5]:
            print("   页面317行:", line[:110])
    report.append(row)

(HERE / f"verify-{ISSUE}.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("\n汇总：")
for row in report:
    print(
        f"  {row['name']:<12} 写入={row['written'] or '-':<4} "
        f"解析={row.get('parsed') or '-'} 一致={row.get('match_written')}"
    )
print("报告：", HERE / f"verify-{ISSUE}.json")
