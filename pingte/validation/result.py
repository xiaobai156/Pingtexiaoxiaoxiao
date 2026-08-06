from __future__ import annotations

import re
from dataclasses import dataclass

from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.models import Candidate, SourceDocument, Target, ValidatedResult
from pingte.fetch.documents import deserialize_source_documents
from pingte.parse.registry import DedicatedParserRegistry
from pingte.parse.context import (
    ANY_ISSUE_PATTERN,
    clean_lines,
    issue_anchor_matches,
)

from .conflict import distinct_zodiacs
from .issue import extract_target_zodiac, issue_pattern


@dataclass(frozen=True)
class ValidationOutcome:
    zodiac: str | None = None
    candidate: Candidate | None = None
    result: ValidatedResult | None = None
    failure: FailureDetail | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None and self.failure is None


def _failure(
    code: FailureCode,
    message: str,
    target: Target,
    issue: str,
    *,
    zodiac: str | None = None,
    matched_line: str = "",
    visible_issues: tuple[str, ...] = (),
) -> ValidationOutcome:
    return ValidationOutcome(
        zodiac=zodiac,
        failure=FailureDetail(
            code=code,
            message=message,
            target_id=target.target_id,
            name=target.name,
            url=target.url,
            position=target.position,
            keyword=target.keyword,
            issue=str(int(issue)),
            matched_line=matched_line,
            visible_issues=visible_issues,
        )
    )


def _document_mentions_target_issue(
    document: SourceDocument,
    target: Target,
    issue: str,
) -> bool:
    if not re.search(issue_pattern(issue), document.text):
        return False
    return bool(
        (target.keyword and target.keyword in document.text)
        or (target.name and target.name in document.text)
    )


def _visible_issue_keys(text: str) -> list[str]:
    issues: list[str] = []
    for match in re.finditer(ANY_ISSUE_PATTERN, text):
        value = str(int(match.group(0).replace("期", "").strip()))
        if value not in issues:
            issues.append(value)
    return issues


def _line_index(lines: list[str], raw_line: str, start: int = 0) -> int:
    for index in range(max(0, start), len(lines)):
        line = lines[index]
        if raw_line == line:
            return index
    for index in range(max(0, start), len(lines)):
        line = lines[index]
        if raw_line in line or line in raw_line:
            return index
    return -1


def _rule_anchor(rule: dict, target: Target, issue: str) -> str:
    anchor = str(rule.get("section_anchor", "")).strip()
    if anchor:
        return anchor.replace("{issue}", str(int(issue)))
    return target.name or target.keyword


def _raw_zodiac_order(
    line: str,
    target: Target,
    rule: dict,
    registry: DedicatedParserRegistry,
) -> str:
    sanitized = line
    for identity in (target.name, str(rule.get("section_name", ""))):
        if identity:
            sanitized = sanitized.replace(identity, "")
    before_open = re.split(r"[开開]", sanitized, maxsplit=1)[0]
    bracket_parts = re.findall(r"[【『\[(（](.*?)[】』\])）]", before_open)
    for part in bracket_parts:
        value = registry.hooks.zodiac_chars(part)
        if value:
            return value
    equals_parts = re.findall(r"[=＝]\s*([^\s=＝]+)", line)
    if equals_parts:
        value = registry.hooks.zodiac_chars(equals_parts[-1])
        if value:
            return value
    return registry.hooks.zodiac_chars(before_open)


