from pingte.application.shadow import ShadowCase, compare_parsers
from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIACS
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.registry import DedicatedParserRegistry


def extract(line: str) -> str | None:
    values = "".join(character for character in line if character in ZODIACS)
    return "".join(dict.fromkeys(values)) or None


HOOKS = ParserHooks(
    extract_zodiac=extract,
    extract_target_zodiac=lambda line, _target: extract(line),
    zodiac_chars=lambda line: "".join(
        character for character in line if character in ZODIACS
    ),
    dedupe_zodiac=lambda value: "".join(dict.fromkeys(value)),
)


def target(index: int, mode: str) -> TargetProfile:
    return TargetProfile(
        f"https://example.test/topic/{index}.html",
        "top",
        f"目录{index}",
        "成语平特",
        target_id=f"PT-{index:04d}",
    )


def rule(item: TargetProfile, mode: str, **extra) -> dict:
    return {
        "target_id": item.target_id,
        "url_contains": item.url,
        "name": item.name,
        "position": item.position,
        "keyword": item.keyword,
        "mode": mode,
        **extra,
    }


def test_all_configured_modes_match_frozen_same_document_contracts():
    definitions = []

    item = target(1, "header_section")
    definitions.append(
        (
            item,
            rule(item, "header_section"),
            "目录1\n【成语平特】\n211期 成语平特【虎】开00准\n210期 成语平特【牛】开00准",
            ["211期 成语平特【虎】开00准"],
        )
    )

    item = target(2, "followup_label")
    definitions.append(
        (
            item,
            rule(
                item,
                "followup_label",
                section_anchor="目录2 {issue}期",
                section_end="栏目结束",
                followup_label="平特一肖",
            ),
            "目录2 211期\n平特一肖【虎】开00准\n栏目结束\n平特一肖【牛】开00准",
            ["平特一肖【虎】开00准"],
        )
    )

    item = target(3, "next_line_zodiac")
    definitions.append(
        (
            item,
            rule(item, "next_line_zodiac"),
            "211期 成语平特\n开奖结果【虎】开00准\n210期 成语平特【牛】开00准",
            ["211期 成语平特 开奖结果【虎】开00准"],
        )
    )

    for index, mode in ((4, "nearest_keyword_line"), (5, "linked_topic")):
        item = target(index, mode)
        definitions.append(
            (
                item,
                rule(item, mode),
                "1211期 成语平特【牛】开00准\n211期 成语平特【虎】开00准",
                ["211期 成语平特【虎】开00准"],
            )
        )

    item = target(6, "named_section")
    definitions.append(
        (
            item,
            rule(item, "named_section", section_name="目录6"),
            "目录6【成语平特】\n211期 成语平特【虎】开00准\n目录6 其它栏目\n211期 成语平特【牛】开00准",
            ["211期 成语平特【虎】开00准"],
        )
    )

    item = target(7, "ai_public_label")
    definitions.append(
        (
            item,
            rule(
                item,
                "ai_public_label",
                section_anchor="AAAAA级大公开{issue}期",
                section_end="本期结束",
            ),
            "AAAAA级大公开211期\n成语平特【虎】开00准\n本期结束\n成语平特【牛】开00准",
            ["AAAAA级大公开211期 成语平特【虎】开00准"],
        )
    )

    item = target(8, "anchored_section")
    definitions.append(
        (
            item,
            rule(
                item,
                "anchored_section",
                section_anchor="目录8开始",
                section_end="目录8结束",
            ),
            "目录8开始\n211期 成语平特【虎】开00准\n目录8结束\n211期 成语平特【牛】开00准",
            ["211期 成语平特【虎】开00准"],
        )
    )

    item = target(9, "anchored_formula_section")
    definitions.append(
        (
            item,
            rule(
                item,
                "anchored_formula_section",
                section_anchor="目录9开始",
                section_end="目录9结束",
            ),
            "目录9开始\n211期 01 02=虎√\n目录9结束\n211期 01 02=牛√",
            ["211期 01 02=虎√"],
        )
    )

    item = target(10, "author_section")
    definitions.append(
        (
            item,
            rule(
                item,
                "author_section",
                section_anchor="目录10 发表于",
                section_end="作者区结束",
            ),
            "成语平特\n目录10 发表于\n211期 成语平特【虎】开00准\n作者区结束\n211期 成语平特【牛】开00准",
            ["211期 成语平特【虎】开00准"],
        )
    )

    registry = DedicatedParserRegistry(
        RuleBook((entry[1] for entry in definitions), {}),
        HOOKS,
    )
    expected = {entry[0].target_id: entry[3] for entry in definitions}
    cases = [
        ShadowCase(entry[0].target_id, entry[0], "211", entry[2])
        for entry in definitions
    ]

    differences = compare_parsers(
        cases,
        lambda item, _issue, _document: expected[item.target_id],
        lambda item, issue, document: registry.parse_issue_lines(
            document,
            item,
            issue,
        ),
    )

    assert differences == []
