import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.compat import zodiac_multi
from tests.compat.zodiac_scraper import Target

PROJECT_ROOT = Path(__file__).resolve().parent


def write_issue_files(paths: dict[str, Path], success: str = "", failure: str = "") -> None:
    paths["success"].parent.mkdir(parents=True, exist_ok=True)
    paths["success"].write_text(success, encoding="utf-8")
    paths["failure"].write_text(failure, encoding="utf-8")


def test_normalize_issues_deduplicates_and_preserves_order():
    assert zodiac_multi.normalize_issues(["187,188", "187 189", "188"]) == [
        "187",
        "188",
        "189",
    ]


def test_main_forwards_normalized_manual_issues(monkeypatch):
    calls = []
    monkeypatch.setattr(
        zodiac_multi,
        "run_multi",
        lambda issues, timeout: calls.append((issues, timeout)) or 0,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["zodiac_multi.py", "211,210", "211", "--timeout", "8"],
    )

    assert zodiac_multi.main() == 0
    assert calls == [(["211", "210"], 8)]


def test_main_rejects_invalid_issue_without_running(monkeypatch, capsys):
    monkeypatch.setattr(
        zodiac_multi,
        "run_multi",
        lambda *_args: pytest.fail("run_multi must not be called"),
    )
    monkeypatch.setattr(sys, "argv", ["zodiac_multi.py", "211", "bad"])

    assert zodiac_multi.main() == 2
    assert "期数必须是数字" in capsys.readouterr().err


def test_main_prompts_when_no_issues_are_passed(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["zodiac_multi.py", "--timeout", "6"])
    monkeypatch.setattr("builtins.input", lambda _prompt: "211 210")
    monkeypatch.setattr(
        zodiac_multi,
        "run_multi",
        lambda issues, timeout: calls.append((issues, timeout)) or 0,
    )

    assert zodiac_multi.main() == 0
    assert calls == [(["211", "210"], 6)]


def test_run_multi_returns_zero_when_any_issue_succeeds_and_skips_cache(tmp_path, monkeypatch):
    calls = []

    sessions = []

    def fake_run(issue, output, timeout, update_cache, fetch_session=None):
        calls.append((issue, timeout, update_cache))
        sessions.append(fetch_session)
        paths = {"success": output, "failure": output.with_suffix(".errors.txt")}
        write_issue_files(paths, success="鼠 目录A\n" if issue == "188" else "")
        return 0 if issue == "188" else 1

    monkeypatch.setattr(zodiac_multi, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(zodiac_multi, "TARGETS", [Target("https://a", "top", "目录A", "平特一肖")])
    monkeypatch.setattr(zodiac_multi.zodiac_scraper, "run", fake_run)

    assert zodiac_multi.run_multi(["187", "188"], 9) == 0
    assert calls == [("187", 9, False), ("188", 9, False)]
    assert sessions[0] is sessions[1]
    assert sessions[0] is not None
    assert (tmp_path / "多期187_188平特一肖-失败汇总.txt").exists()


def test_run_multi_returns_nonzero_when_all_issues_fail_and_still_writes_summary(tmp_path, monkeypatch):
    def fake_run(issue, output, timeout, update_cache, fetch_session=None):
        paths = {"success": output, "failure": output.with_suffix(".errors.txt")}
        write_issue_files(paths, failure=f"失败，目录：目录A，网址：https://a/{issue}\n")
        return 1

    monkeypatch.setattr(zodiac_multi, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(zodiac_multi, "TARGETS", [Target("https://a", "top", "目录A", "平特一肖")])
    monkeypatch.setattr(zodiac_multi.zodiac_scraper, "run", fake_run)

    assert zodiac_multi.run_multi(["187", "188"], 9) != 0
    assert (tmp_path / "多期187_188平特一肖-失败汇总.txt").exists()


def test_run_multi_returns_nonzero_on_program_error_and_continues_summary(tmp_path, monkeypatch):
    calls = []

    def fake_run(issue, output, timeout, update_cache, fetch_session=None):
        calls.append(issue)
        if issue == "187":
            raise RuntimeError("boom")
        paths = {"success": output, "failure": output.with_suffix(".errors.txt")}
        write_issue_files(paths, success="鼠 目录A\n")
        return 0

    monkeypatch.setattr(zodiac_multi, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(zodiac_multi, "TARGETS", [Target("https://a", "top", "目录A", "平特一肖")])
    monkeypatch.setattr(zodiac_multi.zodiac_scraper, "run", fake_run)

    assert zodiac_multi.run_multi(["187", "188"], 9) != 0
    assert calls == ["187", "188"]
    summary = (tmp_path / "多期187_188平特一肖-失败汇总.txt").read_text(encoding="utf-8")
    assert "RuntimeError: boom" in summary


def test_failure_summary_keeps_same_name_targets_separate(tmp_path):
    issue_results = {
        "187": {"success": tmp_path / "187.txt", "failure": tmp_path / "187.errors.txt"},
    }
    write_issue_files(
        issue_results["187"],
        failure=(
            "原因A，目录：同名目录，网址：https://a\n"
            "原因B，目录：同名目录，网址：https://b\n"
        ),
    )
    targets = [
        Target("https://a", "top", "同名目录", "关键字A"),
        Target("https://b", "tail", "同名目录", "关键字B"),
    ]

    text = zodiac_multi.build_multi_failure_summary(["187"], targets, issue_results)

    assert "全部失败目录数：2" in text
    assert "原因A，目录：同名目录，网址：https://a" in text
    assert "原因B，目录：同名目录，网址：https://b" in text
    assert text.count("同名目录 | ") == 2


def make_fake_python(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "python.cmd").write_text(
        "@echo off\r\n"
        ">\"%CAPTURE_FILE%\" echo(%2\r\n"
        "exit /b %FAKE_PYTHON_EXIT%\r\n",
        encoding="ascii",
    )
    return fake_bin


@pytest.mark.parametrize("batch_name", ["run.bat", "run_multi.bat"])
def test_batch_files_return_python_errorlevel(tmp_path, batch_name):
    source = PROJECT_ROOT / batch_name
    batch = tmp_path / batch_name
    shutil.copyfile(source, batch)
    fake_bin = make_fake_python(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "CAPTURE_FILE": str(tmp_path / "captured.txt"),
        "FAKE_PYTHON_EXIT": "7",
    }

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(batch), "187"],
        input="\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 7


def test_run_multi_batch_does_not_expand_interactive_cmd_metacharacters(tmp_path):
    batch = tmp_path / "run_multi.bat"
    shutil.copyfile(PROJECT_ROOT / "run_multi.bat", batch)
    fake_bin = make_fake_python(tmp_path)
    capture = tmp_path / "captured.txt"
    injected = tmp_path / "injected.txt"
    entered = f"187 & echo injected>{injected}"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "CAPTURE_FILE": str(capture),
        "FAKE_PYTHON_EXIT": "0",
    }

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(batch)],
        input=f"{entered}\n\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 0
    assert capture.read_text(encoding="utf-8").strip().strip('"') == entered
    assert not injected.exists()