def _candidate_context(
    document: SourceDocument,
    target: Target,
    rule: dict,
    issue: str,
    raw_line: str,
    lines: list[str],
    block_index: int,
    line_search_start: int = 0,
) -> dict[str, object]:
    anchor = _rule_anchor(rule, target, issue)
    anchor_template = str(rule.get("section_anchor", ""))
    candidate_index = _line_index(lines, raw_line, line_search_start)
    # Some dedicated parsers intentionally return a compact follow-up label
    # without repeating the issue number. Bind those candidates to their
    # exact issue anchor instead of locating identical labels globally.
    if anchor and not re.search(issue_pattern(issue), raw_line):
        anchored_index = next(
            (
                index
                for index, line in enumerate(lines)
                if issue_anchor_matches(line, str(rule.get("section_anchor", "")), issue)
            ),
            -1,
        )
        if anchored_index >= 0:
            candidate_index = anchored_index
    if candidate_index < 0:
        candidate_index = 0
    anchor_index = -1
    if anchor:
        anchor_index = next(
            (
                index
                for index in range(candidate_index, -1, -1)
                if issue_anchor_matches(lines[index], anchor_template, issue)
            ),
            -1,
        )
    if anchor_index < 0:
        anchor_index = next(
            (
                index
                for index in range(candidate_index, -1, -1)
                if target.name and target.name in lines[index]
            ),
            -1,
        )
    if anchor_index < 0:
        anchor_index = candidate_index
    end_anchor_template = str(rule.get("section_end", ""))
    end_anchor = end_anchor_template.replace("{issue}", str(int(issue)))
    block_end = next(
        (
            index
            for index in range(anchor_index + 1, len(lines))
            if end_anchor
            and issue_anchor_matches(lines[index], end_anchor_template, issue)
        ),
        len(lines) - 1,
    )
    actual_anchor = lines[anchor_index] if lines else ""
    block_id = f"{document.source}:{anchor_index}:{block_end}"
    return {
        "anchor_line": actual_anchor,
        "block_id": block_id,
        "block_start": anchor_index,
        "block_end": block_end,
        "page_index": candidate_index,
        "block_index": block_index,
        "candidate_index": candidate_index,
        "parser_rule_id": target.target_id,
        "direction": target.position,
    }


def _document_candidates(
    document: SourceDocument,
    target: Target,
    issue: str,
    registry: DedicatedParserRegistry,
    *,
    all_blocks: bool = False,
) -> list[Candidate]:
    lines = (
        registry.parse_issue_lines_all(document.text, target, issue)
        if all_blocks
        else registry.parse_issue_lines(document.text, target, issue)
    )
    rule = registry.rules.rule_for(target)
    source_lines = clean_lines(document.text)
    candidates: list[Candidate] = []
    line_search_start = 0
    for block_index, line in enumerate(lines):
        # The follow-up-label parser already binds the label to the exact
        # issue header while returning the compact label line itself.
        issue_bound_by_parser = rule.get("mode") == "followup_label"
        if not issue_bound_by_parser and not re.search(issue_pattern(issue), line):
            continue
        zodiac = extract_target_zodiac(line, target, rule)
        if not zodiac:
            continue
        context = _candidate_context(
            document,
            target,
            rule,
            issue,
            line,
            source_lines,
            block_index,
            line_search_start,
        )
        candidate_index = int(context["candidate_index"])
        if candidate_index >= 0:
            line_search_start = candidate_index + 1
        context["raw_zodiac_order"] = _raw_zodiac_order(
            line,
            target,
            rule,
            registry,
        )
        candidates.append(
            Candidate(
                target_id=target.target_id,
                issue=str(int(issue)),
                zodiac=zodiac,
                raw_line=line,
                source=document.source,
                source_url=document.source_url,
                section_start=str(rule.get("section_anchor", "")),
                section_end=str(rule.get("section_end", "")),
                **context,
            )
        )
    return candidates


def _document_candidate_map(
    document: SourceDocument,
    target: Target,
    registry: DedicatedParserRegistry,
) -> dict[str, list[Candidate]]:
    candidates_by_issue: dict[str, list[Candidate]] = {}
    for issue in _visible_issue_keys(document.text):
        candidates = _document_candidates(
            document,
            target,
            issue,
            registry,
            all_blocks=True,
        )
        if candidates:
            candidates_by_issue[issue] = candidates
    return candidates_by_issue


