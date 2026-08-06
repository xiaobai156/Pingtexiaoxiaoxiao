from __future__ import annotations

import re

from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIACS

from .context import (
    ParserHooks,
    RuleBook,
    clean_lines,
    issue_anchor_matches,
    issue_pattern,
    selected_section_starts,
)


def formula_section_zodiac(
    line: str,
    issue: str,
    hooks: ParserHooks,
    allow_question_summary: bool = False,
) -> str | None:
    if not re.search(issue_pattern(issue), line):
        return None
    equals_index = line.find("=")
    if equals_index >= 0:
        issue_match = re.search(issue_pattern(issue), line)
        formula_prefix = (
            line[issue_match.end() : equals_index]
            if issue_match
            else line[:equals_index]
        )
        allowed_prefix = re.sub(
            r"(?:公式|平特一肖|平特|规律|二肖|一肖)",
            "",
            formula_prefix,
        )
        if re.search(r"[\u3400-\u9fff]", allowed_prefix):
            return None
        numeric_parts = [
            int(value)
            for value in re.findall(
                r"(?<!\d)\d{1,2}(?!\d)",
                formula_prefix,
            )
        ]
        if len(numeric_parts) >= 2 and all(value == 0 for value in numeric_parts):
            return None
    formula = re.search(
        rf"=\s*([{ZODIACS}](?:\s*[√✓×xX]\s*[{ZODIACS}])*"
        rf"\s*[√✓×xX]?\s*)$",
        line,
    )
    if formula:
        return hooks.dedupe_zodiac(hooks.zodiac_chars(formula.group(1)))
    question_suffix = r"(?:\s*[？?])?" if allow_question_summary else ""
    summary = re.search(
        rf"^{issue_pattern(issue)}\s*(?:平特一肖|平特)\s*"
        rf"([{ZODIACS}]+)肖{question_suffix}\s*$",
        line,
    )
    if summary:
        return hooks.dedupe_zodiac(summary.group(1))
    return None


def anchored_formula_section_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
    *,
    all_sections: bool = False,
) -> list[str]:
    rule = rules.rule_for(target)
    anchor_template = str(rule.get("section_anchor", ""))
    end_anchor_template = str(rule.get("section_end", ""))
    anchor = anchor_template
    end_anchor = end_anchor_template
    if not anchor or not end_anchor:
        return []
    allow_question_summary = bool(rule.get("allow_question_summary"))
    lines = clean_lines(text)
    starts = [
        index
        for index, line in enumerate(lines)
        if issue_anchor_matches(line, anchor_template, issue)
    ]
    if not starts:
        return []
    collected: list[str] = []
    for start in selected_section_starts(
        starts,
        target,
        rule,
        all_sections=all_sections,
    ):
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if issue_anchor_matches(
                    lines[index], end_anchor_template, issue
                )
            ),
            None,
        )
        if end is None:
            continue
        matches = [
            line
            for line in lines[start + 1 : end]
            if formula_section_zodiac(
                line,
                issue,
                hooks,
                allow_question_summary,
            )
        ]
        if matches:
            if not all_sections:
                return matches
            collected.extend(matches)
    return list(dict.fromkeys(collected))
