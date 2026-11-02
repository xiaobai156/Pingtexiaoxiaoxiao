from __future__ import annotations

from pathlib import Path

import run_single
from pingte.fetch.http_fetcher import FetchSession


class _Outcome:
    return_code = 0


class _Runner:
    def __init__(self) -> None:
        self.kwargs = None

    def run(self, issue, timeout, **kwargs):
        self.kwargs = kwargs
        return _Outcome()


class _Runtime:
    def __init__(self, runner: _Runner) -> None:
        self.runner = runner

    def single_runner(self):
        return self.runner


def test_single_entry_passes_shared_fetch_session(monkeypatch):
    runner = _Runner()
    monkeypatch.setattr(
        run_single,
        "build_runtime",
        lambda project_dir: _Runtime(runner),
    )

    assert run_single.main(["123", "--audit"]) == 0
    assert isinstance(runner.kwargs["session"], FetchSession)
