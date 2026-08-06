from __future__ import annotations

import re

from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIACS

from .context import (
    ParserHooks,
    RuleBook,
    clean_lines,
    has_confirmed_result_structure,
    issue_anchor_matches,
    issue_pattern,
    many_zodiac_category,
    matches_keyword,
    selected_section_starts,
)


def anchored_section_issue_lines(
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
    anchor = anchor_template.replace(
        "{issue}", str(int(issue))
    )
    end_anchor_template = str(rule.get("section_end", ""))
    end_anchor = end_anchor_template.replace(
        "{issue}", str(int(issue))
    )
    line_keyword = str(rule.get("line_keyword", target.keyword))
    anchor_exact = bool(rule.get("section_anchor_exact"))
    end_exact = bool(rule.get("section_end_exact"))
    allow_many = bool(rule.get("allow_many_zodiac_candidate"))
    if not anchor or not end_anchor:
        return []
    lines = clean_lines(text)
    starts = [
        index
        for index, line in enumerate(lines)
        if (
            line == anchor
            if anchor_exact
            else issue_anchor_matches(line, anchor_template, issue)
        )
    ]
    if not starts:
        return []
    marker = issue_pattern(issue)
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
                if (
                    lines[index] == end_anchor
                    if end_exact
                    else issue_anchor_matches(
                        lines[index], end_anchor_template, issue
                    )
                )
            ),
            None,
        )
        if end is None:
            continue
        matches = [
            line
            for line in lines[start + 1 : end]
            if re.search(marker, line)
            and matches_keyword(line, line_keyword)
            and hooks.extract_target_zodiac(line, target)
            and (allow_many or not many_zodiac_category(line))
        ]
        if matches:
            if not all_sections:
                return matches
            collected.extend(matches)
    return list(dict.fromkeys(collected))


def author_section_result_structure(line: str, issue: str) -> bool:
    if has_confirmed_result_structure(line, issue):
        return True
    return bool(
        re.search(issue_pattern(issue), line)
        and re.search(
            rf"平特\s*[{ZODIACS}]+肖?\s*(?:√|✓|准|中|错|×|x|X)",
            line,
        )
    )


def compact_author_result_line(line: str, issue: str, rule: dict) -> bool:
    if rule.get("result_line_format") != "compact_zodiac_suffix":
        return False
    prefix = str(rule.get("result_prefix", ""))
    suffix = str(rule.get("result_suffix", ""))
    if not suffix:
        return False
    marker = (
        r"(?:√|✓|×|x|X)"
        if rule.get("result_marker_required")
        else r"(?:√|✓|×|x|X)?"
    )
    return bool(
        re.fullmatch(
            rf"{issue_pattern(issue)}\s*{re.escape(prefix)}[{ZODIACS}]{{1,2}}"
            rf"{re.escape(suffix)}\s*{marker}",
            line,
        )
    )


def author_section_issue_lines(
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
    anchor = anchor_template.replace("{issue}", str(int(issue)))
    end_anchor = end_anchor_template.replace("{issue}", str(int(issue)))
    anchor_exact = bool(rule.get("section_anchor_exact"))
    end_exact = bool(rule.get("section_end_exact"))
    if not anchor or not end_anchor or not target.keyword:
        return []
    lines = clean_lines(text)
    starts = [
        index
        for index, line in enumerate(lines)
        if (
            line == anchor
            if anchor_exact
            else issue_anchor_matches(line, anchor_template, issue)
        )
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
        header_start = max(0, start - 8)
        if not any(target.keyword in line for line in lines[header_start:start]):
            continue
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if (
                    lines[index] == end_anchor
                    if end_exact
                    else issue_anchor_matches(
                        lines[index], end_anchor_template, issue
                    )
                )
            ),
            None,
        )
        if end is None:
            continue
        matches: list[str] = []
        for line in lines[start + 1 : end]:
            if not re.search(issue_pattern(issue), line):
                continue
            if rule.get("result_line_format") == "compact_zodiac_suffix":
                if compact_author_result_line(line, issue, rule):
                    matches.append(line)
                continue
            if author_section_result_structure(
                line,
                issue,
            ) and hooks.extract_target_zodiac(line, target):
                matches.append(line)
        if matches:
            if not all_sections:
                return matches
            collected.extend(matches)
    return list(dict.fromkeys(collected))
