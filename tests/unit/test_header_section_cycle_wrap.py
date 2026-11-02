"""轮次边界（stop_at_cycle_wrap）回归测试。

页面结构取自 2026-09-17 真实抓取的 PT-0031 / PT-0165 浏览器 DOM 文本：
同一栏目在结束当前轮次 001 期后，继续列出上一轮次 365 期起的旧记录，
导致同一个期号（如 260 期）在文档中出现两次。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.header_section import (
    cycle_wrap_detected,
    period_numbers,
    special_header_section_issue_lines,
)
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import validate_documents

TARGET_ID = "PT-9901"
NAME = "素面朝天"
URL = "https://example.test/topic/702056.html"
KEYWORD = "成语平特"


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
        rule_version=2,
    )


def _rule(*, stop_at_cycle_wrap: bool = True) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 2,
        "url_contains": URL,
        "name": NAME,
        "position": "top",
        "keyword": KEYWORD,
        "mode": "header_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_line",
        "section_boundary": "target_header_section",
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
        "260期:大汉美男「成语平特」独家提供",
        "",
        f"作者:{NAME}",
        "",
        "260期成语平特《鸡飞狗跳》开：000准",
        "",
        "259期成语平特《猴年马月》开：49准",
        "",
        "001期成语平特《鸡飞狗跳》开：33.08准",
        "",
        "365期成语平特《猪狗不如》开：20准",
        "",
        "260期成语平特《猪狗不如》开：44准",
        "",
        "259期成语平特《蛇鼠一窝》开：47错",
    )
)

IN_CYCLE_DUPLICATE_PAGE = "\n".join(
    (
        "260期:大汉美男「成语平特」独家提供",
        "",
        f"作者:{NAME}",
        "",
        "260期成语平特《鸡飞狗跳》开：000准",
        "",
        "260期成语平特《猪狗不如》开：44准",
    )
)

PREVIOUS_CYCLE_ONLY_PAGE = "\n".join(
    (
        "260期:大汉美男「成语平特」独家提供",
        "",
        f"作者:{NAME}",
        "",
        "250期成语平特《蛇鼠一窝》开：04错",
        "",
        "365期成语平特《猪狗不如》开：20准",
        "",
        "260期成语平特《猪狗不如》开：44准",
    )
)


def _lines(text: str, issue: str, rule: dict) -> list[str]:
    return special_header_section_issue_lines(
        text,
        _target(),
        issue,
        RuleBook([rule], {}),
        _hooks(),
    )


def test_wrap_boundary_detection():
    assert period_numbers("365期成语平特《猪狗不如》开：20准") == [365]
    assert period_numbers("260期18码:17.29.41.09") == [260]
    assert period_numbers("作者:素面朝天 发表于 08月02日") == []
    assert cycle_wrap_detected([365], 1)
    assert not cycle_wrap_detected([359], 365)
    assert not cycle_wrap_detected([], 1)
    assert not cycle_wrap_detected([260], None)


def test_wrap_drops_previous_cycle_duplicate():
    rule = _rule()
    assert _lines(CYCLE_PAGE, "260", rule) == ["260期成语平特《鸡飞狗跳》开：000准"]


def test_adjacent_issue_also_uses_current_cycle():
    rule = _rule()
    assert _lines(CYCLE_PAGE, "259", rule) == ["259期成语平特《猴年马月》开：49准"]


def test_wrapped_record_alone_does_not_satisfy_target():
    rule = _rule()
    assert _lines(PREVIOUS_CYCLE_ONLY_PAGE, "260", rule) == []


def test_issue_outside_page_returns_nothing():
    rule = _rule()
    assert _lines(CYCLE_PAGE, "300", rule) == []


def test_flag_off_keeps_both_occurrences():
    rule = _rule(stop_at_cycle_wrap=False)
    assert _lines(CYCLE_PAGE, "260", rule) == [
        "260期成语平特《鸡飞狗跳》开：000准",
        "260期成语平特《猪狗不如》开：44准",
    ]


def test_same_cycle_duplicate_is_still_reported():
    rule = _rule()
    assert _lines(IN_CYCLE_DUPLICATE_PAGE, "260", rule) == [
        "260期成语平特《鸡飞狗跳》开：000准",
        "260期成语平特《猪狗不如》开：44准",
    ]


def _serialized(text: str) -> str:
    return serialize_source_documents(
        [make_source_document("browser-main", URL, True, text)]
    )


def test_validation_conflict_without_flag():
    """关掉 stop_at_cycle_wrap 时，旧轮同号会进入候选并报同期冲突。

    2026-10-26 起 001→365 / 365→001 被识别为跨年回绕（不算方向反转），
    因此 `_candidate_context` 不再按方向截断掉旧轮数据；此时必须依赖
    stop_at_cycle_wrap 或冲突判定来拦截，本用例验证冲突判定仍然生效。
    """
    outcome = validate_documents(
        _target(),
        "260",
        _serialized(CYCLE_PAGE),
        _registry(_rule(stop_at_cycle_wrap=False)),
    )
    assert outcome.failure is not None
    assert outcome.failure.code.value == "ambiguous_candidates"


def test_validation_accepts_current_cycle_with_flag():
    outcome = validate_documents(
        _target(),
        "260",
        _serialized(CYCLE_PAGE),
        _registry(_rule()),
    )
    assert outcome.failure is None
    assert outcome.zodiac == "鸡狗"


def test_validation_still_fails_on_same_cycle_duplicate():
    outcome = validate_documents(
        _target(),
        "260",
        _serialized(IN_CYCLE_DUPLICATE_PAGE),
        _registry(_rule()),
    )
    assert outcome.failure is not None
    assert outcome.failure.code.value == "ambiguous_candidates"


def _site_payload(parser_extra: dict) -> dict:
    parser = {
        "url_contains": URL,
        "name": NAME,
        "position": "top",
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
        "rule_version": 2,
        "target": {
            "url": URL,
            "position": "top",
            "name": NAME,
            "keyword": KEYWORD,
        },
        "parser": parser,
        "auxiliary": {},
    }


def test_schema_accepts_bool_cycle_wrap():
    site = SiteConfig.from_dict(_site_payload({"stop_at_cycle_wrap": True}))
    assert site.parser["stop_at_cycle_wrap"] is True


def test_schema_rejects_non_bool_cycle_wrap():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(_site_payload({"stop_at_cycle_wrap": "yes"}))


def test_schema_rejects_cycle_wrap_outside_header_section():
    payload = _site_payload({"stop_at_cycle_wrap": True})
    payload["parser"]["mode"] = "anchored_section"
    payload["parser"]["data_structure"] = "confirmed_result_line"
    payload["parser"]["section_boundary"] = "explicit_anchors"
    payload["parser"]["section_anchor"] = KEYWORD
    payload["parser"]["section_end"] = "结束"
    with pytest.raises(ConfigValidationError) as error:
        SiteConfig.from_dict(payload)
    assert "stop_at_cycle_wrap" in str(error.value)
