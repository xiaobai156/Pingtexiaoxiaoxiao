from __future__ import annotations

from pingte.domain.failures import FailureCode
from pingte.domain.models import SourceDocument, Target
from pingte.fetch.documents import serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.identity import target_cache_key
from pingte.validation.issue import (
    extract_target_zodiac,
    extract_zodiac,
    strict_extract_zodiac,
)
from pingte.validation.result import validate_documents


def make_target(name: str = "测试目录", keyword: str = "成语平特") -> Target:
    return Target(
        "https://example.test/topic/1.html",
        "top",
        name,
        keyword,
        "PT-TEST",
        1,
    )


def make_registry(target: Target, mode: str = "header_section") -> DedicatedParserRegistry:
    rule = {
        "target_id": target.target_id,
        "url_contains": target.url,
        "position": target.position,
        "name": target.name,
        "keyword": target.keyword,
        "mode": mode,
        "source_strategy": "http_main",
        "section_name": target.name,
    }
    hooks = ParserHooks(
        extract_zodiac=extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=lambda value: "".join(ch for ch in value if ch in "鼠牛虎兔龙蛇马羊猴鸡狗猪"),
        dedupe_zodiac=lambda value: "".join(dict.fromkeys(value)),
    )
    return DedicatedParserRegistry(
        RuleBook([rule], {}, dedicated_names=(), dedicated_url_parts=()),
        hooks,
    )


def source(text: str, *, primary: bool = True, source: str = "http-main") -> SourceDocument:
    return SourceDocument(source, "https://example.test/topic/1.html", primary, text)


def encoded(*documents: SourceDocument) -> str:
    return serialize_source_documents(documents)


def test_extract_zodiac_rejects_declaration_and_directory_name_pollution():
    target = make_target(name="龙马目录")

    assert extract_zodiac("164期【龙马】开00准") == "龙马"
    assert extract_zodiac("164期站长宣言：如遇马后炮资料直接封号开000中") is None
    assert extract_target_zodiac("164期龙马目录【成语平特】开00准", target) is None
    assert strict_extract_zodiac("164期成语平特开01准") is None


def test_validation_requires_exact_issue_and_target_keyword():
    target = make_target()
    registry = make_registry(target)
    text = encoded(
        source(
            "测试目录\n"
            "成语平特\n"
            "164期成语平特【鼠】开00准\n"
            "163期成语平特【牛】开00准\n"
        )
    )

    outcome = validate_documents(target, "164", text, registry)

    assert outcome.ok
    assert outcome.zodiac == "鼠"
    assert outcome.candidate is not None
    assert "164期" in outcome.candidate.raw_line


