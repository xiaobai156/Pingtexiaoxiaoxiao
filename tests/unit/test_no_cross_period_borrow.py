"""跨期借值回归测试（2026-10-25 审查修复）。

覆盖四条真实借值路径：
  1. 行内期号只做「包含」判断 —— ``297期 … 下期298期预告`` 被当成 298 期；
  2. 一行混两个期号 —— ``298期 … 297期 平特一肖：鼠`` 里的鼠属于 297 期；
  3. 区块内混入邻期值行 —— 298 期区块里放一行 297 期的数据；
  4. 候选期号反向（进入上一轮/另一栏目）—— tail 窗口借到旧轮同号；
以及行内「上期/回顾」字样不得取值。
"""
from __future__ import annotations

from pingte.domain.models import TargetProfile
from pingte.fetch.documents import make_source_document, serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook, value_line_belongs_to_issue
from pingte.parse.header_section import special_header_section_issue_lines
from pingte.parse.named_section import special_followup_issue_lines
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)
from pingte.validation.result import _direction_window, _monotonic_segments, validate_documents

TARGET_ID = "PT-9902"
NAME = "跨期测试站"
URL = "https://example.test/topic/900001.html"
KEYWORD = "成语平特"


def _hooks() -> ParserHooks:
    return ParserHooks(
        extract_zodiac=strict_extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=zodiac_chars,
        dedupe_zodiac=dedupe_zodiac,
    )


def _target(position: str = "top") -> TargetProfile:
    return TargetProfile(
        url=URL,
        position=position,
        name=NAME,
        keyword=KEYWORD,
        target_id=TARGET_ID,
        rule_version=1,
    )


def _rule(**extra) -> dict:
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 1,
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
    rule.update(extra)
    return rule


def _registry(rule: dict) -> DedicatedParserRegistry:
    return DedicatedParserRegistry(RuleBook([rule], {}), _hooks())


def _serialized(text: str) -> str:
    return serialize_source_documents(
        [make_source_document("browser-main", URL, True, text)]
    )


# ---------------------------------------------------------------- 单元级判据

def test_line_owner_rejects_next_issue_preview():
    """297 期行里的「下期298期预告」不能算 298 期。"""
    line = "297期 成语平特 蛇 开 蛇 准 下期298期预告"
    assert value_line_belongs_to_issue(line, "297") is True
    assert value_line_belongs_to_issue(line, "298") is False


def test_line_owner_rejects_two_issue_mix():
    """一行里混两个期号时，另一个期号的值不能借给指定期。"""
    line = "AAAAA级大公开298期 297期 平特一肖 ：鼠鼠鼠"
    assert value_line_belongs_to_issue(line, "298") is False
    assert value_line_belongs_to_issue(line, "297") is True


def test_line_owner_accepts_range_covering_issue():
    line = "289-291期：致富平特 【羊】（289期✔）"
    assert value_line_belongs_to_issue(line, "290") is True
    assert value_line_belongs_to_issue(line, "295") is False


def test_line_without_issue_is_allowed():
    """专属解析器已绑定期号、行内无期号时放行。"""
    assert value_line_belongs_to_issue("平特一肖【鼠鼠鼠】开00准", "298") is True


# ---------------------------------------------------------------- 路径 1/2

def test_header_section_rejects_neighbour_issue_value_line():
    """区块里出现 297 期的值行，请求 298 期不得取到它。"""
    text = "\n".join(
        (
            "298期:【成语平特】跨期测试站",
            "",
            f"作者:{NAME}",
            "",
            "297期：成语平特《鸡飞狗跳》开：44准",
        )
    )
    rule = _rule()
    lines = special_header_section_issue_lines(
        text, _target(), "298", RuleBook([rule], {}), _hooks()
    )
    assert lines == []


def test_header_section_rejects_issue_with_trailing_preview():
    """298 期请求不能吃 297 期行里「下期298期」的预告。"""
    text = "\n".join(
        (
            "298期:【成语平特】跨期测试站",
            "",
            f"作者:{NAME}",
            "",
            "297期：成语平特《鸡飞狗跳》开：44准 下期298期预告",
        )
    )
    rule = _rule()
    lines = special_header_section_issue_lines(
        text, _target(), "298", RuleBook([rule], {}), _hooks()
    )
    assert lines == []


