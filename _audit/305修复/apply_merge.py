"""305 期失败站点修复落盘：重跑白名单 25 站，合并成功TXT、当期缓存、证据，并清理失败TXT。

仅处理失败列表中的站点，不跑全量；任何异常都中止且不改动正式文件。
"""
from __future__ import annotations

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
from pingte.fetch.http_fetcher import FetchSession
from pingte.storage.cache import CacheStore
from pingte.storage.evidence import EvidenceStore
from pingte.storage.output import atomic_write_text, build_output

HERE = Path(__file__).resolve().parent
FAIL = Path(
    r"C:/Users/Administrator/.dsh/attachments/v1/files/a1/"
    r"a16c9d0e4598e4cfeba7d0223b84e8684614874dfd8bfa70ee151e11baca46bf/11.1平特肖-失败.txt"
)
OUT_DIR = Path(
    r"C:/Users/Administrator/Desktop/每天工具/爬虫合集/大围杀号生肖数据统一归纳"
)
SUCCESS_TXT = OUT_DIR / "11.1平特肖.txt"
FAILURE_TXT = OUT_DIR / "11.1平特肖-失败.txt"
EXISTING = HERE / "repair_results.json"
ISSUE = "305"


def load_failures() -> list[dict]:
    text = FAIL.read_text(encoding="utf-8")
    return [
        {"name": m.group(1), "url": m.group(2)}
        for m in re.finditer(r"失败 (\S+) (\S+) 方向: (\S+) 期数: (\S+)", text)
    ]


def main(apply: bool) -> int:
    moments = datetime.now().strftime("%Y%m%d-%H%M%S")
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
    items = pipeline.run(ISSUE, 30, session=FetchSession())

    results = []
    problems = []
    previous = {
        row["target_id"]: row
        for row in json.loads(EXISTING.read_text(encoding="utf-8"))
    }
    for item in items:
        target = item.target
        if item.error or item.outcome is None or not item.outcome.ok:
            reason = item.error or (
                item.outcome.failure.message
                if item.outcome and item.outcome.failure
                else "无结果"
            )
            problems.append(f"{target.name}：{reason}")
            continue
        result = item.outcome.result
        if result is None:
            problems.append(f"{target.name}：结果为空")
            continue
        zodiac = result.candidate.zodiac
        if (
            not 1 <= len(zodiac) <= 2
            or len(set(zodiac)) != len(zodiac)
            or any(ch not in ZODIACS for ch in zodiac)
        ):
            problems.append(f"{target.name}：生肖非法 {zodiac}")
            continue
        old = previous.get(target.target_id, {}).get("zodiac")
        if old and old != zodiac:
            problems.append(
                f"{target.name}：两次解析不一致 上次{old} 本次{zodiac}"
            )
            continue
        results.append(result)

    if problems:
        print("中止：复跑存在未通过项")
        for problem in problems:
            print("  -", problem)
        return 1
    print(f"复跑通过 {len(results)}/{len(subset)}，开始合并")

    additions = {
        result.target.name: f"{result.candidate.zodiac} {result.target.name}"
        for result in results
    }
    original_success = SUCCESS_TXT.read_text(encoding="utf-8")
    body = original_success.split("\n排行榜\n", 1)[0]
    records = [line.strip() for line in body.splitlines() if line.strip()]
    known: dict[str, str] = {}
    for line in records:
        zodiac, name = line.split(maxsplit=1)
        known[name] = zodiac
    overwritten = [
        name
        for name, line in additions.items()
        if name in known and known[name] != line.split()[0]
    ]
    if overwritten:
        print("中止：成功文件已存在不同值", overwritten)
        return 1
    merged = dict(known)
    for name, line in additions.items():
        merged.setdefault(name, line.split()[0])
    order = {target.name: index for index, target in enumerate(runtime.targets)}
    unknown = [name for name in merged if name not in order]
    if unknown:
        print("中止：成功文件存在非活跃目录", unknown)
        return 1
    ordered = [
        f"{merged[name]} {name}"
        for name in sorted(merged, key=lambda item: order[item])
    ]
    new_success = build_output(ordered)

    backup = HERE / f"backup-{moments}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SUCCESS_TXT, backup / SUCCESS_TXT.name)
    if FAILURE_TXT.exists():
        shutil.copy2(FAILURE_TXT, backup / FAILURE_TXT.name)
    evidence_path = ROOT / "evidence" / f"11.1-{ISSUE}期.json"
    if evidence_path.exists():
        shutil.copy2(evidence_path, backup / evidence_path.name)
    shutil.copy2(ROOT / "recent_10_cache.json", backup / "recent_10_cache.json")
    print("备份：", backup)

    if not apply:
        print("预演：未写入。新增行样例：")
        for line in ordered:
            if line.split(maxsplit=1)[1] in additions:
                print("   +", line)
        return 0

    atomic_write_text(SUCCESS_TXT, new_success)
    print("成功TXT已写入，共", len(ordered), "条")

    cache_store = CacheStore(ROOT / "recent_10_cache.json")
    outcome = cache_store.update_selected(results, ISSUE)
    print("缓存更新：", outcome.ok, outcome.message or "ok")
    if not outcome.ok:
        print("缓存更新失败，回滚成功TXT")
        shutil.copy2(backup / SUCCESS_TXT.name, SUCCESS_TXT)
        return 1

    if evidence_path.exists():
        payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        rows = payload.get("results", [])
        have = {row.get("target_id") for row in rows}
        tmp = HERE / "evidence-delta.json"
        EvidenceStore(tmp).write(ISSUE, results)
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

    remaining = [
        block
        for block in FAILURE_TXT.read_text(encoding="utf-8").split("\n\n")
        if block.startswith("失败 ")
        and block.split(maxsplit=2)[1] not in additions
    ]
    if remaining:
        print("仍有失败项", len(remaining), "条，失败TXT保留")
        return 0
    FAILURE_TXT.unlink()
    print("失败项已全部清除，失败TXT已删除")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--apply" in sys.argv))
