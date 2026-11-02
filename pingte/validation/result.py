from __future__ import annotations

import re
from dataclasses import dataclass

from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.models import Candidate, SourceDocument, Target, ValidatedResult
from pingte.fetch.documents import deserialize_source_documents
from pingte.parse.context import (
    ANY_ISSUE_PATTERN,
    clean_lines,
    issue_anchor_matches,
    issue_pattern_for_rule,
)
from pingte.parse.registry import DedicatedParserRegistry

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


_PERIOD_TOKEN_RE = re.compile(r"(?<!\d)(\d{1,3})(?:\s*[-－~]\s*(\d{1,3}))?(?!\d)\s*期")


def _period_tokens(line: str) -> list[tuple[int, int]]:
    """行内每个期号标记 -> (起, 止)；区间写法 289-291期 记为 (289, 291)。"""
    tokens: list[tuple[int, int]] = []
    for match in _PERIOD_TOKEN_RE.finditer(line):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        tokens.append((min(start, end), max(start, end)))
    return tokens


def _line_belongs_to_issue(line: str, issue: str) -> bool:
    """该行是否是「指定期」自己的数据行。

    阻止两类跨期借值：
      1. 行内期号只做「包含」判断 —— ``297期 … 下期298期预告`` 不能算 298 期；
      2. 一行里混入别的期号 —— ``AAAAA级大公开298期 297期 平特一肖：鼠`` 里
         的鼠属于 297 期。
    没有期号的行（专属解析器已绑定期号）放行。
    """
    tokens = _period_tokens(line)
    if not tokens:
        return True
    target = int(issue)
    for start, end in tokens:
        if not (start <= target <= end):
            return False
    return True


_PERIOD_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,3})(?!\d)\s*期")


def _issue_sequence(lines: list[str], start: int, end: int) -> list[int]:
    sequence: list[int] = []
    for line in lines[max(0, start) : end + 1]:
        match = _PERIOD_NUMBER_RE.search(line)
        if match:
            sequence.append(int(match.group(1)))
    return sequence


def _wrap_step(previous: int, value: int, step: int) -> int:
    """跨年回绕归一：365→001 与 001→365 都算「换年继续」，不改变当前方向。

    页面常把上一轮 353→365 与本轮 001→299 连成一串：365→001 是换年，
    在递增序列里它应该继续递增（+1），在递减序列里应该继续递减（-1）。
    这里返回 0 表示「不改变方向」，由调用方沿用已有方向。
    """
    if previous >= 300 and value <= 2:
        return 0
    if previous <= 2 and value >= 300:
        return 0
    return step


def _direction_break(sequence: list[int]) -> bool:
    """期号序列中途反向 → 已进入上一轮或另一栏目，禁止继续取值。

    跨年回绕（365→001 / 001→365）不算反向。
    """
    if len(sequence) < 3:
        return False
    direction = 0
    previous = sequence[0]
    for value in sequence[1:]:
        if value == previous:
            continue
        step = _wrap_step(previous, value, value - previous)
        previous = value
        if step == 0:
            # 跨年回绕：沿用当前方向，不参与反向判定。
            continue
        if direction == 0:
            direction = 1 if step > 0 else -1
            continue
        if (step > 0) != (direction > 0):
            return True
    return False


