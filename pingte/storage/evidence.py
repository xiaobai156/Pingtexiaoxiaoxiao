from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pingte.domain.models import ValidatedResult


class EvidenceStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, issue: str, results: Iterable[ValidatedResult]) -> None:
        rows = []
        for result in results:
            if not isinstance(result, ValidatedResult):
                raise TypeError("证据只能接收已经通过校验的 ValidatedResult")
            rows.append(
                {
                    "target_id": result.target.target_id,
                    "name": result.target.name,
                    "url": result.target.url,
                    "position": result.target.position,
                    "keyword": result.target.keyword,
                    "issue": result.issue,
                    "zodiac": result.candidate.zodiac,
                    "raw_line": result.candidate.raw_line,
                    "raw_order": result.candidate.raw_zodiac_order or result.candidate.zodiac,
                    "source": result.candidate.source,
                    "source_url": result.candidate.source_url,
                    "source_sha256": result.document.sha256,
                    "document_id": result.document.document_id,
                    "section_start": result.candidate.section_start,
                    "section_end": result.candidate.section_end,
                    "anchor_line": result.candidate.anchor_line,
                    "block_id": result.candidate.block_id,
                    "block_start": result.candidate.block_start,
                    "block_end": result.candidate.block_end,
                    "page_index": result.candidate.page_index,
                    "block_index": result.candidate.block_index,
                    "candidate_index": result.candidate.candidate_index,
                    "parser_rule_id": result.candidate.parser_rule_id,
                    "direction": result.candidate.direction,
                    "rule_version": result.target.rule_version,
                    "fetched_at": result.document.fetched_at,
                }
            )
        payload = {
            "schema": 1,
            "issue": str(int(issue)),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "results": rows,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        except Exception:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
            raise
