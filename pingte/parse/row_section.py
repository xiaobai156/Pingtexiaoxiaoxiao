from __future__ import annotations

import re

from pingte.domain.models import TargetProfile

from .context import (
    ANY_ISSUE_PATTERN,
    ParserHooks,
    RuleBook,
    clean_lines,
    issue_anchor_matches,
    issue_pattern,
    selected_section_starts,
    value_line_belongs_to_issue,
)

RESULT_STATUS_PATTERN = r"(?:准|中|错|√|✓|×|x|X)"


def _matches_anchor(line: str, template: str, *, exact: bool) -> bool:
    if exact:
        return line == template
    return bool(template and issue_anchor_matches(line, template, "0"))


def _row_result_zodiac(row: str, hooks: ParserHooks) -> str | None:
    parts = re.split(r"[开開]", row, maxsplit=1)
    if len(parts) != 2:
        return None
    result_field = parts[1]
    if not re.search(RESULT_STATUS_PATTERN, result_field):
        return None
    zodiac = hooks.dedupe_zodiac(hooks.zodiac_chars(result_field))
    return zodiac if len(zodiac) == 1 else None


def _row_phrase_zodiac(row: str, hooks: ParserHooks) -> str | None:
    parts = re.split(r"[开開]", row, maxsplit=1)
    if len(parts) != 2 or not re.search(RESULT_STATUS_PATTERN, parts[1]):
        return None
    bracket_parts = re.findall(r"[【『\[(（](.*?)[】』\])）]", parts[0])
    zodiac = hooks.dedupe_zodiac(
        hooks.zodiac_chars(" ".join(bracket_parts))
    )
    return zodiac if 1 <= len(zodiac) <= 2 else None


def row_section_issue_lines(
    text: str,
    target: TargetProfile,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
    *,
    all_sections: bool = False,
) -> list[str]:
    """Parse flex/table rows whose cells become separate DOM text lines.

    The parser is deliberately bound to explicit section anchors. A row is
    valid only when its issue, configured keyword, and confirmed result field
    remain in the same bounded row. Zodiac characters in the descriptive
    phrase are never used as a substitute for the ``开`` result field.
    """

    rule = rules.rule_for(target)
    anchor = str(rule.get("section_anchor", "")).strip()
    end_anchor = str(rule.get("section_end", "")).strip()
    line_keyword = str(rule.get("line_keyword", target.keyword)).strip()
    if not anchor or not end_anchor:
        return []

    lines = clean_lines(text)
    starts = [
        index
        for index, line in enumerate(lines)
        if _matches_anchor(
            line,
            anchor,
            exact=bool(rule.get("section_anchor_exact")),
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
                if _matches_anchor(
                    lines[index],
                    end_anchor,
                    exact=bool(rule.get("section_end_exact")),
                )
            ),
            None,
        )
        if end is None:
            continue

        rows: list[list[str]] = []
        current: list[str] = []
        for line in lines[start + 1 : end]:
            if re.search(ANY_ISSUE_PATTERN, line):
                if current:
                    rows.append(current)
                current = [line]
                if re.search(r"[开開]", line):
                    rows.append(current)
                    current = []
            elif current:
                current.append(line)
                if re.search(r"[开開]", line):
                    rows.append(current)
                    current = []
        if current:
            rows.append(current)

        matches: list[str] = []
        for row_lines in rows:
            row = " ".join(row_lines)
            if not re.search(marker, row):
                continue
            if not value_line_belongs_to_issue(row, issue):
                continue
            if line_keyword and line_keyword not in row:
                continue
            opened = _row_result_zodiac(row, hooks)
            if rule.get("row_zodiac_source") == "phrase_or_open":
                phrase = _row_phrase_zodiac(row, hooks)
                if phrase and opened and phrase != opened:
                    matches.extend(
                        (row, f"{int(issue)}期 {line_keyword}【{opened}】开{opened}准")
                    )
                elif phrase or opened:
                    matches.append(row)
                continue
            if opened is None:
                continue
            matches.append(row)

        if all_sections:
            collected.extend(matches)
        else:
            return matches
    return list(dict.fromkeys(collected))
