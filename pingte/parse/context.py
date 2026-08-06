from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIACS


ANY_ISSUE_PATTERN = r"(?<!\d)\d{1,3}(?!\d)\s*期"


def issue_pattern(issue: str) -> str:
    return rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)\s*期"


def issue_anchor_matches(line: str, template: str, issue: str) -> bool:
    """Match an issue-bearing section anchor without accepting a larger issue."""
    if not template:
        return False
    if "{issue}" not in template:
        return template in line
    before, after = template.split("{issue}", 1)
    issue_number = rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)"
    pattern = re.escape(before) + issue_number + re.escape(after)
    return bool(re.search(pattern, line))


def clean_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


@dataclass(frozen=True)
class ParserHooks:
    extract_zodiac: Callable[[str], str | None]
    extract_target_zodiac: Callable[[str, TargetProfile], str | None]
    zodiac_chars: Callable[[str], str]
    dedupe_zodiac: Callable[[str], str]


class RuleBook:
    def __init__(
        self,
        rules: Iterable[dict],
        followup_labels: Mapping[str, str],
        *,
        dedicated_names: Iterable[str] = ("赌神平特", "小白平特"),
        dedicated_url_parts: Iterable[str] = (
            "topic/385412.html",
            "topic/385408.html",
        ),
    ) -> None:
        self.rules = tuple(rules)
        self.followup_labels = dict(followup_labels)
        self.dedicated_names = frozenset(dedicated_names)
        self.dedicated_url_parts = tuple(dedicated_url_parts)

    @staticmethod
    def rule_matches(rule: dict, target: TargetProfile) -> bool:
        rule_target_id = str(rule.get("target_id", ""))
        if target.target_id and rule_target_id:
            return rule_target_id == target.target_id
        return (
            str(rule.get("url_contains", "")) == target.url
            and str(rule.get("name", "")) == target.name
            and str(rule.get("position", "")) == target.position
            and str(rule.get("keyword", "")) == target.keyword
        )

    def rule_for(self, target: TargetProfile) -> dict:
        matches = [
            rule for rule in self.rules if self.rule_matches(rule, target)
        ]
        return matches[0] if len(matches) == 1 else {}

    def mode_for(self, target: TargetProfile) -> str:
        return str(self.rule_for(target).get("mode", ""))

    def is_dedicated_bottom(self, target: TargetProfile) -> bool:
        return target.name in self.dedicated_names or any(
            part in target.url for part in self.dedicated_url_parts
        )

    def has_dedicated_parser(self, target: TargetProfile) -> bool:
        return bool(self.mode_for(target)) or self.is_dedicated_bottom(target)


def matches_keyword(line: str, keyword: str) -> bool:
    return not keyword or keyword in line


def many_zodiac_category(line: str) -> bool:
    return bool(
        re.search(
            r"[二三四五六七八九十②③④⑤⑥⑦⑧⑨⑩]\s*肖|"
            r"[2-9]\s*肖|1[0-9]\s*肖",
            line,
        )
    )


def selected_section_starts(
    starts: list[int],
    target: TargetProfile,
    rule: dict,
    *,
    all_sections: bool = False,
) -> list[int]:
    if all_sections:
        return list(starts)
    if not starts:
        return []
    # target.position is the only direction authority. A legacy override is
    # rejected during config validation and ignored here for fail-closed use
    # by tests or callers that construct rules directly.
    return [starts[0] if target.position == "top" else starts[-1]]


def has_confirmed_result_structure(
    line: str,
    issue: str | None = None,
) -> bool:
    if issue and not re.search(issue_pattern(issue), line):
        return False
    if any(
        token in line
        for token in (
            "→绝密数据",
            "→横扫庄家",
            "独家高手",
            "免费公開",
            "免费公开",
        )
    ):
        return False
    if re.search(rf"=[{ZODIACS}]+\s*[√✓×xX]", line):
        return True
    if re.search(
        r"[开開](?:\s*[:：]?\s*[开開])?[\s\S]{0,18}"
        r"(?:准|中|错|赢|输|对|對|赚|賺|√|✓|×|x|X)",
        line,
    ):
        return True
    if re.search(rf"平[特一]{{1,3}}[\s:：]*[{ZODIACS}]+肖?[？?]?\s*$", line):
        return True
    if re.search(rf"平特[^期]{{0,10}}[{ZODIACS}]{{2,}}\s*$", line):
        return True
    return bool(
        re.search(rf"[{ZODIACS}]+肖[？?]?\s*$", line)
        and "平特" in line
    )


def is_section_boundary(
    line: str,
    target: TargetProfile,
    header: str = "",
) -> bool:
    if line == header:
        return False
    if line.startswith((".", "function ")) or any(
        token in line for token in ("上一篇", "下一篇")
    ):
        return True
    if re.search(r"^(?:广告|广告推荐|赞助|推广)(?:$|[:：])", line):
        return True
    return any(token in line for token in ("发表于", "作者：", "作者:")) and (
        target.name not in line
    )
