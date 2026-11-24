"""header_context_required 回归测试。

页面结构取自 2026-11-20 真实抓取的 PT-0030 凉风有信浏览器 DOM 文本：站点用
`{期}期:{署名}「平特一肖」独家提供` 同一套模板生成多个栏目表头，广告列表里
出现一模一样的 section_name 行，导致 tail 方向取到广告块、候选为 0。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.header_section import special_header_section_issue_lines
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)

TARGET_ID = "PT-9903"
NAME = "凉风有信"
KEYWORD = "平特一肖"
URL = "https://example.test/topic/702058.html"
SECTION_NAME = "「平特一肖」独家提供"
DATA_LINE = "324期：一肖平特（狗狗狗）开00赢"

AD_LIST = [
    "324期:水色山光【稳杀四肖】独家提供",
    "",
    "324期:坐看云起「平特一肖」独家提供",
    "",
    "324期:闲云野鹤（前后中特）独家高手",
    "",
    "324期：打枪客网【三肖三肖】已公开",
]


def _page(header_author: str = "鹬蚌相危", with_ad: bool = True) -> str:
    body = [
        "【单双10码】鸿运当头",
        "",
        f"324期:{header_author}{SECTION_NAME}",
        "",
        "作者:鹬蚌相危",
        "",
        DATA_LINE,
        "",
        "★★ 博彩必备★★",
        "",
        "澳门公式",
        "",
    ]
    if with_ad:
        body.extend(AD_LIST)
    return "\n".join(body)


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
        rule_version=2,
    )


def _rule(*, context: str | None = None) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 2,
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
        "section_name": SECTION_NAME,
    }
    if context is not None:
        rule["header_context_required"] = context
    return rule


def _lines(text: str, rule: dict, issue: str = "324") -> list[str]:
    return special_header_section_issue_lines(
        text,
        _target(),
        issue,
        RuleBook([rule], {}),
        _hooks(),
    )


def test_single_header_parses_without_context_key():
    assert _lines(_page(header_author=NAME, with_ad=False), _rule()) == [DATA_LINE]


def test_duplicate_section_name_in_ad_list_breaks_tail_selection():
    """回归用例：广告列表里同名表头把 tail 方向带偏，候选为 0。"""
    assert _lines(_page(), _rule()) == []


def test_context_required_ignores_ad_list_header():
    assert _lines(_page(), _rule(context="一肖平特")) == [DATA_LINE]


def test_context_required_keeps_normal_variant_working():
    assert _lines(_page(header_author=NAME, with_ad=False), _rule(context="一肖平特")) == [
        DATA_LINE
    ]


def test_context_required_rejects_when_context_missing():
    page = "\n".join(
        [
            f"324期:{NAME}{SECTION_NAME}",
            "",
            "作者:鹬蚌相危",
            "",
            "324期：本期未发布",
            "",
            "★★ 博彩必备★★",
        ]
    )
    assert _lines(page, _rule(context="一肖平特")) == []


def _payload(parser_extra: dict) -> dict:
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
        "section_name": SECTION_NAME,
        **parser_extra,
    }
    return {
        "schema_version": 1,
        "target_id": TARGET_ID,
        "rule_version": 2,
        "target": {"url": URL, "position": "tail", "name": NAME, "keyword": KEYWORD},
        "parser": parser,
        "auxiliary": {},
    }


def test_schema_accepts_header_context_required_on_header_section():
    SiteConfig.from_dict(_payload({"header_context_required": "一肖平特"}))


def test_schema_rejects_empty_header_context_required():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(_payload({"header_context_required": "  "}))


def test_schema_rejects_header_context_required_on_other_modes():
    payload = _payload({"header_context_required": "一肖平特"})
    payload["parser"]["mode"] = "named_section"
    payload["parser"]["data_structure"] = "confirmed_result_line"
    payload["parser"]["section_boundary"] = "target_name_section"
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(payload)
