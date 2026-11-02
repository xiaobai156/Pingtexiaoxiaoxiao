from __future__ import annotations

import re

from pingte.domain.models import TargetProfile

from .context import (
    ANY_ISSUE_PATTERN,
    ParserHooks,
    RuleBook,
    clean_lines,
    has_confirmed_result_structure,
    is_section_boundary,
    issue_anchor_matches,
    issue_pattern,
    issue_pattern_for_rule,
    many_zodiac_category,
    matches_keyword,
    value_line_belongs_to_issue,
)


def accepted_result_status(line: str, rule: dict) -> bool:
    statuses = rule.get("accepted_result_statuses")
    if statuses is None:
        return True
    if not isinstance(statuses, (list, tuple)):
        return False
    normalized_line = line.rstrip()
    return any(
        str(status).strip() and normalized_line.endswith(str(status).strip())
        for status in statuses
    )


def period_numbers(line: str) -> list[int]:
    """Period-marked numbers on one line, for example 365 from ``365期...``."""
    return [
        int(match) for match in re.findall(r"(?<!\d)(\d{1,3})(?!\d)\s*期", line)
    ]


def cycle_wrap_detected(numbers: list[int], lowest_issue: int | None) -> bool:
    """True when the column restarted after a lower period number was seen.

    Sites that keep more than one full numbering cycle in one column list the
    current cycle first (descending) and then continue with the previous cycle,
    whose numbers jump back up. Only pages proven to have that wrap may enable
    ``stop_at_cycle_wrap``; the wrapped list must never be treated as another
    candidate for the same issue.
    """
    return bool(numbers) and lowest_issue is not None and min(numbers) > lowest_issue


def target_identity_header_indexes(
    lines: list[str],
    header_indexes: list[int],
    target: TargetProfile,
    rules: RuleBook,
) -> list[int]:
    rule = rules.rule_for(target)
    identities = {target.name, str(rule.get("section_name", "")).strip()}
    matches: list[int] = []
    for position, index in enumerate(header_indexes):
        start = max(0, index - 2)
        end = min(len(lines), index + 3)
        if position > 0:
            start = max(start, header_indexes[position - 1] + 1)
        if position + 1 < len(header_indexes):
            end = min(end, header_indexes[position + 1])
        window = " ".join(lines[start:end])
        if any(identity and identity in window for identity in identities):
            matches.append(index)
    return matches


def special_header_section_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
    *,
    all_sections: bool = False,
) -> list[str]:
    rule = rules.rule_for(target)
    marker = issue_pattern_for_rule(issue, rule)
    section_end_text = str(rule.get("section_end_text", ""))
    allow_short_pingte = bool(rule.get("allow_short_pingte_result"))
    lines = clean_lines(text)
    if rule.get("source_strategy") == "dynamic_record":
        return [
            line
            for line in lines
            if re.search(marker, line)
            and matches_keyword(line, target.keyword)
            and has_confirmed_result_structure(line, issue, issue_marker=marker)
            and accepted_result_status(line, rule)
            and hooks.extract_target_zodiac(line, target)
        ]
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if target.keyword in line and not has_confirmed_result_structure(line)
    ]
    if not header_indexes:
        return []
    named_headers = target_identity_header_indexes(
        lines,
        header_indexes,
        target,
        rules,
    )
    if named_headers:
        eligible = named_headers
    else:
        # A keyword by itself is not a target identity. Even one remaining
        # keyword header can belong to another column or author.
        return []
    selected = (
        eligible
        if all_sections
        else [eligible[0] if target.position == "top" else eligible[-1]]
    )
    collected: list[str] = []
    for index in selected:
        position = header_indexes.index(index)
        end = (
            header_indexes[position + 1]
            if position + 1 < len(header_indexes)
            else len(lines)
        )
        matches: list[str] = []
        seen_issue = False
        stop_at_cycle_wrap = bool(rule.get("stop_at_cycle_wrap"))
        lowest_issue: int | None = None
        for local_index, line in enumerate(lines[index:end]):
            if section_end_text and section_end_text in line and line != lines[index]:
                break
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
                and any(token in line for token in ("发表于", "作者：", "作者:"))
            ):
                break
            if local_index > 0 and re.search(ANY_ISSUE_PATTERN, line):
                seen_issue = True
            if not re.search(marker, line) or many_zodiac_category(line):
                continue
            if has_confirmed_result_structure(
                line,
                issue,
                issue_marker=marker,
                allow_short_pingte=allow_short_pingte,
            ) and accepted_result_status(line, rule) and value_line_belongs_to_issue(
                line,
                issue,
            ) and hooks.extract_target_zodiac(
                line,
                target,
                rule,
            ):
                matches.append(line)
        if not all_sections:
            return matches
        collected.extend(matches)
    return list(dict.fromkeys(collected))


