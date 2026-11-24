"""「326期平特 狗尾」类模板噪声后缀（allow_pingte_tail_suffix）回归测试。

页面结构取自 2026-11-22 真实抓取的 PT-0159「气冲牛斗」与 PT-0179「大公无私」
浏览器 DOM 文本：这两站平时把本期答案写成「325期平特 鸡肖」，当天站点模板
多写了一个「尾」字（「326期平特 狗尾」）。默认解析器不认这种写法，会把
指定期判成「不在方向窗口内」而失败；只有真实页面证明存在该变体的站点才
可以打开 allow_pingte_tail_suffix。
"""
from __future__ import annotations

import pytest

from pingte.config.schema import ConfigValidationError, SiteConfig
from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import (
    ParserHooks,
    RuleBook,
    has_confirmed_result_structure,
)
from pingte.parse.named_section import named_section_issue_lines
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import validate_documents

TARGET_ID = "PT-9903"
NAME = "气冲牛斗"
URL = "https://example.test/topic/741286.html"
KEYWORD = "平特一肖"
CURRENT_LINE = "326期平特 狗尾"

PAGE = "\n".join(
    (
        "平特贴 326期:【平特一肖】买码必看",
        "",
        f"{NAME} 发表于 08月02日 20:04:44",
        "",
        "324期19-04-14-12-21-34T43 +03=鸡√",
        "",
        "325期41-37-10-01-27-17T03 +04=狗√",
        "",
        CURRENT_LINE,
        "",
        "上一篇：",
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
        rule_version=2,
    )


def _rule(*, allow_tail: bool = True) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 2,
        "url_contains": URL,
        "name": NAME,
        "position": "tail",
        "keyword": KEYWORD,
        "mode": "named_section",
        "issue_format": "arabic_issue_exact",
        "data_structure": "confirmed_result_line",
        "section_boundary": "target_name_section",
        "source_strategy": "browser_main",
        "frame_scope": "main",
        "browser_selector": "body",
    }
    if allow_tail:
        rule["allow_pingte_tail_suffix"] = True
    return rule


def _registry(rule: dict) -> DedicatedParserRegistry:
    return DedicatedParserRegistry(RuleBook([rule], {}), _hooks())


def _lines(text: str, issue: str, rule: dict) -> list[str]:
    return named_section_issue_lines(
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


def test_tail_suffix_line_is_recognised_only_with_the_flag():
    assert has_confirmed_result_structure(
        CURRENT_LINE, "326", allow_pingte_tail_suffix=True
    )
    assert not has_confirmed_result_structure(CURRENT_LINE, "326")


def test_flag_resolves_the_current_issue():
    assert _lines(PAGE, "326", _rule()) == [CURRENT_LINE]


def test_without_the_flag_the_issue_stays_unresolved():
    assert _lines(PAGE, "326", _rule(allow_tail=False)) == []


def test_plain_zodiac_suffix_still_works_without_the_flag():
    page = PAGE.replace(CURRENT_LINE, "326期平特 狗肖")
    assert _lines(page, "326", _rule(allow_tail=False)) == ["326期平特 狗肖"]


def test_tail_flag_does_not_accept_other_spellings():
    # 「平特尾」是开奖号栏目，不能被当成生肖答案。
    assert not has_confirmed_result_structure(
        "326期平特1尾", "326", allow_pingte_tail_suffix=True
    )
    assert not has_confirmed_result_structure(
        "326期平特 狗马羊猴鸡尾", "326", allow_pingte_tail_suffix=True
    )


def test_validation_end_to_end_resolves_current_issue():
    outcome = validate_documents(
        _target(),
        "326",
        _serialized(PAGE),
        _registry(_rule()),
    )
    assert outcome.failure is None
    assert outcome.zodiac == "狗"
    assert outcome.candidate.raw_line == CURRENT_LINE


def _site_payload(parser_extra: dict) -> dict:
    parser = {
        "url_contains": URL,
        "name": NAME,
        "position": "tail",
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


def test_schema_accepts_the_flag():
    site = SiteConfig.from_dict(
        _site_payload({"allow_pingte_tail_suffix": True})
    )
    assert site.parser["allow_pingte_tail_suffix"] is True


def test_schema_rejects_non_bool():
    with pytest.raises(ConfigValidationError):
        SiteConfig.from_dict(
            _site_payload({"allow_pingte_tail_suffix": "yes"})
        )


def test_schema_rejects_the_flag_outside_named_section():
    payload = _site_payload({"allow_pingte_tail_suffix": True})
    payload["parser"]["mode"] = "anchored_section"
    payload["parser"]["section_anchor"] = KEYWORD
    payload["parser"]["section_end"] = "结束"
    payload["parser"]["section_boundary"] = "explicit_anchors"
    with pytest.raises(ConfigValidationError) as error:
        SiteConfig.from_dict(payload)
    assert "allow_pingte_tail_suffix" in str(error.value)
