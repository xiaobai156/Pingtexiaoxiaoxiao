from __future__ import annotations

import json
from pathlib import Path

from pingte.application.multi_issue import MultiIssueRunner, normalize_issues
from pingte.application.single_issue import SingleRunOutcome
from pingte.domain.models import Target
from pingte.storage.cache import CacheStore


def test_normalize_issues_accepts_spaces_commas_and_deduplicates():
    assert normalize_issues(["187,188", "187 189", "188"]) == ["187", "188", "189"]


def test_multi_runner_disables_cache_and_reports_only_all_issue_failures(tmp_path):
    targets = [
        Target("https://a", "top", "目录A", "成语平特", "PT-A", 1),
        Target("https://b", "top", "目录B", "成语平特", "PT-B", 1),
    ]
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text(json.dumps({"issues": [186], "sites": []}), encoding="utf-8")

    class FakeSingle:
        def __init__(self):
            self.calls = []

        def run(self, issue, timeout, **kwargs):
            self.calls.append((issue, kwargs.get("update_cache")))
            return SingleRunOutcome(0 if issue == "188" else 1, _RunResult(issue, issue == "188"), Path("s"), Path("f"))

    class _RunResult:
        def __init__(self, issue, success):
            self.issue = issue
            self.successes = ()
            self.failures = ()
            self.success_target_ids = {"PT-A"} if success else set()

    runner = MultiIssueRunner(
        targets,
        FakeSingle(),
        output_dir=tmp_path / "output",
        today=None,
    )

    outcome = runner.run(["187", "188"], 5)

    assert outcome.return_code == 0
    assert runner.single.calls == [("187", False), ("188", False)]
    assert not (tmp_path / "recent_10_cache.json").read_text(encoding="utf-8").endswith("\n\n")
    summary = outcome.summary_path.read_text(encoding="utf-8")
    assert "全部失败目录数：1" in summary
    assert "目录B" in summary
