"""只读复跑：只对本项目失败列表中的站点，按 305 期执行专属解析（不写 TXT/缓存）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pingte.application.runtime import build_runtime
from pingte.application.site_pipeline import SitePipeline
from pingte.fetch.http_fetcher import FetchSession

FAIL = Path(
    r"C:/Users/Administrator/.dsh/attachments/v1/files/a1/"
    r"a16c9d0e4598e4cfeba7d0223b84e8684614874dfd8bfa70ee151e11baca46bf/11.1平特肖-失败.txt"
)
OUT = Path(__file__).with_name("repair_results.json")
ISSUE = "305"


def load_failures() -> list[dict]:
    text = FAIL.read_text(encoding="utf-8")
    return [
        {
            "name": m.group(1),
            "url": m.group(2),
            "position": "tail" if m.group(3) == "bottom" else m.group(3),
            "issue": m.group(4),
            "stage": m.group(5),
            "reason": m.group(6),
        }
        for m in re.finditer(
            r"失败 (\S+) (\S+) 方向: (\S+) 期数: (\S+)\n阶段: (\S+) 原因: (.+)",
            text,
        )
    ]


def main() -> int:
    failures = load_failures()
    names = [item["name"] for item in failures]
    runtime = build_runtime(ROOT)
    by_name = {target.name: target for target in runtime.targets}
    subset = [by_name[name] for name in names]
    pipeline = SitePipeline(
        subset,
        runtime.registry,
        fetch_text=runtime.pipeline.fetch_text,
        fetch_browser_texts=runtime.pipeline.fetch_browser_texts,
        max_workers=5,
    )
    results = pipeline.run(ISSUE, 30, session=FetchSession())
    report = []
    for item in results:
        target = item.target
        row = {
            "target_id": target.target_id,
            "name": target.name,
            "url": target.url,
            "position": target.position,
            "keyword": target.keyword,
        }
        if item.error:
            row["status"] = "抓取失败"
            row["detail"] = item.error[:300]
        elif item.outcome is None:
            row["status"] = "无解析结果"
        elif item.outcome.ok and item.outcome.result:
            result = item.outcome.result
            row["status"] = "成功"
            row["zodiac"] = result.candidate.zodiac
            row["raw_line"] = result.candidate.raw_line
            row["raw_order"] = (
                result.candidate.raw_zodiac_order or result.candidate.zodiac
            )
            row["raw_zodiac_order"] = result.candidate.raw_zodiac_order
        else:
            failure = item.outcome.failure
            row["status"] = "校验失败"
            row["detail"] = (
                f"{failure.code.value} | {failure.message}"
                if failure
                else "未返回失败详情"
            )
            if failure and failure.matched_line:
                row["matched_line"] = failure.matched_line
        report.append(row)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = [r for r in report if r["status"] == "成功"]
    print(f"成功 {len(ok)}/{len(report)}")
    for row in report:
        print(
            f"{row['status']:<6} {row['name']:<6} {row['target_id']} "
            f"{row.get('zodiac', '')} {row.get('detail', '')[:100]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
