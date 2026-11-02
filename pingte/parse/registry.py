from __future__ import annotations

import re

from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIACS

from .anchored_section import (
    anchored_section_issue_lines,
    author_section_issue_lines,
)
from .context import (
    ANY_ISSUE_PATTERN,
    ParserHooks,
    RuleBook,
    clean_lines,
    issue_pattern,
    matches_keyword,
)
from .formula_section import anchored_formula_section_issue_lines
from .header_section import (
    special_ai_public_label_issue_lines,
    special_header_section_issue_lines,
    special_nearest_keyword_line_issue_lines,
    special_next_line_zodiac_issue_lines,
)
from .named_section import (
    named_section_issue_lines,
    special_followup_issue_lines,
)
from .row_section import row_section_issue_lines


class DedicatedParserRegistry:
    def __init__(self, rules: RuleBook, hooks: ParserHooks) -> None:
        self.rules = rules
        self.hooks = hooks

    def dedicated_bottom_issue_zodiac_lines(
        self,
        text: str,
        target: TargetProfile,
        issue: str,
    ) -> list[str]:
        rule = self.rules.rule_for(target)
        if (
            not self.rules.is_dedicated_bottom(target)
            or rule.get("source_strategy") != "image_resource"
            or not target.name
        ):
            return []
        marker = issue_pattern(issue)
        pattern = (
            marker
            + rf"\s*(?:[:：]\s*|\s+)([{ZODIACS}])"
            rf"(?:\s|$|[√✓×xX。,.，、])"
        )
        lines = clean_lines(text)
        identity_indexes = [
            index for index, line in enumerate(lines) if target.name in line
        ]
        return [
            line
            for index, line in enumerate(lines)
            if re.search(pattern, line)
            and (
                target.name in line
                if target.target_id
                else any(identity_index <= index for identity_index in identity_indexes)
            )
        ]

    def parse_issue_lines(
        self,
        text: str,
        target: TargetProfile,
        issue: str,
        *,
        all_blocks: bool = False,
    ) -> list[str]:
        normalized_issue = str(int(issue))
        dedicated = self.dedicated_bottom_issue_zodiac_lines(
            text,
            target,
            normalized_issue,
        )
        if dedicated:
            return dedicated
        mode = self.rules.mode_for(target)
        if mode == "header_section":
            return special_header_section_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "followup_label":
            return special_followup_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "next_line_zodiac":
            return special_next_line_zodiac_issue_lines(
                text,
                target,
                normalized_issue,
                self.hooks,
            )
        if mode in {"nearest_keyword_line", "linked_topic"}:
            return special_nearest_keyword_line_issue_lines(
                text,
                target,
                normalized_issue,
                self.hooks,
            )
        if mode == "named_section":
            return named_section_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "anchored_section":
            return anchored_section_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "anchored_formula_section":
            return anchored_formula_section_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "author_section":
            return author_section_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "row_section":
            return row_section_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        if mode == "ai_public_label":
            return special_ai_public_label_issue_lines(
                text,
                target,
                normalized_issue,
                self.rules,
                self.hooks,
                all_sections=all_blocks,
            )
        return []

    def parse_issue_lines_all(
        self,
        text: str,
        target: TargetProfile,
        issue: str,
    ) -> list[str]:
        return self.parse_issue_lines(text, target, issue, all_blocks=True)


def issue_lines(
    text: str,
    issue: str,
    keyword: str,
    hooks: ParserHooks,
) -> list[str]:
    marker = issue_pattern(issue)
    lines = clean_lines(text)
    matches: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(marker, line):
            continue
        if keyword and not matches_keyword(line, keyword):
            continue
        segment = line
        for next_line in lines[index + 1 : index + 5]:
            if re.search(ANY_ISSUE_PATTERN, next_line):
                break
            if keyword and not matches_keyword(next_line, keyword):
                break
            if hooks.extract_zodiac(segment) and re.search(r"[开開]", segment):
                break
            segment = f"{segment} {next_line}"
        matches.append(segment)
    return matches


def choose_line(
    lines: list[str],
    target: TargetProfile,
    hooks: ParserHooks,
) -> str | None:
    candidates = [
        line
        for line in lines
        if hooks.extract_target_zodiac(line, target)
    ]
    if not candidates:
        return None
    return candidates[0] if target.position == "top" else candidates[-1]
