from dataclasses import dataclass
from enum import Enum


class FailureCode(str, Enum):
    WEB_FETCH_FAILED = "web_fetch_failed"
    EMPTY_DOCUMENT = "empty_document"
    TARGET_BOUNDARY_MISSING = "target_boundary_missing"
    KEYWORD_MISSING = "keyword_missing"
    ISSUE_MISSING = "issue_missing"
    ISSUE_OUT_OF_DIRECTION_WINDOW = "issue_out_of_direction_window"
    ANCHOR_MISSING = "anchor_missing"
    BLOCK_AMBIGUOUS = "block_ambiguous"
    CONTENT_PENDING = "content_pending"
    ZODIAC_MISSING = "zodiac_missing"
    TOO_MANY_ZODIACS = "too_many_zodiacs"
    AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
    RECORD_ID_MISSING = "record_id_missing"
    RECORD_ID_AMBIGUOUS = "record_id_ambiguous"
    RECORD_VALIDATION_FAILED = "record_validation_failed"
    SOURCE_CONFLICT = "source_conflict"
    CACHE_UPDATE_FAILED = "cache_update_failed"
    RULE_MISSING = "rule_missing"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class FailureDetail:
    code: FailureCode
    message: str
    target_id: str
    name: str
    url: str
    position: str
    keyword: str
    issue: str
    matched_line: str = ""
    visible_issues: tuple[str, ...] = ()

    def render(self) -> str:
        parts = [
            self.message,
            f"目录：{self.name}",
            f"网址：{self.url}",
            f"位置：{self.position}",
            f"关键字：{self.keyword}",
            f"指定期数：{self.issue}",
        ]
        if self.matched_line:
            parts.append(f"匹配行：{self.matched_line}")
        if self.visible_issues:
            visible = "、".join(f"{issue}期" for issue in self.visible_issues)
            parts.append(f"当前可见期数：{visible}")
        return "，".join(parts)
