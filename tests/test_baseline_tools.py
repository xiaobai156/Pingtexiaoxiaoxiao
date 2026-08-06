import hashlib
import json
import sys

import pytest

from tools.freeze_baseline import build_manifest, main


def sha256_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_manifest_preserves_result_order_failures_and_hashes(tmp_path):
    config_path = tmp_path / "targets.json"
    cache_path = tmp_path / "recent_10_cache.json"
    success_path = tmp_path / "7.30平特一肖.txt"
    failure_path = tmp_path / "7.30平特一肖-失败.txt"

    config_text = json.dumps(
        {
            "targets": [
                {"url": "https://a", "position": "top", "name": "目录A", "keyword": "平特一肖"},
                {"url": "https://b", "position": "tail", "name": "目录B", "keyword": "成语平特"},
                {"url": "https://c", "position": "top", "name": "目录C", "keyword": "两字平特"},
            ],
            "special_parse_targets": [
                {"url_contains": "https://a", "name": "目录A"},
                {"url_contains": "https://b", "name": "目录B"},
                {"url_contains": "https://c", "name": "目录C"},
            ],
        },
        ensure_ascii=False,
    )
    cache_text = json.dumps(
        {
            "issues": ["211"],
            "sites": [
                {"name": "目录A", "values": {"211": "虎"}},
                {"name": "目录B", "values": {"211": "狗"}},
            ],
        },
        ensure_ascii=False,
    )
    success_text = "虎 目录A\n狗 目录B\n\n排行榜\n虎 1\n狗 1\n"
    failure_text = "指定期数不存在，目录：目录C，网址：https://c\n"

    config_path.write_text(config_text, encoding="utf-8")
    cache_path.write_text(cache_text, encoding="utf-8")
    success_path.write_text(success_text, encoding="utf-8")
    failure_path.write_text(failure_text, encoding="utf-8")

    manifest = build_manifest(
        issue="211",
        config_path=config_path,
        cache_path=cache_path,
        success_path=success_path,
        failure_path=failure_path,
        test_summary="191 passed",
        compile_summary="passed",
        created_at="2026-07-30T23:30:00+08:00",
    )

    assert manifest["schema_version"] == 1
    assert manifest["issue"] == "211"
    assert manifest["config_summary"] == {
        "target_count": 3,
        "dedicated_rule_count": 3,
    }
    assert manifest["success_lines"] == ["虎 目录A", "狗 目录B"]
    assert manifest["failure_lines"] == [
        "指定期数不存在，目录：目录C，网址：https://c"
    ]
    assert manifest["cache_issue_values"] == [
        {"name": "目录A", "value": "虎"},
        {"name": "目录B", "value": "狗"},
    ]
    assert manifest["files"]["success"]["sha256"] == sha256_file(success_path)
    assert manifest["files"]["failure"]["sha256"] == sha256_file(failure_path)
    assert manifest["verification"] == {
        "tests": "191 passed",
        "py_compile": "passed",
    }


def test_build_manifest_rejects_target_in_both_success_and_failure(tmp_path):
    config_path = tmp_path / "targets.json"
    cache_path = tmp_path / "recent_10_cache.json"
    success_path = tmp_path / "success.txt"
    failure_path = tmp_path / "failure.txt"

    config_path.write_text(
        json.dumps(
            {
                "targets": [
                    {"url": "https://a", "position": "top", "name": "目录A"},
                    {"url": "https://b", "position": "tail", "name": "目录B"},
                ],
                "special_parse_targets": [
                    {"url_contains": "https://a", "name": "目录A"},
                    {"url_contains": "https://b", "name": "目录B"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cache_path.write_text('{"issues":["211"],"sites":[]}', encoding="utf-8")
    success_path.write_text("虎 目录A\n狗 目录B\n\n排行榜\n", encoding="utf-8")
    failure_path.write_text(
        "指定期数不存在，目录：目录B，网址：https://b\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="同时出现在成功和失败"):
        build_manifest(
            issue="211",
            config_path=config_path,
            cache_path=cache_path,
            success_path=success_path,
            failure_path=failure_path,
            test_summary="passed",
            compile_summary="passed",
        )


def test_freeze_baseline_cli_writes_an_atomic_manifest(tmp_path, monkeypatch):
    config_path = tmp_path / "targets.json"
    cache_path = tmp_path / "recent_10_cache.json"
    success_path = tmp_path / "success.txt"
    failure_path = tmp_path / "failure.txt"
    manifest_path = tmp_path / "baselines" / "issue_211.json"

    config_path.write_text(
        json.dumps(
            {
                "targets": [{"url": "https://a", "position": "top", "name": "目录A"}],
                "special_parse_targets": [{"url_contains": "https://a", "name": "目录A"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cache_path.write_text(
        '{"issues":["211"],"sites":[{"name":"目录A","values":{"211":"虎"}}]}',
        encoding="utf-8",
    )
    success_path.write_text("虎 目录A\n\n排行榜\n虎 1\n", encoding="utf-8")
    failure_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze_baseline.py",
            "--issue",
            "211",
            "--config",
            str(config_path),
            "--cache",
            str(cache_path),
            "--success",
            str(success_path),
            "--failure",
            str(failure_path),
            "--manifest",
            str(manifest_path),
            "--tests",
            "passed",
            "--compile",
            "passed",
        ],
    )

    assert main() == 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["coverage_summary"] == {
        "target_count": 1,
        "success_target_count": 1,
        "failure_target_count": 0,
    }
    assert manifest["success_lines"] == ["虎 目录A"]
