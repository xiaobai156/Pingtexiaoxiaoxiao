from __future__ import annotations

from pathlib import Path

from pingte.application.runtime import build_runtime


PROJECT = Path(__file__).parents[2]


def test_runtime_builds_all_targets_with_one_dedicated_rule_each():
    runtime = build_runtime(PROJECT, output_dir=PROJECT / "tmp-output", evidence_dir=PROJECT / "tmp-evidence")

    assert len(runtime.targets) == 236
    assert all(runtime.registry.rules.has_dedicated_parser(target) for target in runtime.targets)
    assert runtime.cache_store.path.name == "recent_10_cache.json"


def test_formal_entries_do_not_import_legacy_scripts():
    single_source = (PROJECT / "run_single.py").read_text(encoding="utf-8")
    multi_source = (PROJECT / "run_multi.py").read_text(encoding="utf-8")

    assert "zodiac_scraper" not in single_source
    assert "zodiac_scraper" not in multi_source
