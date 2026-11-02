"""平特失败清单定向修复：probe / parse / apply 三步，只处理清单内站点。

用法：
  python repair.py probe  --failure 路径 --issue 306
  python repair.py parse  --failure 路径 --issue 306
  python repair.py apply  --failure 路径 --issue 306 --label 11.2 [--write]
  python repair.py inspect --url URL --issue 306
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pingte.application.runtime import build_runtime
from pingte.application.site_pipeline import SitePipeline
from pingte.domain.zodiac import ZODIACS
from pingte.fetch.browser_fetcher import BrowserFetchSpec, fetch_browser_captures
from pingte.fetch.http_fetcher import FetchSession
from pingte.storage.cache import CacheStore
from pingte.storage.evidence import EvidenceStore
from pingte.storage.output import atomic_write_text, build_output

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(
    r"C:/Users/Administrator/Desktop/每天工具/爬虫合集/大围杀号生肖数据统一归纳"
)


def load_failures(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
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


def scoped_pipeline(names: list[str]):
    runtime = build_runtime(ROOT)
    by_name = {target.name: target for target in runtime.targets}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise SystemExit(f"名单不在活跃目标中：{missing}")
    subset = [by_name[name] for name in names]
    pipeline = SitePipeline(
        subset,
        runtime.registry,
        fetch_text=runtime.pipeline.fetch_text,
        fetch_browser_texts=runtime.pipeline.fetch_browser_texts,
        max_workers=5,
    )
    return runtime, subset, pipeline


def cmd_probe(args) -> int:
    items = load_failures(Path(args.failure))
    specs = [BrowserFetchSpec(url=item["url"]) for item in items]
    captures, errors = fetch_browser_captures(specs, timeout=25, max_workers=5)
    report = []
    for item in items:
        capture = captures.get(item["url"])
        row = dict(item)
        row["reached"] = capture is not None
        row["error"] = errors.get(item["url"], "")
        if capture:
            body = capture.body or ""
            row["final_url"] = capture.final_url
            row["body_len"] = len(body)
            row["has_issue"] = bool(
                re.search(rf"(?<!\d){args.issue}(?!\d)", body)
            )
            row["issue_lines"] = [
                line.strip()
                for line in body.splitlines()
                if re.search(rf"(?<!\d){args.issue}(?!\d)", line)
            ][:12]
        report.append(row)
    out = HERE / f"probe-{args.issue}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in report:
        print(
            f"{'OK ' if row['reached'] else 'ERR'} {row['name']:<6} "
            f"原失败阶段={row['stage']} 长度={row.get('body_len', 0)} "
            f"{row['error'][:70]}"
        )
        for line in row.get("issue_lines", []):
            print("     |", line[:120])
    print("报告：", out)
    return 0


def cmd_parse(args) -> int:
    items = load_failures(Path(args.failure))
    names = [item["name"] for item in items]
    runtime, subset, pipeline = scoped_pipeline(names)
    results = pipeline.run(args.issue, 30, session=FetchSession())
    rows = []
    for item in results:
        target = item.target
        row = {
            "target_id": target.target_id,
            "name": target.name,
            "url": target.url,
            "position": target.position,
        }
        if item.error:
            row["status"] = "抓取失败"
            row["detail"] = item.error[:300]
        elif item.outcome is None or not item.outcome.ok:
            failure = item.outcome.failure if item.outcome else None
            row["status"] = "校验失败"
            row["detail"] = (
                f"{failure.code.value} | {failure.message}" if failure else "无结果"
            )
        else:
            row["status"] = "成功"
            row["zodiac"] = item.outcome.result.candidate.zodiac
            row["raw_line"] = item.outcome.result.candidate.raw_line
        rows.append(row)
    out = HERE / f"parse-{args.issue}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in rows:
        print(
            f"{row['status']:<6} {row['name']:<6} {row.get('zodiac', ''):<4} "
            f"{row.get('detail', '')[:110]}"
        )
    print("报告：", out)
    return 0


def cmd_apply(args) -> int:
    label = args.label
    success_txt = OUT_DIR / f"{label}平特肖.txt"
    failure_txt = OUT_DIR / f"{label}平特肖-失败.txt"
    items = load_failures(Path(args.failure))
    names = [item["name"] for item in items]
    runtime, subset, pipeline = scoped_pipeline(names)
    results = pipeline.run(args.issue, 30, session=FetchSession())

    fixes = []
    problems = []
    for item in results:
        target = item.target
        if item.error or item.outcome is None or not item.outcome.ok:
            reason = item.error or (
                item.outcome.failure.message
                if item.outcome and item.outcome.failure
                else "无结果"
            )
            problems.append((target.name, reason))
            continue
        result = item.outcome.result
        zodiac = result.candidate.zodiac
        if (
            not 1 <= len(zodiac) <= 2
            or len(set(zodiac)) != len(zodiac)
            or any(ch not in ZODIACS for ch in zodiac)
        ):
            problems.append((target.name, f"生肖非法 {zodiac}"))
            continue
        fixes.append(result)

    print(f"本轮可修复 {len(fixes)}/{len(subset)}")
    for result in fixes:
        print(f"   + {result.candidate.zodiac} {result.target.name}")
    for name, reason in problems:
        print(f"   保留失败 {name}：{reason[:110]}")

    if not args.write:
        print("预演：未写文件")
        return 0
    if fixes:
        backup = HERE / f"backup-{label}-{datetime.now():%Y%m%d-%H%M%S}"
        backup.mkdir(parents=True, exist_ok=True)
        for path in (success_txt, failure_txt, ROOT / "recent_10_cache.json"):
            if path.exists():
                shutil.copy2(path, backup / path.name)
        evidence_path = ROOT / "evidence" / f"{label}-{args.issue}期.json"
        if evidence_path.exists():
            shutil.copy2(evidence_path, backup / evidence_path.name)
        print("备份：", backup)

        original = success_txt.read_text(encoding="utf-8")
        body = original.split("\n排行榜\n", 1)[0]
        records = [line.strip() for line in body.splitlines() if line.strip()]
        known = {}
        for line in records:
            zodiac, name = line.split(maxsplit=1)
            known[name] = zodiac
        for result in fixes:
            name = result.target.name
            zodiac = result.candidate.zodiac
            if name in known and known[name] != zodiac:
                print(f"中止：成功文件已有{known[name]}，本轮为{zodiac}（{name}）")
                return 1
            known.setdefault(name, zodiac)
        order = {target.name: index for index, target in enumerate(runtime.targets)}
        unknown = [name for name in known if name not in order]
        if unknown:
            print("中止：成功文件含非活跃目录", unknown)
            return 1
        ordered = [
            f"{known[name]} {name}"
            for name in sorted(known, key=lambda item: order[item])
        ]
        atomic_write_text(success_txt, build_output(ordered))
        print("成功TXT已写入，共", len(ordered), "条")

        outcome = CacheStore(ROOT / "recent_10_cache.json").update_selected(
            fixes, args.issue
        )
        print("缓存更新：", outcome.ok, outcome.message or "ok")
        if not outcome.ok:
            shutil.copy2(backup / success_txt.name, success_txt)
            print("已回滚成功TXT")
            return 1

        if evidence_path.exists():
            payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
            rows = payload.get("results", [])
            have = {row.get("target_id") for row in rows}
            tmp = HERE / f"delta-{args.issue}.json"
            EvidenceStore(tmp).write(args.issue, fixes)
            delta = json.loads(tmp.read_text(encoding="utf-8"))["results"]
            rows.extend(row for row in delta if row["target_id"] not in have)
            payload["results"] = rows
            payload["repaired_at"] = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
            atomic_write_text(
                evidence_path,
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            )
            print("证据已合并，共", len(rows), "条")

    original_text = (
        failure_txt.read_text(encoding="utf-8") if failure_txt.exists() else ""
    )
    fixed_names = {result.target.name for result in fixes}
    kept = [
        block
        for block in original_text.split("\n\n")
        if block.startswith("失败 ") and block.split(maxsplit=2)[1] not in fixed_names
    ]
    categories = {}
    for block in kept:
        stage = block.split("阶段: ", 1)[1].split(" 原因", 1)[0]
        categories[stage] = categories.get(stage, 0) + 1
    if kept:
        text = "\n\n".join(
            ["\n\n".join(kept), "\n".join(
                ["失败分类统计"] + [f"{k} {v}条" for k, v in categories.items()]
            )]
        ) + "\n"
        atomic_write_text(failure_txt, text)
        print("失败TXT保留", len(kept), "条")
    elif failure_txt.exists():
        failure_txt.unlink()
        print("失败项已全部清除，失败TXT已删除")
    return 0


def cmd_inspect(args) -> int:
    captures, errors = fetch_browser_captures(
        [BrowserFetchSpec(url=args.url)], timeout=25, max_workers=1
    )
    capture = captures.get(args.url)
    if not capture:
        print("抓取失败：", errors.get(args.url))
        return 1
    body = capture.body or ""
    print("最终URL:", capture.final_url, "长度:", len(body))
    hits = [
        index
        for index, line in enumerate(body.splitlines())
        if re.search(rf"(?<!\d){args.issue}(?!\d)", line)
    ]
    lines = body.splitlines()
    for index in hits:
        start = max(0, index - 3)
        end = min(len(lines), index + 4)
        print("---- 命中行", index)
        for offset in range(start, end):
            mark = ">" if offset == index else " "
            print(f"{mark} {lines[offset][:160]}")
    out = HERE / f"inspect-{args.issue}.txt"
    out.write_text(body, encoding="utf-8")
    print("正文快照：", out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--failure", required=True)
    probe.add_argument("--issue", required=True)
    probe.set_defaults(func=cmd_probe)

    parse = sub.add_parser("parse")
    parse.add_argument("--failure", required=True)
    parse.add_argument("--issue", required=True)
    parse.set_defaults(func=cmd_parse)

    apply = sub.add_parser("apply")
    apply.add_argument("--failure", required=True)
    apply.add_argument("--issue", required=True)
    apply.add_argument("--label", required=True)
    apply.add_argument("--write", action="store_true")
    apply.set_defaults(func=cmd_apply)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--url", required=True)
    inspect.add_argument("--issue", required=True)
    inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
