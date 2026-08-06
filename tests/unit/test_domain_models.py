from dataclasses import FrozenInstanceError

import pytest

from tests.compat import zodiac_scraper
from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.models import (
    Candidate,
    FetchRequest,
    ParseRequest,
    SourceDocument,
    Target,
    TargetProfile,
    ValidatedResult,
)
from pingte.domain.zodiac import ZODIACS, ZODIAC_NUMBERS


def test_legacy_target_and_source_document_use_domain_models():
    assert Target is TargetProfile
    assert zodiac_scraper.Target is TargetProfile
    assert zodiac_scraper.SourceDocument is SourceDocument


def test_target_profile_preserves_legacy_constructor_and_is_immutable():
    target = Target("https://example.test", "top", "目录A", "平特一肖")

    assert target.target_id == ""
    assert target.rule_version == 1
    with pytest.raises(FrozenInstanceError):
        target.name = "changed"


def test_domain_requests_and_results_keep_structured_provenance():
    target = TargetProfile(
        "https://example.test",
        "tail",
        "目录A",
        "成语平特",
        target_id="PT-0001",
        rule_version=3,
    )
    document = SourceDocument(
        "browser-main",
        target.url,
        True,
        "211期成语平特【鸡飞狗跳】开00准",
        sha256="abc123",
        fetched_at="2026-07-30T23:00:00+08:00",
    )
    fetch_request = FetchRequest(target, "211", 20)
    parse_request = ParseRequest(target, "211", (document,))
    candidate = Candidate(
        target_id=target.target_id,
        issue="211",
        zodiac="鸡狗",
        raw_line=document.text,
        source=document.source,
        source_url=document.source_url,
        section_start="目录A【成语平特】",
        section_end="栏目结束",
    )
    result = ValidatedResult(target, "211", candidate, document)

    assert fetch_request.target is target
    assert parse_request.documents == (document,)
    assert result.candidate.zodiac == "鸡狗"
    assert result.document.sha256 == "abc123"


def test_failure_detail_renders_all_required_context():
    failure = FailureDetail(
        code=FailureCode.ISSUE_MISSING,
        message="目标区块没有指定期数",
        target_id="PT-0001",
        name="目录A",
        url="https://example.test",
        position="tail",
        keyword="成语平特",
        issue="211",
        visible_issues=("212", "210", "209"),
    )

    assert failure.render() == (
        "目标区块没有指定期数，目录：目录A，网址：https://example.test，"
        "位置：tail，关键字：成语平特，指定期数：211，"
        "当前可见期数：212期、210期、209期"
    )


def test_domain_zodiac_constants_match_existing_behavior():
    assert ZODIACS == "鼠牛虎兔龙蛇马羊猴鸡狗猪"
    assert ZODIAC_NUMBERS["马"] == frozenset({1, 13, 25, 37, 49})
    assert ZODIAC_NUMBERS["鼠"] == frozenset({7, 19, 31, 43})
