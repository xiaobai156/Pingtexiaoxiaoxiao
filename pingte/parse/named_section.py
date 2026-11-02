from __future__ import annotations

import re

from pingte.domain.models import TargetProfile

from .anchored_section import compact_author_result_line
from .context import (
    ANY_ISSUE_PATTERN,
    ParserHooks,
    RuleBook,
    clean_lines,
    has_confirmed_result_structure,
    is_section_boundary,
    issue_anchor_matches,
    issue_pattern,
    matches_keyword,
    value_line_belongs_to_issue as _value_line_belongs_to_issue,
)
from .header_section import cycle_wrap_detected, period_numbers


def named_section_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
    *,
    all_sections: bool = False,
) -> list[str]:
    rule = rules.rule_for(target)
    section_name = str(rule.get("section_name", target.name)).strip()
    if not section_name:
        return []
    lines = clean_lines(text)
    indexes = [
        index for index, line in enumerate(lines) if section_name in line
    ]
    if not indexes:
        return []
    grouped_indexes = [indexes[0]]
    for index in indexes[1:]:
        previous = grouped_indexes[-1]
        if any(
            re.search(ANY_ISSUE_PATTERN, line)
            for line in lines[previous + 1 : index]
        ):
            grouped_indexes.append(index)
    marker = issue_pattern(issue)
    keyword_indexes = [
        index
        for index in grouped_indexes
        if target.keyword and target.keyword in lines[index]
    ]
    eligible_indexes = keyword_indexes or grouped_indexes
    selected_indexes = (
        eligible_indexes
        if all_sections
        else [
            eligible_indexes[0]
            if target.position == "top"
            else eligible_indexes[-1]
        ]
    )
    collected: list[str] = []
    for index in selected_indexes:
        end = next(
            (item for item in grouped_indexes if item > index),
            len(lines),
        )
        section = []
        seen_issue = False
        stop_at_cycle_wrap = bool(rule.get("stop_at_cycle_wrap"))
        lowest_issue: int | None = None
        for local_index, line in enumerate(lines[index:end]):
            if stop_at_cycle_wrap and local_index > 0:
                numbers = period_numbers(line)
                if cycle_wrap_detected(numbers, lowest_issue):
                    break
                if numbers:
                    lowest_issue = (
                        min(numbers)
                        if lowest_issue is None
                        else min(lowest_issue, *numbers)
                    )
            if is_section_boundary(line, target, lines[index]) and not (
                not seen_issue
                and any(
                    token in line
                    for token in ("发表于", "作者：", "作者:")
                )
            ):
                break
            section.append(line)
            if re.search(ANY_ISSUE_PATTERN, line) and (
                local_index > 0 or has_confirmed_result_structure(line)
            ):
                seen_issue = True
        header = " ".join(lines[max(0, index - 2) : index + 3])
        matches: list[str] = []
        allow_bare = bool(rule.get("allow_bare_pingte_result"))
        for local_index, line in enumerate(section):
            if not re.search(marker, line):
                continue
            zodiac = (
                hooks.extract_target_zodiac(line, target)
                if has_confirmed_result_structure(
                    line, issue, allow_bare_pingte=allow_bare
                )
                or compact_author_result_line(line, issue, rule)
                else None
            )
            if zodiac:
                matches.append(line)
                continue
            segment = line
            for next_line in section[local_index + 1 : local_index + 8]:
                if re.search(ANY_ISSUE_PATTERN, next_line):
                    break
                segment = f"{segment} {next_line}"
                if hooks.extract_target_zodiac(
                    segment,
                    target,
                ) and has_confirmed_result_structure(
                    segment, issue, allow_bare_pingte=allow_bare
                ):
                    matches.append(segment)
                    break
        if target.keyword:
            keyword_matches = [
                line
                for line in matches
                if matches_keyword(line, target.keyword)
            ]
            if keyword_matches:
                if not all_sections:
                    return keyword_matches
                collected.extend(keyword_matches)
                continue
            if matches_keyword(header, target.keyword):
                neutral_matches = [
                    line
                    for line in matches
                    if not re.search(
                        r"[一二三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩]\s*肖|"
                        r"\d+\s*肖",
                        line,
                    )
                ]
                if neutral_matches:
                    if not all_sections:
                        return neutral_matches
                    collected.extend(neutral_matches)
            continue
        if matches:
            if not all_sections:
                return matches
            collected.extend(matches)
    return list(dict.fromkeys(collected))


def special_followup_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
    *,
    all_sections: bool = False,
) -> list[str]:
    rule = rules.rule_for(target)
    label = str(rule.get("followup_label", "")) or rules.followup_labels.get(
        target.url,
        "",
    )
    if not label:
        return []
    marker = issue_pattern(issue)
    lines = clean_lines(text)
    anchor_template = str(rule.get("section_anchor", ""))
    end_anchor = str(rule.get("section_end", ""))
    if anchor_template and end_anchor:
        starts = [
            index
            for index, line in enumerate(lines)
            if issue_anchor_matches(line, anchor_template, issue)
        ]
        if not starts:
            return []
        selected_starts = (
            starts
            if all_sections
            else [starts[0] if target.position == "top" else starts[-1]]
        )
        collected: list[str] = []
        for start in selected_starts:
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if issue_anchor_matches(
                        lines[index], end_anchor, issue
                    )
                ),
                None,
            )
            if end is None:
                continue
            collected.extend(
                line
                for line in lines[start + 1 : end]
                if label in line
                and hooks.extract_target_zodiac(line, target)
                and _value_line_belongs_to_issue(line, issue)
            )
        return list(dict.fromkeys(collected))
    matches: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(marker, line):
            continue
        if target.keyword and not matches_keyword(line, target.keyword):
            continue
        for next_line in lines[index + 1 : index + 6]:
            if re.search(ANY_ISSUE_PATTERN, next_line):
                break
            if label in next_line and hooks.extract_target_zodiac(
                next_line,
                target,
            ) and _value_line_belongs_to_issue(next_line, issue):
                matches.append(next_line)
    return list(dict.fromkeys(matches))
