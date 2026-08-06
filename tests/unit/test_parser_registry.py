from pingte.domain.models import TargetProfile
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.registry import DedicatedParserRegistry


def hooks() -> ParserHooks:
    return ParserHooks(
        extract_zodiac=lambda line: (
            "虎" if "虎" in line else "牛" if "牛" in line else None
        ),
        extract_target_zodiac=lambda line, _target: (
            "虎" if "虎" in line else "牛" if "牛" in line else None
        ),
        zodiac_chars=lambda line: "".join(
            character for character in line if character in "鼠牛虎兔龙蛇马羊猴鸡狗猪"
        ),
        dedupe_zodiac=lambda value: "".join(dict.fromkeys(value)),
    )


def target() -> TargetProfile:
    return TargetProfile(
        "https://example.test/topic/1.html",
        "top",
        "目录A",
        "成语平特",
        target_id="PT-0001",
    )


def rule() -> dict:
    item = target()
    return {
        "target_id": item.target_id,
        "url_contains": item.url,
        "name": item.name,
        "position": item.position,
        "keyword": item.keyword,
        "mode": "nearest_keyword_line",
    }


def test_rulebook_resolves_exact_permanent_identity():
    book = RuleBook((rule(),), {})

    assert book.rule_for(target()) == rule()
    assert book.mode_for(target()) == "nearest_keyword_line"


def test_rulebook_fails_closed_when_rule_is_missing_or_duplicated():
    item = target()

    assert RuleBook((), {}).rule_for(item) == {}
    assert RuleBook((rule(), rule()), {}).rule_for(item) == {}


def test_registry_dispatches_only_the_configured_mode_and_exact_issue():
    registry = DedicatedParserRegistry(RuleBook((rule(),), {}), hooks())
    text = "\n".join(
        (
            "1211期 成语平特【虎】开00准",
            "211期 成语平特【虎】开00准",
            "210期 成语平特【牛】开00准",
        )
    )

    assert registry.parse_issue_lines(text, target(), "211") == [
        "211期 成语平特【虎】开00准"
    ]


def test_registry_never_falls_back_to_another_mode():
    item = rule()
    item["mode"] = "named_section"
    registry = DedicatedParserRegistry(RuleBook((item,), {}), hooks())

    assert registry.parse_issue_lines(
        "211期 成语平特【虎】开00准",
        target(),
        "211",
    ) == []


def test_registry_can_collect_all_target_blocks_for_conflict_validation():
    item = target()
    item_rule = rule()
    item_rule.update(
        {
            "mode": "anchored_section",
            "section_anchor": "目录A开始",
            "section_end": "目录A结束",
        }
    )
    registry = DedicatedParserRegistry(RuleBook((item_rule,), {}), hooks())
    text = (
        "目录A开始\n211期 成语平特【虎】开00准\n目录A结束\n"
        "目录A开始\n211期 成语平特【牛】开00准\n目录A结束\n"
    )

    assert registry.parse_issue_lines_all(text, item, "211") == [
        "211期 成语平特【虎】开00准",
        "211期 成语平特【牛】开00准",
    ]


def test_image_result_parser_requires_the_bound_target_identity():
    item = TargetProfile(
        "https://example.test/topic/385412.html",
        "tail",
        "赌神平特",
        "赌神平特",
        target_id="PT-0011",
    )
    registry = DedicatedParserRegistry(
        RuleBook(
            [
                {
                    "target_id": item.target_id,
                    "url_contains": item.url,
                    "name": item.name,
                    "position": item.position,
                    "keyword": item.keyword,
                    "mode": "header_section",
                    "source_strategy": "image_resource",
                }
            ],
            {},
        ),
        hooks(),
    )

    assert registry.parse_issue_lines("164期：马\n", item, "164") == []
    assert registry.parse_issue_lines("赌神平特 164期：马\n", item, "164") == [
        "赌神平特 164期：马"
    ]


def test_dynamic_record_parser_does_not_require_author_name_in_record_body():
    item = TargetProfile(
        "https://example.test/#/users/1",
        "top",
        "作者名不在正文",
        "平特⒈肖",
        target_id="PT-DYNAMIC",
    )
    registry = DedicatedParserRegistry(
        RuleBook(
            [
                {
                    "target_id": item.target_id,
                    "url_contains": item.url,
                    "name": item.name,
                    "position": item.position,
                    "keyword": item.keyword,
                    "mode": "header_section",
                    "source_strategy": "dynamic_record",
                    "record_topic": "平特⒈肖",
                }
            ],
            {},
        ),
        hooks(),
    )

    text = "平特⒈肖\n164期:平特⒈肖【虎】开00中\n"

    assert registry.parse_issue_lines(text, item, "164") == [
        "164期:平特⒈肖【虎】开00中"
    ]
