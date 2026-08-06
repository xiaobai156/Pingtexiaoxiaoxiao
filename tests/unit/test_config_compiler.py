import json
from pathlib import Path

import pytest

from tests.compat import zodiac_scraper
from pingte.config.compiler import compile_site_configs, migrate_legacy_config
from pingte.config.loader import load_compiled_config, load_site_configs
from pingte.config.schema import ConfigValidationError, SiteConfig


def site_payload(
    target_id: str = "PT-0001",
    *,
    name: str = "目录A",
    url: str = "https://example.test/topic/1.html",
    keyword: str = "成语平特",
) -> dict:
    return {
        "schema_version": 1,
        "target_id": target_id,
        "rule_version": 1,
        "target": {
            "url": url,
            "position": "top",
            "name": name,
            "keyword": keyword,
        },
        "parser": {
            "url_contains": url,
            "name": name,
            "position": "top",
            "keyword": keyword,
            "mode": "header_section",
            "issue_format": "arabic_issue_exact",
            "data_structure": "confirmed_result_line",
            "section_boundary": "target_header_section",
            "source_strategy": "browser_main",
            "frame_scope": "main",
            "browser_selector": "body",
        },
        "auxiliary": {},
    }


def write_site(directory: Path, payload: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload['target_id']}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_site_config_builds_versioned_target_profile():
    site = SiteConfig.from_dict(site_payload())

    assert site.target.target_id == "PT-0001"
    assert site.target.rule_version == 1
    assert site.parser["url_contains"] == site.target.url


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_id", "bad-id", "target_id"),
        ("schema_version", 2, "schema_version"),
        ("rule_version", 0, "rule_version"),
    ],
)
def test_site_config_rejects_invalid_identity_or_version(field, value, message):
    payload = site_payload()
    if field == "rule_version":
        payload[field] = value
    else:
        payload[field] = value

    with pytest.raises(ConfigValidationError, match=message):
        SiteConfig.from_dict(payload)


def test_loader_rejects_filename_identity_mismatch(tmp_path):
    sites = tmp_path / "sites"
    path = write_site(sites, site_payload())
    path.rename(sites / "PT-9999.json")

    with pytest.raises(ConfigValidationError, match="文件名"):
        load_site_configs(sites)


def test_compiler_rejects_duplicate_name_and_exact_target(tmp_path):
    sites = tmp_path / "sites"
    write_site(sites, site_payload("PT-0001"))
    write_site(sites, site_payload("PT-0002"))

    with pytest.raises(ConfigValidationError, match="目录名重复"):
        compile_site_configs(sites, tmp_path / "targets.json")


def test_compiler_allows_shared_page_for_distinct_bound_targets(tmp_path):
    sites = tmp_path / "sites"
    shared_url = "https://example.test/"
    write_site(
        sites,
        site_payload(
            "PT-0001",
            name="成语栏目",
            url=shared_url,
            keyword="成语平特",
        ),
    )
    second = site_payload(
        "PT-0002",
        name="规律栏目",
        url=shared_url,
        keyword="规律二肖",
    )
    second["parser"]["name"] = "规律栏目"
    second["parser"]["keyword"] = "规律二肖"
    write_site(sites, second)

    compiled = compile_site_configs(sites, tmp_path / "targets.json")

    assert [item["target_id"] for item in compiled["targets"]] == [
        "PT-0001",
        "PT-0002",
    ]


def test_compiler_writes_deterministic_runtime_config(tmp_path):
    sites = tmp_path / "sites"
    write_site(sites, site_payload("PT-0002", name="目录B", url="https://b.test/"))
    write_site(sites, site_payload("PT-0001"))
    output = tmp_path / "targets.json"

    compiled = compile_site_configs(sites, output)
    loaded = load_compiled_config(output)

    assert loaded == compiled
    assert compiled["schema_version"] == 1
    assert [item["target_id"] for item in compiled["targets"]] == [
        "PT-0001",
        "PT-0002",
    ]
    assert all(item["rule_version"] == 1 for item in compiled["targets"])
    assert all(item["target_id"].startswith("PT-") for item in compiled["special_parse_targets"])


def test_legacy_migration_round_trips_all_runtime_rules(tmp_path):
    legacy = {
        "targets": [
            {
                "url": "https://example.test/topic/1.html",
                "position": "top",
                "name": "目录A",
                "keyword": "成语平特",
            }
        ],
        "special_image_targets": [],
        "special_followup_labels": [
            {
                "url_contains": "https://example.test/topic/1.html",
                "label": "平特一肖",
            }
        ],
        "special_parse_targets": [site_payload()["parser"]],
    }
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sites = tmp_path / "sites"

    migrated = migrate_legacy_config(legacy_path, sites)
    compiled = compile_site_configs(sites, tmp_path / "compiled.json")

    assert len(migrated) == 1
    assert compiled["targets"][0]["target_id"] == "PT-0001"
    assert compiled["special_followup_labels"] == legacy["special_followup_labels"]
    for key in (
        "url",
        "position",
        "name",
        "keyword",
    ):
        assert compiled["targets"][0][key] == legacy["targets"][0][key]


def test_legacy_migration_failure_leaves_no_partial_site_files(tmp_path):
    legacy = {
        "targets": [
            site_payload()["target"],
            {
                "url": "https://example.test/topic/2.html",
                "position": "tail",
                "name": "目录B",
                "keyword": "平特一肖",
            },
        ],
        "special_image_targets": [],
        "special_followup_labels": [],
        "special_parse_targets": [site_payload()["parser"]],
    }
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )
    sites = tmp_path / "sites"

    with pytest.raises(ConfigValidationError, match="目录B"):
        migrate_legacy_config(legacy_path, sites)

    assert not sites.exists() or list(sites.iterdir()) == []


def test_compiled_loader_rejects_manual_drift(tmp_path):
    output = tmp_path / "targets.json"
    payload = {
        "schema_version": 1,
        "targets": [],
        "special_image_targets": [],
        "special_followup_labels": [],
        "special_parse_targets": [],
    }
    output.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="targets"):
        load_compiled_config(output)


def test_legacy_runtime_loads_permanent_target_identity():
    assert zodiac_scraper.CONFIG["schema_version"] == 1
    assert len(zodiac_scraper.TARGETS) == 236
    assert zodiac_scraper.TARGETS[0].target_id == "PT-0001"
    assert zodiac_scraper.TARGETS[-1].target_id == "PT-0236"
    assert len({target.target_id for target in zodiac_scraper.TARGETS}) == 236


def test_site_config_rejects_direction_override():
    payload = site_payload()
    payload["target"]["position"] = "tail"
    payload["parser"]["position"] = "tail"
    payload["parser"]["section_anchor"] = "目录A开始"
    payload["parser"]["section_end"] = "目录A结束"
    payload["parser"]["section_anchor_position"] = "first"

    with pytest.raises(ConfigValidationError, match="不能覆盖 target.position"):
        SiteConfig.from_dict(payload)
