"""row_section 谐音成语（phrase_zodiac_map）回归测试。

页面结构取自 2026-11-22 真实抓取的 PT-0256「澳门资料库」浏览器 DOM 文本：
该栏目每期一行 `{期}期 成语爆平特 【成语】 开 ￥00 准`，成语字面一般带生肖
（虎虎生威=虎、马到成功=马），但 326 期用的「洋洋得意」不含任何生肖字，
未开奖时 `开 ￥00` 也反推不出，只能由站点配置显式登记的映射解析。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.registry import DedicatedParserRegistry
from pingte.parse.row_section import row_section_issue_lines
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import validate_documents

TARGET_ID = "PT-9904"
NAME = "澳门资料库"
URL = "https://example.test:1888/"
ANCHOR = "澳门资料库 『成语平特』"
END = "澳门资料库 『输尽光』"
KEYWORD = "成语爆平特"
CURRENT_ROW = "326期 成语爆平特 【洋洋得意】 开 ￥00 准"
PREVIOUS_ROW = "325期 成语爆平特 【马到成功】 开 马37 准"

PAGE = "\n".join(
    (
        ANCHOR,
        "326期",
        "成语爆平特 【洋洋得意】",
        "开 ￥00 准",
        "325期",
        "成语爆平特 【马到成功】",
        "开 马37 准",
        "投注澳门六合彩就上9B彩票,请点击下注",
        END,
    )
)


def _hooks() -> ParserHooks:
    return ParserHooks(
        extract_zodiac=strict_extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=zodiac_chars,
        dedupe_zodiac=dedupe_zodiac,
    )


def _target() -> TargetProfile:
    return TargetProfile(
        url=URL,
        position="top",
        name=NAME,
        keyword=KEYWORD,
        target_id=TARGET_ID,
        rule_version=3,
    )


def _rule(phrase_map: dict | None = None) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 3,
        "url_contains": URL,
        "name": NAME,
        "position": "top",
        "keyword": KEYWORD,
        "mode": "row_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_row",
        "section_boundary": "explicit_anchors",
        "section_anchor": ANCHOR,
        "section_end": END,
        "section_anchor_exact": True,
        "section_end_exact": True,
        "line_keyword": KEYWORD,
        "row_zodiac_source": "phrase_or_open",
        "source_strategy": "browser_main",
        "frame_scope": "main",
        "browser_selector": "body",
    }
    if phrase_map is not None:
        rule["phrase_zodiac_map"] = phrase_map
    return rule


def _registry(rule: dict) -> DedicatedParserRegistry:
    return DedicatedParserRegistry(RuleBook([rule], {}), _hooks())


def _lines(text: str, issue: str, rule: dict) -> list[str]:
    return row_section_issue_lines(
        text,
        _target(),
        issue,
        RuleBook([rule], {}),
        _hooks(),
    )


def _serialized(text: str) -> str:
    return serialize_source_documents(
        [make_source_document("browser-main", URL, True, text)]
    )


def test_homophone_idiom_is_resolved_by_the_configured_map():
    lines = _lines(PAGE, "326", _rule({"洋洋得意": "羊"}))
    assert len(lines) == 1
    assert "洋洋得意" in lines[0]


def test_current_issue_is_missing_without_the_map():
    assert _lines(PAGE, "326", _rule()) == []


def test_literal_zodiac_still_wins_over_the_map():
    rule = _rule({"马到成功": "羊"})
    lines = _lines(PAGE, "325", rule)
    assert len(lines) == 1
    assert extract_target_zodiac(lines[0], _target(), rule) == "马"


def test_ambiguous_map_fails_instead_of_guessing():
    assert _lines(PAGE, "326", _rule({"洋洋得意": "羊", "得意": "猪"})) == []


def test_validation_end_to_end_resolves_current_issue():
    outcome = validate_documents(
        _target(),
        "326",
        _serialized(PAGE),
        _registry(_rule({"洋洋得意": "羊"})),
    )
    assert outcome.failure is None
    assert outcome.zodiac == "羊"


def _site_payload(parser_extra: dict) -> dict:
    parser = {
        "url_contains": URL,
        "name": NAME,
        "position": "top",
        "keyword": KEYWORD,
        "mode": "row_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_row",
        "section_boundary": "explicit_anchors",
        "section_anchor": ANCHOR,
        "section_end": END,
        "section_anchor_exact": True,
        "section_end_exact": True,
        "line_keyword": KEYWORD,
        "row_zodiac_source": "phrase_or_open",
        "source_strategy": "browser_main",
        "frame_scope": "main",
        "browser_selector": "body",
        **parser_extra,
    }
    return {
        "schema_version": 1,
        "target_id": TARGET_ID,
        "rule_version": 3,
        "target": {
            "url": URL,
            "position": "top",
            "name": NAME,
            "keyword": KEYWORD,
        },
        "parser": parser,
        "auxiliary": {},
    }


def test_schema_accepts_the_map_for_row_section():
    site = SiteConfig.from_dict(
        _site_payload({"phrase_zodiac_map": {"洋洋得意": "羊"}})
    )
    assert site.parser["phrase_zodiac_map"] == {"洋洋得意": "羊"}


def test_schema_still_rejects_the_map_for_other_modes():
    payload = _site_payload({"phrase_zodiac_map": {"洋洋得意": "羊"}})
    payload["parser"]["mode"] = "named_section"
    for key in ("section_anchor", "section_end", "line_keyword", "row_zodiac_source"):
        payload["parser"].pop(key, None)
    with pytest.raises(ConfigValidationError) as error:
        SiteConfig.from_dict(payload)
    assert "phrase_zodiac_map" in str(error.value)
