"""缩略写法（allow_short_pingte_result）回归测试。

页面结构取自 2026-09-18 真实抓取的 PT-0074 蝶化庄生浏览器 DOM 文本：
历史期是 "252期 ...=龙√" 形式，本期行写成 "261期 平鸡肖"（历史各期均为
"NNN期 平特X肖"，本期站点漏了"特"字）。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook, has_confirmed_result_structure
from pingte.parse.header_section import special_header_section_issue_lines
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import validate_documents

TARGET_ID = "PT-9902"
NAME = "蝶化庄生"
KEYWORD = "蝶化庄生平特一肖"
URL = "https://example.test/topic/654270.html"
HISTORY = [
    "252期 33-41-43-13-06-48-T22+02=龙√",
    "253期 05-35-15-28-13-49-T16+02=牛√",
    "254期 26-44-35-06-16-10-T02+02=猪√",
    "255期 36-22-06-47-39-11-T44+02=马√",
    "256期 40-15-09-37-07-03-T01+02=龙√",
    "257期 08-46-47-39-27-45-T07+02=虎√",
    "258期 03-23-21-35-05-19-T46+02=马√",
    "259期 43-33-49-36-19-30-T22+02=蛇√",
    "260期 25-26-44-32-06-48-T20+02=鸡√",
]


def _page(prediction: str = "261期 平鸡肖", header: str = f"261期:★★【{KEYWORD}】★★") -> str:
    return "\n".join(
        ("【单双10码】鸿运当头", "", header, "", f"作者:{NAME}", "", *HISTORY, "", prediction, "", "刷新|登录|免费注册")
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
        rule_version=2,
    )


def _rule(*, allow_short: bool = True) -> dict:
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
    }
    if allow_short:
        rule["allow_short_pingte_result"] = True
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


def test_short_form_is_accepted_when_enabled():
    assert _lines(_page(), "261", _rule()) == ["261期 平鸡肖"]


def test_short_form_is_rejected_by_default():
    assert _lines(_page(), "261", _rule(allow_short=False)) == []


def test_full_form_still_accepted_with_flag():
    assert _lines(_page("261期 平特鸡肖"), "261", _rule()) == ["261期 平特鸡肖"]


def test_other_issue_line_is_not_accepted():
    assert _lines(_page("262期 平鸡肖"), "261", _rule()) == []


def test_three_zodiac_short_form_is_rejected():
    assert _lines(_page("261期 平鸡狗鼠肖"), "261", _rule()) == []


def test_flag_does_not_loosen_shared_structure_by_default():
    assert not has_confirmed_result_structure("261期 平鸡肖", "261")
    assert has_confirmed_result_structure(
        "261期 平鸡肖",
        "261",
        allow_short_pingte=True,
    )


def test_validation_succeeds_with_flag():
    outcome = validate_documents(
        _target(),
        "261",
        _serialized(_page()),
        _registry(_rule()),
    )
    assert outcome.failure is None
    assert outcome.zodiac == "鸡"
    assert outcome.candidate.raw_line == "261期 平鸡肖"


def test_validation_fails_without_flag():
    outcome = validate_documents(
        _target(),
        "261",
        _serialized(_page()),
        _registry(_rule(allow_short=False)),
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
        "rule_version": 2,
        "target": {
            "url": URL,
            "position": "tail",
            "name": NAME,
            "keyword": KEYWORD,
        },
        "parser": parser,
        "auxiliary": {},
    }


def test_schema_accepts_bool_short_pingte():
    site = SiteConfig.from_dict(_site_payload({"allow_short_pingte_result": True}))
    assert site.parser["allow_short_pingte_result"] is True


def test_schema_rejects_non_bool_short_pingte():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(_site_payload({"allow_short_pingte_result": "yes"}))


def test_schema_rejects_short_pingte_outside_header_section():
    payload = _site_payload({"allow_short_pingte_result": True})
    payload["parser"]["mode"] = "anchored_section"
    payload["parser"]["data_structure"] = "confirmed_result_line"
    payload["parser"]["section_boundary"] = "explicit_anchors"
    payload["parser"]["section_anchor"] = KEYWORD
    payload["parser"]["section_end"] = "结束"
    with pytest.raises(ConfigValidationError) as error:
        SiteConfig.from_dict(payload)
    assert "allow_short_pingte_result" in str(error.value)