# ---------------------------------------------------------------- 路径 3

def test_followup_label_rejects_neighbour_issue_line():
    """followup_label 区块里的 297 期数据行不得当 298 期。"""
    text = "\n".join(
        (
            "AAAAA级大公开298期",
            "297期 平特一肖 马 开 马 准",
            "AI智能网:",
        )
    )
    rule = {
        "target_id": TARGET_ID,
        "rule_version": 1,
        "url_contains": URL,
        "name": NAME,
        "position": "top",
        "keyword": "平特一肖",
        "mode": "followup_label",
        "followup_label": "平特一肖",
        "issue_format": "arabic_issue_exact",
        "data_structure": "label_followup_result",
        "section_boundary": "issue_followup_block",
        "section_anchor": "AAAAA级大公开{issue}期",
        "section_end": "AI智能网:",
        "source_strategy": "browser_main",
        "frame_scope": "main",
        "browser_selector": "body",
    }
    target = TargetProfile(
        url=URL, position="top", name=NAME, keyword="平特一肖", target_id=TARGET_ID
    )
    lines = special_followup_issue_lines(
        text, target, "298", RuleBook([rule], {}), _hooks()
    )
    assert lines == []


# ---------------------------------------------------------------- 路径 4

def test_direction_window_does_not_cross_cycle():
    """期号反向切段后，tail 窗口不得把旧轮同号算进来。"""
    # 本轮递减到 295 后，跳到旧轮的 298 —— 这是反向，必须切段。
    ordered = [(1, "297"), (2, "296"), (3, "295"), (4, "298")]
    segments = _monotonic_segments(ordered)
    assert [item[1] for item in segments[0]] == ["297", "296", "295"]
    assert [item[1] for item in segments[1]] == ["298"]

    candidates_by_issue = {
        "297": [],
        "296": [],
        "295": [],
        "298": [],
    }
    # 请求 298：窗口只在含 298 的那一段里算，不会把本轮 295/296 拉进来。
    window_298 = _direction_window(candidates_by_issue, _target("tail"), issue="298")
    assert window_298 == ("298",)
    # 请求 296：窗口只在含 296 的那一段（297/296/295）里算，不会把旧轮 298 拉进来。
    window_296 = _direction_window(candidates_by_issue, _target("tail"), issue="296")
    assert window_296 == ("297", "296", "295")


def test_cycle_wrap_one_to_365_is_not_reversal():
    """1 期之后接 365 期属跨年回绕，不算反向，不能切段。"""
    ordered = [(1, "002"), (2, "001"), (3, "365")]
    segments = _monotonic_segments(ordered)
    assert len(segments) == 1


def test_validation_tail_rejects_previous_cycle_same_issue():
    """页面只发布到 297，回卷出现旧轮 298 —— 请求 298 必须失败。"""
    text = "\n".join(
        (
            "297期:【成语平特】跨期测试站",
            "",
            f"作者:{NAME}",
            "",
            "297期：成语平特《鸡飞狗跳》开：44准",
            "",
            "296期：成语平特《马马虎虎》开：23错",
            "",
            "295期：成语平特《鸡飞狗跳》开：22.33准",
            "",
            "298期：成语平特《龙马精神》开：11准",
        )
    )
    rule = _rule(position="tail")
    target = _target("tail")
    outcome = validate_documents(target, "298", _serialized(text), _registry(rule))
    assert outcome.ok is False
    assert outcome.failure is not None


# ---------------------------------------------------------------- 上期回顾

def test_extract_rejects_previous_draw_value():
    """``上期开马 本期待开`` 不得取到马。"""
    assert extract_target_zodiac("298期 平特一肖 上期开马 本期待开", _target()) is None
    assert extract_target_zodiac("298期 平特一肖 开 蛇(上期)", _target()) is None


def test_extract_still_accepts_current_value():
    assert extract_target_zodiac("298期 平特一肖【鼠鼠鼠】开00准", _target()) == "鼠"