def _direction_window(
    candidates_by_issue: dict[str, list[Candidate]],
    target: Target,
    window_size: int = 3,
) -> tuple[str, ...]:
    ordered = sorted(
        (
            min(
                candidate.candidate_index
                for candidate in candidates
                if candidate.candidate_index >= 0
            )
            if any(candidate.candidate_index >= 0 for candidate in candidates)
            else index,
            issue,
        )
        for index, (issue, candidates) in enumerate(candidates_by_issue.items())
    )
    selected = ordered[:window_size] if target.position == "top" else ordered[-window_size:]
    return tuple(issue for _index, issue in selected)


def _has_target_anchor(
    document: SourceDocument,
    target: Target,
    registry: DedicatedParserRegistry,
) -> bool:
    rule = registry.rules.rule_for(target)
    if rule.get("source_strategy") == "dynamic_record":
        return True
    identities = {
        target.name,
        str(rule.get("section_name", "")).strip(),
    }
    return any(identity and identity in document.text for identity in identities)


def _choose_document_candidates(
    document: SourceDocument,
    candidates: list[Candidate],
    target: Target,
    issue: str,
) -> ValidationOutcome | list[Candidate]:
    if not candidates:
        return []
    zodiacs = distinct_zodiacs(candidates)
    if len(zodiacs) > 1:
        return _failure(
            FailureCode.AMBIGUOUS_CANDIDATES,
            f"同一目标文档出现不同生肖候选：{'、'.join(zodiacs)}",
            target,
            issue,
            matched_line="；".join(candidate.raw_line for candidate in candidates),
        )
    return candidates


def _finish(
    target: Target,
    document: SourceDocument,
    candidates: list[Candidate],
    issue: str,
) -> ValidationOutcome:
    candidate = candidates[0] if target.position == "top" else candidates[-1]
    zodiac = candidate.zodiac
    if len(zodiac) > 2:
        return _failure(
            FailureCode.TOO_MANY_ZODIACS,
            f"抓到的生肖超过2个，按规则丢失败，生肖：{zodiac}",
            target,
            issue,
            zodiac=zodiac,
            matched_line=candidate.raw_line,
        )
    return ValidationOutcome(
        zodiac=zodiac,
        candidate=candidate,
        result=ValidatedResult(target, str(int(issue)), candidate, document),
    )


