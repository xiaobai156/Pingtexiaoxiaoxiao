"""无生肖字成语（phrase_zodiac_map）回归测试。

页面结构取自 2026-09-29 真实抓取的 PT-0245 澳门赌神浏览器 DOM 文本：
该站每期只写一句成语，生肖字通常就在成语里（马踏飞燕=马、过街老鼠=鼠），
但 259 期与 272 期用的「洋洋得意」没有任何生肖字，且本期未开奖时
`开:00` 也无法用号码反推，导致本报社无法取值（259 期当时即失败）。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.header_section import special_header_section_issue_lines
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import validate_documents

TARGET_ID = "PT-0245"
NAME = "澳门赌神"
KEYWORD = "四字平特"
URL = "https://552554.com.xn--61b2aeb.xn--h2brj9c:1888/sp/04.html"
CURRENT_LINE = "272 期:【四字平特】【洋洋得意】开:00准"
PAGE = "\n".join(
    (
        "返回主页",
        f"{NAME}【{KEYWORD}】资料已公开,敬请期待",
        "温馨提示:为了提高网速，部分过往记录已删除",
        "257 期:【四字平特】【狗急跳墙】开:45准",
        "258 期:【四字平特】【虎虎生威】开:05准",
        "259 期:【四字平特】【洋洋得意】开:36准",
        "260 期:【四字平特】【母猪上树】开:20准",
        "261 期:【四字平特】【金鸡独立】开:46准",
        "262 期:【四字平特】【马踏飞燕】开:00错",
        "263 期:【四字平特】【引蛇出洞】开:02准",
        "265 期:【四字平特】【过街老鼠】开:00错",
        "266 期:【四字平特】【牛气冲天】开:42准",
        "269 期:【四字平特】【金鸡独立】开:22准",
        "270 期:【四字平特】【母猪上树】开:20准",
        "271 期:【四字平特】【马踏飞燕】开:25准",
        CURRENT_LINE,
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
        position="tail",
        name=NAME,
        keyword=KEYWORD,
        target_id=TARGET_ID,
        rule_version=1,
    )


def _rule(phrase_map: dict | None = None) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 1,
        "url_contains": URL,
        "name": NAME,
        "position": "tail",
        "keyword": KEYWORD,
        "mode": "header_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_line",
        "section_boundary": "target_header_section",
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
    return special_header_section_issue_lines(
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
    assert _lines(PAGE, "272", _rule({"洋洋得意": "羊"})) == [CURRENT_LINE]


def test_current_issue_is_still_missing_without_the_map():
    assert _lines(PAGE, "272", _rule()) == []


def test_literal_zodiac_still_wins_over_the_map():
    rule = _rule({"马踏飞燕": "羊"})
    assert extract_target_zodiac("271 期:【四字平特】【马踏飞燕】开:25准", _target(), rule) == "马"
    assert _lines(PAGE, "271", rule) == ["271 期:【四字平特】【马踏飞燕】开:25准"]


def test_map_does_not_apply_to_other_issues():
    assert _lines(PAGE, "271", _rule({"洋洋得意": "羊"})) == [
        "271 期:【四字平特】【马踏飞燕】开:25准"
    ]


def test_ambiguous_map_fails_instead_of_guessing():
    rule = _rule({"洋洋得意": "羊", "得意": "猪"})
    assert extract_target_zodiac(CURRENT_LINE, _target(), rule) is None
    assert _lines(PAGE, "272", rule) == []


def test_unmatched_map_leaves_the_line_unresolved():
    rule = _rule({"十全十美": "兔"})
    assert extract_target_zodiac(CURRENT_LINE, _target(), rule) is None


def test_validation_end_to_end_resolves_272():
    outcome = validate_documents(
        _target(),
        "272",
        _serialized(PAGE),
        _registry(_rule({"洋洋得意": "羊"})),
    )
    assert outcome.failure is None
    assert outcome.zodiac == "羊"
    assert outcome.candidate.raw_line == CURRENT_LINE


def test_validation_fails_without_the_map():
    outcome = validate_documents(
        _target(),
        "272",
        _serialized(PAGE),
        _registry(_rule()),
    )
    assert outcome.failure is not None


def _site_payload(parser_extra: dict) -> dict:
    parser = {
        "url_contains": URL,
        "name": NAME,
        "position": "tail",
        "keyword": KEYWORD,
        "mode": "header_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_line",
        "section_boundary": "target_header_section",
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
            "position": "tail",
            "name": NAME,
            "keyword": KEYWORD,
        },
        "parser": parser,
        "auxiliary": {},
    }


def test_schema_accepts_phrase_zodiac_map():
    site = SiteConfig.from_dict(
        _site_payload({"phrase_zodiac_map": {"洋洋得意": "羊"}})
    )
    assert site.parser["phrase_zodiac_map"] == {"洋洋得意": "羊"}


def test_schema_rejects_non_zodiac_value():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(_site_payload({"phrase_zodiac_map": {"洋洋得意": "洋"}}))


def test_schema_rejects_empty_map():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(_site_payload({"phrase_zodiac_map": {}}))


def test_schema_rejects_map_outside_header_section():
    payload = _site_payload({"phrase_zodiac_map": {"洋洋得意": "羊"}})
    payload["parser"]["mode"] = "anchored_section"
    payload["parser"]["section_anchor"] = KEYWORD
    payload["parser"]["section_end"] = "结束"
    payload["parser"]["section_boundary"] = "explicit_anchors"
    with pytest.raises(ConfigValidationError) as error:
        SiteConfig.from_dict(payload)
    assert "phrase_zodiac_map" in str(error.value)
