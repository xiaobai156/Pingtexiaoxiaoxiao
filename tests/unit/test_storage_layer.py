from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.models import Candidate, SourceDocument, Target, ValidatedResult
from pingte.storage.cache import CacheStore
from pingte.storage.evidence import EvidenceStore
from pingte.storage.output import build_failure_output, build_output, default_output_paths


def target(name: str = "目录A") -> Target:
    return Target("https://example.test/topic/1.html", "top", name, "成语平特", "PT-1", 3)


def result(value: str = "鼠", name: str = "目录A", issue: str = "164") -> ValidatedResult:
    item = target(name)
    document = SourceDocument(
        "http-main",
        item.url,
        True,
        "164期成语平特【鼠】开00准",
        "sha256-test",
        "2026-08-01T12:00:00+08:00",
    )
    candidate = Candidate(
        item.target_id,
        issue,
        value,
        document.text,
        document.source,
        document.source_url,
        "section-start",
        "section-end",
    )
    return ValidatedResult(item, issue, candidate, document)


def test_build_output_and_paths_keep_existing_user_format():
    output = build_output(["牛马 目录A", "蛇鼠 目录B", "狗 目录C", "猪狗 目录D"])

    assert output.endswith("排行榜\n狗 2\n鼠 1\n牛 1\n蛇 1\n马 1\n猪 1\n")
    assert default_output_paths("164", output_dir=Path("out"), today=date(2026, 6, 15)) == (
        Path("out/6.15平特肖.txt"),
        Path("out/6.15平特肖-失败.txt"),
    )


def test_build_failure_output_uses_two_line_format_and_category_summary():
    failures = [
        FailureDetail(
            code=FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW,
            message="指定期数不在tail方向最近3组有效候选内",
            target_id="PT-0001",
            name="目录A",
            url="https://example.test/topic/1.html",
            position="tail",
            keyword="成语平特",
            issue="211",
            visible_issues=("212", "210", "209"),
        ),
        FailureDetail(
            code=FailureCode.ANCHOR_MISSING,
            message="指定目录或栏目锚点未找到，禁止仅凭关键字取值",
            target_id="PT-0002",
            name="目录B",
            url="https://example.test/topic/2.html",
            position="top",
            keyword="成语平特",
            issue="211",
        ),
    ]

    assert build_failure_output(failures) == (
        "失败 目录A https://example.test/topic/1.html 方向: bottom 期数: 211\n"
        "阶段: 指定期数校验 原因: 指定期数不在tail方向最近3组有效候选内；"
        "当前可见期数：212期、210期、209期\n\n"
        "失败 目录B https://example.test/topic/2.html 方向: top 期数: 211\n"
        "阶段: 栏目锚点校验 原因: 指定目录或栏目锚点未找到，禁止仅凭关键字取值\n\n"
        "失败分类统计\n"
        "方向范围外 1条\n"
        "锚点缺失 1条\n"
    )


def test_build_failure_output_is_empty_without_failures():
    assert build_failure_output([]) == ""


def test_cache_store_updates_atomically_and_preserves_identity(tmp_path):
    path = tmp_path / "recent_10_cache.json"
    store = CacheStore(path)

    assert store.update([result()], [target()], "164").ok

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    assert data["issues"] == [164]
    assert data["sites"][0]["target_id"] == "PT-1"
    assert data["sites"][0]["values"] == {"164": "鼠"}


def test_cache_store_refuses_same_issue_conflict_without_overwriting(tmp_path):
    path = tmp_path / "recent_10_cache.json"
    store = CacheStore(path)
    assert store.update([result("鼠")], [target()], "164").ok
    before = path.read_bytes()

    outcome = store.update([result("牛")], [target()], "164")

    assert not outcome.ok
    assert "冲突" in outcome.message
    assert path.read_bytes() == before


def test_evidence_store_records_source_and_parser_provenance(tmp_path):
    path = tmp_path / "evidence" / "run.json"

    EvidenceStore(path).write("164", [result()])

    payload = json.loads(path.read_text(encoding="utf-8"))
    row = payload["results"][0]
    assert row["target_id"] == "PT-1"
    assert row["zodiac"] == "鼠"
    assert row["raw_line"] == "164期成语平特【鼠】开00准"
    assert row["source_sha256"] == "sha256-test"
    assert row["rule_version"] == 3


def test_evidence_store_does_not_accept_unvalidated_values(tmp_path):
    with pytest.raises(TypeError):
        EvidenceStore(tmp_path / "evidence.json").write("164", ["鼠 目录A"])