def _monotonic_segments(ordered: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """把按页面顺序排列的候选期号切成单调段。

    同页可能同时存在本轮列表和上一轮/另一栏目的列表，期号会在中途反向。
    切段后窗口只在段内计算，避免同号数据跨轮次借入。

    升序列表（250→251→252…）本身是合法的，只有**反向**才切；
    365→001 与 001→365 的跨年回绕不算反向。
    """
    segments: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    direction = 0
    previous: int | None = None
    for item in ordered:
        value = int(item[1])
        if previous is not None and value != previous:
            step = _wrap_step(previous, value, value - previous)
            if step == 0:
                # 跨年回绕：沿用当前方向，不切段。
                current.append(item)
                previous = value
                continue
            if direction == 0:
                direction = 1 if step > 0 else -1
            elif (step > 0) != (direction > 0):
                if current:
                    segments.append(current)
                current = []
                direction = 1 if step > 0 else -1
        current.append(item)
        previous = value
    if current:
        segments.append(current)
    return segments


def _pick_window_segment(
    ordered: list[tuple[int, str]],
    issue: str,
    position: str = "top",
) -> list[tuple[int, str]]:
    """选出包含指定期的那个单调段，作为方向窗口的取值范围。

    指定期自己所在的段才是本轮的权威列表；其它段（上一轮、别的栏目）不参与窗口。
    同号出现在多段时按方向语义取：
      * tail → 取**最后**一段（页面末尾那段才是本期最新发布的数据）；
      * top  → 取**第一**段。
    若指定期不在任何段里（该站没有发布本期），退回原整体顺序，交由窗口判失败。
    """
    segments = _monotonic_segments(ordered)
    if len(segments) <= 1:
        return ordered
    target = int(issue)
    matched = [
        segment
        for segment in segments
        if any(int(value) == target for _index, value in segment)
    ]
    if not matched:
        return ordered
    return matched[0] if position == "top" else matched[-1]


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


def _row_section_candidate_index(
    lines: list[str],
    target: Target,
    rule: dict,
    issue: str,
    start: int,
) -> int:
    anchor = str(rule.get("section_anchor", "")).strip()
    end_anchor = str(rule.get("section_end", "")).strip()
    if not anchor or not end_anchor:
        return -1
    starts = [
        index
        for index, line in enumerate(lines)
        if (
            line == anchor
            if rule.get("section_anchor_exact")
            else issue_anchor_matches(line, anchor, issue)
        )
    ]
    marker = issue_pattern_for_rule(issue, rule)
    for section_start in starts:
        section_end = next(
            (
                index
                for index in range(section_start + 1, len(lines))
                if (
                    lines[index] == end_anchor
                    if rule.get("section_end_exact")
                    else issue_anchor_matches(lines[index], end_anchor, issue)
                )
            ),
            len(lines),
        )
        for index in range(max(start, section_start + 1), section_end):
            if re.search(marker, lines[index]):
                return index
    return -1


def _rule_anchor(rule: dict, target: Target, issue: str) -> str:
    anchor = str(rule.get("section_anchor", "")).strip()
    if anchor:
        return anchor.replace("{issue}", str(int(issue)))
    section_name = str(rule.get("section_name", "")).strip()
    if section_name:
        return section_name
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
    if rule.get("mode") == "row_section":
        candidate_index = _row_section_candidate_index(
            lines,
            target,
            rule,
            issue,
            line_search_start,
        )
    else:
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
    candidate_index = max(candidate_index, 0)
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
        identities = (
            str(rule.get("section_name", "")).strip(),
            target.name,
        )
        anchor_index = next(
            (
                index
                for index in range(candidate_index, -1, -1)
                if any(identity and identity in lines[index] for identity in identities)
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
    # 区块内期号反向（进入上一轮或另一栏目）时，把区块截断到反向点之前，
    # 避免同号数据从别的轮次/栏目借入。
    # 注意：区块首行常是带期号的标题（如「299期:某站【平特一肖】独家公式」），
    # 它不是数据行，不能拿它当方向基准，否则会把整段真实数据误判成反向。
    data_start = anchor_index + 1
    block_sequence = _issue_sequence(lines, data_start, block_end)
    if _direction_break(block_sequence):
        cut = data_start
        direction = 0
        previous: int | None = None
        break_at: int | None = None
        for index in range(data_start, block_end + 1):
            match = _PERIOD_NUMBER_RE.search(lines[index])
            if not match:
                continue
            value = int(match.group(1))
            if previous is not None and value != previous:
                step = _wrap_step(previous, value, value - previous)
                if step == 0:
                    # 跨年回绕：沿用当前方向，不截断。
                    previous = value
                    cut = index
                    continue
                if direction == 0:
                    direction = 1 if step > 0 else -1
                elif (step > 0) != (direction > 0):
                    break_at = index
                    break
            previous = value
            cut = index
        block_end = max(cut, anchor_index)
        if break_at is not None and candidate_index < break_at:
            block_end = max(block_end, candidate_index)
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
        if not issue_bound_by_parser and not re.search(
            issue_pattern_for_rule(issue, rule),
            line,
        ):
            continue
        # 行内期号归属校验：阻止「297期…下期298期预告」或一行混两个期号时借值。
        if not _line_belongs_to_issue(line, issue):
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
        # 候选必须落在自己所属的权威区块内。区块外（别的轮次/栏目）的同号
        # 数据行即使期号匹配也不能当本期结果，否则 tail 窗口会把旧轮同号借进来。
        block_start = int(context["block_start"])
        block_end = int(context["block_end"])
        if block_start >= 0 and not (block_start <= candidate_index <= block_end):
            continue
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
    rule = registry.rules.rule_for(target)
    occurrence = str(rule.get("issue_occurrence", "")).strip()
    candidates_by_issue: dict[str, list[Candidate]] = {}
    for issue in _visible_issue_keys(document.text):
        candidates = _document_candidates(
            document,
            target,
            issue,
            registry,
            all_blocks=True,
        )
        if occurrence in {"first", "last"} and candidates:
            indexes = [
                candidate.candidate_index
                for candidate in candidates
                if candidate.candidate_index >= 0
            ]
            if indexes:
                wanted = min(indexes) if occurrence == "first" else max(indexes)
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.candidate_index == wanted
                ]
        if candidates:
            candidates_by_issue[issue] = candidates
    return candidates_by_issue


def _direction_window(
    candidates_by_issue: dict[str, list[Candidate]],
    target: Target,
    window_size: int = 3,
    issue: str | None = None,
) -> tuple[str, ...]:
    # 同一期号可能有多个候选（页面多处重复展示）。方向语义决定取哪个位置：
    #   top  → 该期第一次出现的位置；
    #   tail → 该期最后一次出现的位置。
    # 用错位置会让排序失真（例如升序列表里 299 首现在中部、尾现在末尾）。
    use_max = target.position != "top"
    ordered = sorted(
        (
            (
                max(candidate.candidate_index for candidate in candidates)
                if use_max
                else min(candidate.candidate_index for candidate in candidates)
            )
            if any(candidate.candidate_index >= 0 for candidate in candidates)
            else index,
            issue,
        )
        for index, (issue, candidates) in enumerate(candidates_by_issue.items())
    )
    # 只在「指定期所属的那一段」里建窗口，避免旧轮次/别栏目的同号借入。
    scope = (
        _pick_window_segment(ordered, issue, target.position) if issue else ordered
    )
    selected = (
        scope[:window_size] if target.position == "top" else scope[-window_size:]
    )
    return tuple(item[1] for item in selected)


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
    rule = registry.rules.rule_for(target)
    if rule.get("source_strategy") == "external_script":
        documents = [
            document
            for document in documents
            if document.source == "diagnostic"
            or (
                document.source == "external-script"
                and document.document_id == target.target_id
            )
        ]

    primary_documents = [document for document in documents if document.primary]
    primary_groups: list[tuple[SourceDocument, list[Candidate]]] = []
    primary_incomplete: list[SourceDocument] = []
    for document in primary_documents:
        candidate_map = _document_candidate_map(document, target, registry)
        requested_candidates = candidate_map.get(normalized_issue, [])
        window = _direction_window(candidate_map, target, issue=normalized_issue)
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
        window = _direction_window(candidate_map, target, issue=normalized_issue)
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
