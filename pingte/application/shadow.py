from dataclasses import dataclass
from typing import Any, Callable, Iterable


Parser = Callable[[Any, str, str], Any]


@dataclass(frozen=True)
class ShadowCase:
    case_id: str
    target: Any
    issue: str
    document: str


@dataclass(frozen=True)
class ShadowDifference:
    case_id: str
    issue: str
    legacy_result: Any
    candidate_result: Any


def compare_parsers(
    cases: Iterable[ShadowCase],
    legacy_parser: Parser,
    candidate_parser: Parser,
) -> list[ShadowDifference]:
    differences: list[ShadowDifference] = []
    for case in cases:
        legacy_result = legacy_parser(case.target, case.issue, case.document)
        candidate_result = candidate_parser(case.target, case.issue, case.document)
        if legacy_result != candidate_result:
            differences.append(
                ShadowDifference(
                    case_id=case.case_id,
                    issue=case.issue,
                    legacy_result=legacy_result,
                    candidate_result=candidate_result,
                )
            )
    return differences
