"""失败 TXT 生成规则回归测试。

用户规则（2026-10-27）：单期抓取如果没有失败的目录，就不要生成失败 TXT；
已有的旧失败文件也要一并清掉，避免被误当成当期失败清单。
"""
from __future__ import annotations

from pathlib import Path

from pingte.domain.failures import FailureCode, FailureDetail
from pingte.storage.output import write_failure_output


def _failure(name: str = "某站") -> FailureDetail:
    return FailureDetail(
        code=FailureCode.ZODIAC_MISSING,
        message="没有解析到生肖",
        target_id="PT-9999",
        name=name,
        url="https://example.test/topic/1.html",
        position="top",
        keyword="成语平特",
        issue="299",
    )


def test_no_failures_does_not_create_file(tmp_path: Path):
    path = tmp_path / "10.27平特肖-失败.txt"
    write_failure_output(path, [])
    assert not path.exists()


def test_no_failures_removes_stale_file(tmp_path: Path):
    path = tmp_path / "10.27平特肖-失败.txt"
    path.write_text("旧内容", encoding="utf-8")
    write_failure_output(path, [])
    assert not path.exists()


def test_failures_still_written(tmp_path: Path):
    path = tmp_path / "10.27平特肖-失败.txt"
    write_failure_output(path, [_failure()])
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "某站" in text
    assert "失败分类统计" in text


def test_written_file_is_overwritten_not_appended(tmp_path: Path):
    path = tmp_path / "10.27平特肖-失败.txt"
    write_failure_output(path, [_failure("甲站")])
    write_failure_output(path, [_failure("乙站")])
    text = path.read_text(encoding="utf-8")
    assert "乙站" in text
    assert "甲站" not in text
