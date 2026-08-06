from __future__ import annotations

import re

from pingte.domain.models import Target
from pingte.parse.context import (
    ANY_ISSUE_PATTERN,
    ParserHooks,
    RuleBook,
    clean_lines,
    has_confirmed_result_structure,
    issue_anchor_matches,
    is_section_boundary,
    selected_section_starts,
)
from pingte.parse.formula_section import formula_section_zodiac
from pingte.validation.issue import extract_target_zodiac, issue_pattern


def unavailable_reason(text: str) -> str | None:
    if "此帖子ID已被下架" in text:
        return "帖子ID已被下架，页面没有可解析数据"
    return None


def auxiliary_failure_reason(text: str) -> str | None:
    failures = re.findall(r"\[\[附属资源失败:(.*?)\]\]", text)
    if not failures:
        return None
    return "附属资源抓取失败：" + "；".join(failures)


def pending_issue_reason(
    text: str,
    target: Target,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
) -> str | None:
    marker = issue_pattern(issue)
    lines = clean_lines(text)
    mode = rules.mode_for(target)
    if mode == "anchored_section":
        rule = rules.rule_for(target)
        anchor_template = str(rule.get("section_anchor", ""))
        end_anchor_template = str(rule.get("section_end", ""))
        anchor = anchor_template.replace("{issue}", str(int(issue)))
        end_anchor = end_anchor_template.replace("{issue}", str(int(issue)))
        starts = [
            index
            for index, line in enumerate(lines)
            if anchor
            and (
                line == anchor
                if rule.get("section_anchor_exact")
                else issue_anchor_matches(line, anchor_template, issue)
            )
        ]
        if not starts or not end_anchor:
            return None
        for start in selected_section_starts(starts, target, rule):
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if (
                        lines[index] == end_anchor
                        if rule.get("section_end_exact")
                        else issue_anchor_matches(
                            lines[index], end_anchor_template, issue
                        )
                    )
                ),
                None,
            )
            if end is not None and any(re.search(marker, line) for line in lines[start:end]):
                from pingte.parse.anchored_section import anchored_section_issue_lines

                if anchored_section_issue_lines(text, target, issue, rules, hooks):
                    return None
                return "指定期数页面已出现，但该期生肖内容尚未更新"
        return None
    if mode == "anchored_formula_section":
        rule = rules.rule_for(target)
        anchor = str(rule.get("section_anchor", ""))
        end_anchor = str(rule.get("section_end", ""))
        starts = [index for index, line in enumerate(lines) if anchor and anchor in line]
        if starts and end_anchor:
            start = starts[0] if target.position == "top" else starts[-1]
            end = next(
                (index for index in range(start + 1, len(lines)) if end_anchor in lines[index]),
                len(lines),
            )
            section = lines[start:end]
            if any(re.search(marker, line) for line in section) and not any(
                formula_section_zodiac(line, issue, bool(rule.get("allow_question_summary")))
                for line in section
            ):
                return "指定期数页面已出现，但该期生肖内容尚未更新"
    for index, line in enumerate(lines):
        if not re.search(marker, line):
            continue
        section: list[str] = []
        for item in lines[index : index + 8]:
            if section and re.search(ANY_ISSUE_PATTERN, item) and not re.search(marker, item):
                break
            section.append(item)
        window = " ".join(section)
        if (target.keyword and target.keyword in window) or target.name in window:
            if not any(extract_target_zodiac(item, target, rules.rule_for(target)) for item in section):
                return "指定期数页面已出现，但该期生肖内容尚未更新"
    return None


def missing_target_issue_reason(
    text: str,
    target: Target,
    issue: str,
    rules: RuleBook,
    hooks: ParserHooks,
) -> str | None:
    lines = clean_lines(text)
    mode = rules.mode_for(target)
    if mode == "named_section":
        rule = rules.rule_for(target)
        section_name = str(rule.get("section_name", target.name)).strip()
        indexes = [index for index, line in enumerate(lines) if section_name and section_name in line]
        if not indexes:
            return None
        grouped = [indexes[0]]
        for index in indexes[1:]:
            previous = grouped[-1]
            if any(re.search(ANY_ISSUE_PATTERN, line) for line in lines[previous + 1 : index]):
                grouped.append(index)
        start = grouped[0] if target.position == "top" else grouped[-1]
        end = next((index for index in grouped if index > start), len(lines))
        scoped: list[str] = []
        seen_issue = False
        for local_index, line in enumerate(lines[start:end]):
            if is_section_boundary(line, target, lines[start]) and not (
                not seen_issue and any(token in line for token in ("发表于", "作者：", "作者:"))
            ):
                break
            scoped.append(line)
            if re.search(ANY_ISSUE_PATTERN, line) and (
                local_index > 0 or has_confirmed_result_structure(line)
            ):
                seen_issue = True
        return _missing_message(scoped, issue)

    if mode == "anchored_section":
        rule = rules.rule_for(target)
        anchor_template = str(rule.get("section_anchor", ""))
        end_anchor_template = str(rule.get("section_end", ""))
        anchor = anchor_template.replace("{issue}", str(int(issue)))
        end_anchor = end_anchor_template.replace("{issue}", str(int(issue)))
        start = next(
            (
                index
                for index, line in enumerate(lines)
                if anchor and issue_anchor_matches(line, anchor_template, issue)
            ),
            None,
        )
        if start is None:
            return None
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if end_anchor
                and issue_anchor_matches(lines[index], end_anchor_template, issue)
            ),
            None,
        )
        if end is None:
            return None
        return _missing_message(lines[start:end], issue)

    indexes = [index for index, line in enumerate(lines) if target.name in line]
    if not indexes:
        return None
    scoped = []
    for index in indexes:
        scoped.extend(lines[index : index + 10])
    scoped.extend(line for line in lines if target.keyword and target.keyword in line)
    return _missing_message(list(dict.fromkeys(scoped)), issue)


def _missing_message(lines: list[str], issue: str) -> str | None:
    scoped_text = "\n".join(lines)
    if re.search(issue_pattern(issue), scoped_text):
        return None
    available: list[str] = []
    for match in re.finditer(r"(?<!\d)(\d{1,3})(?!\d)\s*期", scoped_text):
        value = str(int(match.group(1)))
        if value not in available:
            available.append(value)
    if not available:
        return None
    visible = "、".join(f"{value}期" for value in available[:5])
    return f"目标目录/栏目存在，但页面没有指定的{int(issue)}期；当前可见期数：{visible}"