def test_validation_rejects_missing_exact_issue_without_using_adjacent_issue():
    target = make_target()
    registry = make_registry(target)
    text = encoded(source("测试目录\n成语平特\n163期成语平特【牛】开00准\n"))

    outcome = validate_documents(target, "164", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code in {
        FailureCode.ISSUE_MISSING,
        FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW,
        FailureCode.ZODIAC_MISSING,
    }


def test_validation_rejects_same_issue_conflict_across_primary_documents():
    target = make_target()
    registry = make_registry(target)
    text = encoded(
        source("测试目录\n成语平特\n164期成语平特【鼠】开00准\n", source="http-main-a"),
        source("测试目录\n成语平特\n164期成语平特【猪】开00准\n", source="http-main-b"),
    )

    outcome = validate_documents(target, "164", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code == FailureCode.SOURCE_CONFLICT
    assert "鼠" in outcome.failure.message and "猪" in outcome.failure.message


def test_validation_rejects_more_than_two_zodiacs():
    target = make_target()
    registry = make_registry(target)
    text = encoded(source("测试目录\n成语平特\n164期成语平特【鼠牛虎】开00准\n"))

    outcome = validate_documents(target, "164", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code == FailureCode.TOO_MANY_ZODIACS
    assert outcome.zodiac == "鼠牛虎"


def test_validation_keeps_same_zodiac_duplicates_but_returns_one_result():
    target = make_target()
    registry = make_registry(target)
    text = encoded(
        source(
            "测试目录\n成语平特\n"
            "164期成语平特【鼠鼠】开00准\n"
            "164期成语平特【鼠】开00准\n"
        )
    )

    outcome = validate_documents(target, "164", text, registry)

    assert outcome.ok
    assert outcome.zodiac == "鼠"


def test_validation_rejects_target_outside_top_direction_window():
    target = make_target()
    registry = make_registry(target)
    text = encoded(
        source(
            "测试目录\n成语平特\n"
            "210期成语平特【鼠】开00准\n"
            "209期成语平特【牛】开00准\n"
            "208期成语平特【虎】开00准\n"
            "207期成语平特【兔】开00准\n"
            "206期成语平特【龙】开00准\n"
            "205期成语平特【蛇】开00准\n"
        )
    )

    outcome = validate_documents(target, "205", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code == FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW
    assert outcome.failure.visible_issues == ("210", "209", "208")


def test_validation_rejects_target_outside_tail_direction_window():
    target = make_target()
    target = Target(target.url, "tail", target.name, target.keyword, target.target_id, target.rule_version)
    registry = make_registry(target)
    text = encoded(
        source(
            "测试目录\n成语平特\n"
            "205期成语平特【鼠】开00准\n"
            "206期成语平特【牛】开00准\n"
            "207期成语平特【虎】开00准\n"
            "208期成语平特【兔】开00准\n"
            "209期成语平特【龙】开00准\n"
            "210期成语平特【蛇】开00准\n"
        )
    )

    outcome = validate_documents(target, "205", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code == FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW
    assert outcome.failure.visible_issues == ("208", "209", "210")


def test_validation_binds_compact_followup_labels_to_their_issue_anchor():
    target = Target(
        "https://example.test/topic/ai.html",
        "top",
        "AI平特肖",
        "AI推荐平特",
        "PT-AI",
        1,
    )
    rule = {
        "target_id": target.target_id,
        "url_contains": target.url,
        "position": target.position,
        "name": target.name,
        "keyword": target.keyword,
        "mode": "followup_label",
        "source_strategy": "browser_main",
        "section_anchor": "{issue}期【AI推荐平特】",
        "section_end": "推荐平码",
        "followup_label": "平特一肖",
    }
    hooks = ParserHooks(
        extract_zodiac=extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=lambda value: "".join(
            character for character in value if character in "鼠牛虎兔龙蛇马羊猴鸡狗猪"
        ),
        dedupe_zodiac=lambda value: "".join(dict.fromkeys(value)),
    )
    registry = DedicatedParserRegistry(
        RuleBook([rule], {}, dedicated_names=(), dedicated_url_parts=()),
        hooks,
    )
    text = encoded(
        source(
            "213期【AI推荐平特】开00中\n"
            "平特一肖：马马马\n"
            "推荐平码\n"
            "212期【AI推荐平特】开00中\n"
            "平特一肖：鼠鼠鼠\n"
            "推荐平码\n"
            "211期【AI推荐平特】开00中\n"
            "平特一肖：羊羊羊\n"
            "推荐平码\n"
            "210期【AI推荐平特】开00中\n"
            "平特一肖：鼠鼠鼠\n"
            "推荐平码\n"
        )
    )

    outcome = validate_documents(target, "212", text, registry)

    assert outcome.ok
    assert outcome.zodiac == "鼠"
    assert outcome.candidate is not None
    assert outcome.candidate.anchor_line.startswith("212期")

    assert registry.parse_issue_lines_all(
        "213期【AI推荐平特】开00中\n平特一肖：马马马\n推荐平码\n",
        target,
        "13",
    ) == []


def test_validation_preserves_structured_candidate_evidence():
    target = make_target()
    registry = make_registry(target)
    outcome = validate_documents(
        target,
        "164",
        encoded(source("测试目录\n成语平特\n164期成语平特【鼠】开00准\n")),
        registry,
    )

    assert outcome.ok
    assert outcome.candidate is not None
    assert outcome.candidate.anchor_line == "测试目录"
    assert outcome.candidate.block_start == 0
    assert outcome.candidate.block_end >= outcome.candidate.block_start
    assert outcome.candidate.parser_rule_id == target.target_id
    assert outcome.candidate.direction == "top"
    assert outcome.candidate.raw_zodiac_order == "鼠"


def test_validation_rejects_same_issue_conflict_across_target_blocks():
    target = make_target()
    rule = {
        "target_id": target.target_id,
        "url_contains": target.url,
        "position": target.position,
        "name": target.name,
        "keyword": target.keyword,
        "mode": "anchored_section",
        "source_strategy": "http_main",
        "section_anchor": "测试目录开始",
        "section_end": "测试目录结束",
        "line_keyword": target.keyword,
    }
    hooks = ParserHooks(
        extract_zodiac=extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=lambda value: "".join(ch for ch in value if ch in "鼠牛虎兔龙蛇马羊猴鸡狗猪"),
        dedupe_zodiac=lambda value: "".join(dict.fromkeys(value)),
    )
    registry = DedicatedParserRegistry(
        RuleBook([rule], {}, dedicated_names=(), dedicated_url_parts=()),
        hooks,
    )
    text = encoded(
        source(
            "测试目录开始\n164期成语平特【鼠】开00准\n测试目录结束\n"
            "测试目录开始\n164期成语平特【牛】开00准\n测试目录结束\n"
        )
    )

    outcome = validate_documents(target, "164", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code == FailureCode.AMBIGUOUS_CANDIDATES
    assert "鼠" in outcome.failure.message and "牛" in outcome.failure.message


def test_validation_rejects_keyword_header_without_target_identity():
    target = make_target()
    registry = make_registry(target)
    text = encoded(
        source(
            "其他目录【成语平特】\n"
            "164期成语平特【鼠】开00准\n"
        )
    )

    outcome = validate_documents(target, "164", text, registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code in {FailureCode.ANCHOR_MISSING, FailureCode.ZODIAC_MISSING}


def test_validation_requires_a_dedicated_rule():
    target = make_target()
    registry = DedicatedParserRegistry(
        RuleBook([], {}, dedicated_names=(), dedicated_url_parts=()),
        ParserHooks(
            extract_zodiac=extract_zodiac,
            extract_target_zodiac=extract_target_zodiac,
            zodiac_chars=lambda value: value,
            dedupe_zodiac=lambda value: value,
        ),
    )

    outcome = validate_documents(target, "164", encoded(source("164期成语平特【鼠】开00准")), registry)

    assert not outcome.ok
    assert outcome.failure is not None
    assert outcome.failure.code == FailureCode.RULE_MISSING


def test_target_cache_key_includes_all_target_identity_fields():
    target = make_target()

    assert target_cache_key(target) == (
        target.url,
        target.name,
        target.position,
        target.keyword,
    )
