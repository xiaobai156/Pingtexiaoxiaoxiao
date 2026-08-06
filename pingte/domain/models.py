from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .failures import FailureDetail


@dataclass(frozen=True, eq=False)
class TargetProfile:
    url: str
    position: str
    name: str
    keyword: str = ""
    target_id: str = ""
    rule_version: int = 1

    def _legacy_identity(self) -> tuple[str, str, str, str]:
        return (self.url, self.position, self.name, self.keyword)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TargetProfile):
            return NotImplemented
        return self._legacy_identity() == other._legacy_identity()

    def __hash__(self) -> int:
        return hash(self._legacy_identity())


Target = TargetProfile


@dataclass(frozen=True)
class SourceDocument:
    source: str
    source_url: str
    primary: bool
    text: str
    sha256: str = ""
    fetched_at: str = ""
    document_id: str = ""


@dataclass(frozen=True)
class FetchRequest:
    target: TargetProfile
    issue: str
    timeout: int


@dataclass(frozen=True)
class ParseRequest:
    target: TargetProfile
    issue: str
    documents: tuple[SourceDocument, ...]


@dataclass(frozen=True)
class Candidate:
    target_id: str
    issue: str
    zodiac: str
    raw_line: str
    source: str
    source_url: str
    section_start: str = ""
    section_end: str = ""
    anchor_line: str = ""
    block_id: str = ""
    block_start: int = -1
    block_end: int = -1
    page_index: int = -1
    block_index: int = -1
    candidate_index: int = -1
    parser_rule_id: str = ""
    direction: str = ""
    raw_zodiac_order: str = ""


@dataclass(frozen=True)
class ValidatedResult:
    target: TargetProfile
    issue: str
    candidate: Candidate
    document: SourceDocument


@dataclass(frozen=True)
class RunResult:
    issue: str
    successes: tuple[ValidatedResult, ...] = ()
    failures: tuple[FailureDetail, ...] = ()
