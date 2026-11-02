"""named_section 轮次边界（stop_at_cycle_wrap）回归测试。

页面结构取自 2026-11-02 真实抓取的 PT-0189「一视同仁」浏览器 DOM 文本：
正文从 306 期顺次列到 001 期后，继续列出上一轮次 365 期起的旧记录，
其末尾再次出现 306 期（不同生肖），此前会被判为同期候选冲突。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.named_section import named_section_issue_lines
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import validate_documents

TARGET_ID = "PT-9902"
NAME = "一视同仁"
URL = "https://example.test/topic/741263.html"
KEYWORD = "平特二肖"


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
        rule_version=1,
    )


def _rule(*, stop_at_cycle_wrap: bool = True) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 1,
        "url_contains": URL,
        "name": NAME,
        "position": "top",
        "keyword": KEYWORD,
        "mode": "named_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_line",
        "section_boundary": "target_name_section",
        "source_strategy": "browser_main",
        "frame_scope": "main",
        "browser_selector": "body",
    }
    if stop_at_cycle_wrap:
        rule["stop_at_cycle_wrap"] = True
    return rule


def _registry(rule: dict) -> DedicatedParserRegistry:
    return DedicatedParserRegistry(RuleBook([rule], {}), _hooks())


CYCLE_PAGE = "\n".join(
    (
        "平特贴 306期:【平特两肖】买码必看",
        "",
        f"{NAME} 发表于 08月02日 20:14:24",
        "",
        "306期:平特二肖【马龙】开:00准",
        "",
        "305期:平特二肖【牛猴】开:18准",
        "",
        "001期:平特二肖【兔羊】开:03准",
        "",
        "365期:平特二肖【猪龙】开:20准",
        "",
        "306期:平特二肖【猴马】开:10.22准",
        "",
        "上一篇：",
    )
)

IN_CYCLE_DUPLICATE_PAGE = "\n".join(
    (
        f"{NAME} 发表于 08月02日 20:14:24",
        "",
        "306期:平特二肖【马龙】开:00准",
        "",
        "306期:平特二肖【猴马】开:10.22准",
    )
)

PREVIOUS_CYCLE_ONLY_PAGE = "\n".join(
    (
        f"{NAME} 发表于 08月02日 20:14:24",
        "",
        "295期:平特二肖【兔羊】开:03准",
        "",
        "365期:平特二肖【猪龙】开:20准",
        "",
        "306期:平特二肖【猴马】开:10.22准",
    )
)


def _lines(text: str, issue: str, rule: dict) -> list[str]:
    return named_section_issue_lines(
        text,
        _target(),
        issue,
        RuleBook([rule], {}),
        _hooks(),
    )


def test_wrap_drops_previous_cycle_duplicate():
    assert _lines(CYCLE_PAGE, "306", _rule()) == [
        "306期:平特二肖【马龙】开:00准"
    ]


def test_adjacent_issue_also_uses_current_cycle():
    assert _lines(CYCLE_PAGE, "305", _rule()) == [
        "305期:平特二肖【牛猴】开:18准"
    ]


def test_wrapped_record_alone_does_not_satisfy_target():
    assert _lines(PREVIOUS_CYCLE_ONLY_PAGE, "306", _rule()) == []


def test_flag_off_keeps_both_occurrences():
    assert _lines(CYCLE_PAGE, "306", _rule(stop_at_cycle_wrap=False)) == [
        "306期:平特二肖【马龙】开:00准",
        "306期:平特二肖【猴马】开:10.22准",
    ]


def test_same_cycle_duplicate_is_still_reported():
    assert _lines(
        IN_CYCLE_DUPLICATE_PAGE, "306", _rule()
    ) == [
        "306期:平特二肖【马龙】开:00准",
        "306期:平特二肖【猴马】开:10.22准",
    ]


def _serialized(text: str) -> str:
    return serialize_source_documents(
        [make_source_document("browser-main", URL, True, text)]
    )


def test_validation_conflict_without_flag():
    outcome = validate_documents(
        _target(),
        "306",
        _serialized(CYCLE_PAGE),
        _registry(_rule(stop_at_cycle_wrap=False)),
    )
    assert outcome.failure is not None
    assert outcome.failure.code.value == "ambiguous_candidates"


def test_validation_accepts_current_cycle_with_flag():
    outcome = validate_documents(
        _target(),
        "306",
        _serialized(CYCLE_PAGE),
        _registry(_rule()),
    )
    assert outcome.failure is None
    assert outcome.zodiac == "马龙"


def _site_payload(parser_extra: dict) -> dict:
    parser = {
        "url_contains": URL,
        "name": NAME,
        "position": "top",
        "keyword": KEYWORD,
        "mode": "named_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_line",
        "section_boundary": "target_name_section",
        "source_strategy": "browser_main",
        "frame_scope": "main",
        "browser_selector": "body",
        **parser_extra,
    }
    return {
        "schema_version": 1,
        "target_id": TARGET_ID,
        "rule_version": 1,
        "target": {
            "url": URL,
            "position": "top",
            "name": NAME,
            "keyword": KEYWORD,
        },
        "parser": parser,
        "auxiliary": {},
    }


def test_schema_accepts_cycle_wrap_for_named_section():
    site = SiteConfig.from_dict(_site_payload({"stop_at_cycle_wrap": True}))
    assert site.parser["stop_at_cycle_wrap"] is True


def test_schema_rejects_non_bool_cycle_wrap():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(_site_payload({"stop_at_cycle_wrap": "yes"}))
