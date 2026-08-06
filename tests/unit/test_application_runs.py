from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pingte.application.single_issue import SingleIssueRunner
from pingte.application.site_pipeline import PipelineTargetResult
from pingte.domain.models import Candidate, SourceDocument, Target, ValidatedResult
from pingte.storage.cache import CacheStore


def make_result(issue: str = "164", zodiac: str = "鼠") -> ValidatedResult:
    target = Target("https://example.test/topic/1.html", "top", "目录A", "成语平特", "PT-1", 1)
    document = SourceDocument(
        "http-main",
        target.url,
        True,
        f"{issue}期成语平特【{zodiac}】开00准",
        "sha-test",
        "2026-08-01T12:00:00+08:00",
    )
    candidate = Candidate(target.target_id, issue, zodiac, document.text, document.source, document.source_url)
    return ValidatedResult(target, issue, candidate, document)


class FakePipeline:
    def __init__(self, result: ValidatedResult):
        self.result = result

    def run(self, issue: str, timeout: int, *, session=None):
        assert issue == self.result.issue
        return [PipelineTargetResult(self.result.target, "source", _Outcome(self.result))]


class _Outcome:
    def __init__(self, result: ValidatedResult):
        self.result = result
        self.zodiac = result.candidate.zodiac
        self.failure = None

    @property
    def ok(self):
        return True


def test_single_runner_commits_output_cache_and_evidence(tmp_path):
    result = make_result()
    runner = SingleIssueRunner(
        [result.target],
        FakePipeline(result),
        cache_store=CacheStore(tmp_path / "recent_10_cache.json"),
        output_dir=tmp_path / "output",
        evidence_dir=tmp_path / "evidence",
        today=date(2026, 8, 1),
    )

    outcome = runner.run("164", 5)

    assert outcome.return_code == 0
    assert outcome.success_path.read_text(encoding="utf-8") == "鼠 目录A\n\n排行榜\n鼠 1\n"
    assert outcome.failure_path.read_text(encoding="utf-8") == ""
    assert json.loads((tmp_path / "recent_10_cache.json").read_text(encoding="utf-8-sig"))["issues"] == [164]
    evidence = list((tmp_path / "evidence").glob("*.json"))
    assert len(evidence) == 1


def test_single_runner_audit_is_read_only(tmp_path):
    result = make_result()
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text('{"issues": [163], "sites": []}', encoding="utf-8")
    runner = SingleIssueRunner(
        [result.target],
        FakePipeline(result),
        cache_store=CacheStore(cache_path),
        output_dir=tmp_path / "output",
        evidence_dir=tmp_path / "evidence",
        today=date(2026, 8, 1),
    )

    outcome = runner.run("164", 5, audit=True)

    assert outcome.return_code == 0
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "evidence").exists()
    assert json.loads(cache_path.read_text(encoding="utf-8"))["issues"] == [163]


def test_single_runner_rejects_historical_conflict_before_output_and_cache(tmp_path):
    cache_path = tmp_path / "recent_10_cache.json"
    cache = CacheStore(cache_path)
    cached = make_result("164", "鼠")
    assert cache.update([cached], [cached.target], "164").ok
    before = cache_path.read_bytes()

    current = make_result("164", "牛")
    runner = SingleIssueRunner(
        [current.target],
        FakePipeline(current),
        cache_store=cache,
        output_dir=tmp_path / "output",
        evidence_dir=tmp_path / "evidence",
        today=date(2026, 8, 1),
    )

    outcome = runner.run("164", 5)

    assert outcome.return_code == 1
    assert outcome.run_result.successes == ()
    assert "历史缓存同一期数据冲突" in outcome.failure_path.read_text(encoding="utf-8")
    assert "牛 目录A" not in outcome.success_path.read_text(encoding="utf-8")
    assert cache_path.read_bytes() == before
    assert not (tmp_path / "evidence").exists()