def validate_documents(
    target: Target,
    issue: str,
    serialized_text: str,
    registry: DedicatedParserRegistry,
) -> ValidationOutcome:
    normalized_issue = str(int(issue))
    documents = deserialize_source_documents(serialized_text)
    if not documents:
        return _failure(FailureCode.EMPTY_DOCUMENT, "页面为空", target, normalized_issue)
    if not registry.rules.has_dedicated_parser(target):
        return _failure(
            FailureCode.RULE_MISSING,
            "未配置站点级专属解析规则",
            target,
            normalized_issue,
        )

    primary_documents = [document for document in documents if document.primary]
    primary_groups: list[tuple[SourceDocument, list[Candidate]]] = []
    primary_incomplete: list[SourceDocument] = []
    for document in primary_documents:
        candidate_map = _document_candidate_map(document, target, registry)
        requested_candidates = candidate_map.get(normalized_issue, [])
        window = _direction_window(candidate_map, target)
        if candidate_map and normalized_issue not in window:
            return _failure(
                FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW,
                f"指定期数不在{target.position}方向最近3组有效候选内",
                target,
                normalized_issue,
                visible_issues=window,
            )
        chosen = _choose_document_candidates(
            document,
            requested_candidates,
            target,
            normalized_issue,
        )
        if isinstance(chosen, ValidationOutcome):
            return chosen
        if chosen:
            primary_groups.append((document, chosen))
        elif _document_mentions_target_issue(document, target, normalized_issue):
            primary_incomplete.append(document)

    if primary_incomplete:
        if any(not _has_target_anchor(document, target, registry) for document in primary_incomplete):
            return _failure(
                FailureCode.ANCHOR_MISSING,
                "指定目录或栏目锚点未找到，禁止仅凭关键字取值",
                target,
                normalized_issue,
            )
        return _failure(
            FailureCode.ZODIAC_MISSING,
            "没有在指定期数、指定关键字/目录区域里解析到生肖",
            target,
            normalized_issue,
        )

    if len(primary_groups) > 1:
        values = list(
            dict.fromkeys(
                candidate.zodiac
                for _document, candidates in primary_groups
                for candidate in candidates
            )
        )
        return _failure(
            FailureCode.SOURCE_CONFLICT,
            f"多个权威文档同时匹配目标，文档边界不明确：{'、'.join(values)}",
            target,
            normalized_issue,
        )
    if primary_groups:
        document, candidates = primary_groups[0]
        return _finish(target, document, candidates, normalized_issue)

    if any(
        _document_mentions_target_issue(document, target, normalized_issue)
        for document in primary_documents
    ):
        return _failure(
            FailureCode.ZODIAC_MISSING,
            "没有在指定期数、指定关键字/目录区域里解析到生肖",
            target,
            normalized_issue,
        )

    embedded_groups: list[tuple[SourceDocument, list[Candidate]]] = []
    embedded_incomplete: list[SourceDocument] = []
    embedded_out_windows: list[tuple[str, ...]] = []
    for document in documents:
        if document.primary or document.source == "diagnostic":
            continue
        candidate_map = _document_candidate_map(document, target, registry)
        requested_candidates = candidate_map.get(normalized_issue, [])
        window = _direction_window(candidate_map, target)
        if candidate_map and normalized_issue not in window:
            embedded_out_windows.append(window)
            continue
        chosen = _choose_document_candidates(
            document,
            requested_candidates,
            target,
            normalized_issue,
        )
        if isinstance(chosen, ValidationOutcome):
            return chosen
        if chosen:
            embedded_groups.append((document, chosen))
        elif _document_mentions_target_issue(document, target, normalized_issue):
            embedded_incomplete.append(document)
    if embedded_incomplete and embedded_groups:
        return _failure(
            FailureCode.BLOCK_AMBIGUOUS,
            "多个附属文档同时包含目标期，但至少一个目标区块无法完整解析",
            target,
            normalized_issue,
        )
    if embedded_out_windows:
        return _failure(
            FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW,
            f"指定期数不在{target.position}方向最近3组有效候选内",
            target,
            normalized_issue,
            visible_issues=embedded_out_windows[0],
        )
    if len(embedded_groups) > 1:
        values = list(
            dict.fromkeys(
                candidate.zodiac
                for _document, candidates in embedded_groups
                for candidate in candidates
            )
        )
        return _failure(
            FailureCode.SOURCE_CONFLICT,
            f"跨文档出现多个目标候选：{'、'.join(values)}",
            target,
            normalized_issue,
        )
    if embedded_groups:
        document, candidates = embedded_groups[0]
        return _finish(target, document, candidates, normalized_issue)

    if not any(target.keyword in document.text for document in documents if target.keyword):
        return _failure(FailureCode.KEYWORD_MISSING, "指定关键字未找到", target, normalized_issue)
    if not any(re.search(issue_pattern(normalized_issue), document.text) for document in documents):
        visible = tuple(
            sorted(
                {
                    match.group(1)
                    for document in documents
                    for match in re.finditer(r"(?<!\d)(\d{1,3})(?!\d)\s*期", document.text)
                },
                key=int,
                reverse=True,
            )[:5]
        )
        return _failure(
            FailureCode.ISSUE_MISSING,
            f"目标目录/栏目存在，但页面没有指定的{int(normalized_issue)}期",
            target,
            normalized_issue,
            visible_issues=visible,
        )
    return _failure(
        FailureCode.ZODIAC_MISSING,
        "没有在指定期数、指定关键字/目录区域里解析到生肖",
        target,
        normalized_issue,
    )