def special_next_line_zodiac_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    hooks: ParserHooks,
) -> list[str]:
    marker = issue_pattern(issue)
    lines = clean_lines(text)
    matches: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(marker, line):
            continue
        if matches_keyword(
            line,
            target.keyword,
        ) and hooks.extract_target_zodiac(line, target):
            matches.append(line)
            continue
        window = " ".join(lines[index : index + 5])
        if not matches_keyword(window, target.keyword):
            continue
        segment = line
        for next_line in lines[index + 1 : index + 5]:
            if re.search(ANY_ISSUE_PATTERN, next_line):
                break
            segment = f"{segment} {next_line}"
            if hooks.extract_target_zodiac(
                segment,
                target,
            ) and re.search(r"[开開]", segment):
                matches.append(segment)
                break
        else:
            if hooks.extract_target_zodiac(segment, target):
                matches.append(segment)
    return list(dict.fromkeys(matches))


def special_ai_public_label_issue_lines(
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
    end_anchor = str(rule.get("section_end", ""))
    if anchor_template and end_anchor:
        lines = clean_lines(text)
        starts = [
            index
            for index, line in enumerate(lines)
            if issue_anchor_matches(line, anchor_template, issue)
        ]
        if not starts:
            return []
        selected = (
            starts
            if all_sections
            else [starts[0] if target.position == "top" else starts[-1]]
        )
        collected: list[str] = []
        for start in selected:
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if end_anchor in lines[index]
                ),
                None,
            )
            if end is None:
                continue
            collected.extend(
                f"{lines[start]} {line}"
                for line in lines[start + 1 : end]
                if target.keyword in line
                and hooks.extract_target_zodiac(line, target)
                and value_line_belongs_to_issue(line, issue)
            )
        return list(dict.fromkeys(collected))
    marker = issue_pattern(issue)
    next_issue_marker = rf"AAAAA级大公开\s*{ANY_ISSUE_PATTERN}"
    lines = clean_lines(text)
    matches: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(marker, line) or "AAAAA级大公开" not in line:
            continue
        for next_line in lines[index + 1 : index + 20]:
            if re.search(next_issue_marker, next_line) and not re.search(
                marker,
                next_line,
            ):
                break
            if target.keyword in next_line and hooks.extract_target_zodiac(
                next_line,
                target,
            ) and value_line_belongs_to_issue(next_line, issue):
                matches.append(f"{line} {next_line}")
    return list(dict.fromkeys(matches))


def special_nearest_keyword_line_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    hooks: ParserHooks,
) -> list[str]:
    marker = issue_pattern(issue)
    return [
        line
        for line in clean_lines(text)
        if re.search(marker, line)
        and matches_keyword(line, target.keyword)
        and has_confirmed_result_structure(line, issue)
        and hooks.extract_target_zodiac(line, target)
    ]


def keyword_header_indexes(
    lines: list[str],
    keyword: str,
    hooks: ParserHooks,
) -> list[int]:
    return [
        index
        for index, line in enumerate(lines)
        if keyword in line
        and any(token in line for token in ("【", "】", "帖", "作者"))
        and not hooks.extract_zodiac(line)
    ]


def has_ambiguous_keyword_headers(
    text: str,
    keyword: str,
    hooks: ParserHooks,
) -> bool:
    if not keyword:
        return False
    return len(keyword_header_indexes(clean_lines(text), keyword, hooks)) > 1


def keyword_header_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
) -> list[str]:
    if not target.keyword:
        return []
    lines = clean_lines(text)
    marker = issue_pattern(issue)
    header_indexes = keyword_header_indexes(lines, target.keyword, hooks)
    if not header_indexes:
        return []
    matching_indexes = target_identity_header_indexes(
        lines,
        header_indexes,
        target,
        rules,
    )
    if matching_indexes:
        selected_indexes = matching_indexes
    else:
        return []
    for index in selected_indexes:
        position = header_indexes.index(index)
        end = (
            header_indexes[position + 1]
            if position + 1 < len(header_indexes)
            else len(lines)
        )
        matches = [
            item
            for item in lines[index:end]
            if re.search(marker, item) and hooks.extract_zodiac(item)
        ]
        if matches:
            return matches
    return []
