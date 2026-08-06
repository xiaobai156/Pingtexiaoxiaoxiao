from __future__ import annotations

from collections.abc import Iterable

from pingte.domain.models import Candidate


def distinct_zodiacs(candidates: Iterable[Candidate]) -> list[str]:
    return list(dict.fromkeys(candidate.zodiac for candidate in candidates))


def has_document_conflict(groups: Iterable[Iterable[Candidate]]) -> bool:
    nonempty = [list(group) for group in groups if list(group)]
    return len(nonempty) > 1
