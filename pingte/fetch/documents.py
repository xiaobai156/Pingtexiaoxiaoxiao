from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Iterable

from pingte.domain.models import SourceDocument


SOURCE_DOCUMENT_START = "[[ZODIAC_SOURCE_DOCUMENT:"
SOURCE_DOCUMENT_END = "[[/ZODIAC_SOURCE_DOCUMENT]]"


def make_source_document(
    source: str,
    source_url: str,
    primary: bool,
    text: str,
    *,
    fetched_at: str | None = None,
    document_id: str = "",
) -> SourceDocument:
    return SourceDocument(
        source=source,
        source_url=source_url,
        primary=primary,
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        fetched_at=fetched_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        document_id=document_id,
    )


def serialize_source_documents(documents: Iterable[SourceDocument]) -> str:
    chunks: list[str] = []
    seen: set[tuple[str, str, bool, str, str]] = set()
    for document in documents:
        text = document.text.strip()
        if not text:
            continue
        key = (
            document.source,
            document.source_url,
            document.primary,
            document.document_id,
            text,
        )
        if key in seen:
            continue
        seen.add(key)
        sha256 = document.sha256 or hashlib.sha256(text.encode("utf-8")).hexdigest()
        metadata = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "source": document.source,
                    "source_url": document.source_url,
                    "primary": document.primary,
                    "sha256": sha256,
                    "fetched_at": document.fetched_at,
                    "document_id": document.document_id,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).decode("ascii")
        chunks.extend(
            (f"{SOURCE_DOCUMENT_START}{metadata}]]", text, SOURCE_DOCUMENT_END)
        )
    return "\n".join(chunks)


def deserialize_source_documents(text: str) -> list[SourceDocument]:
    import re

    pattern = re.compile(
        rf"{re.escape(SOURCE_DOCUMENT_START)}([A-Za-z0-9_=-]+)\]\]\s*"
        rf"([\s\S]*?)\s*{re.escape(SOURCE_DOCUMENT_END)}"
    )
    documents: list[SourceDocument] = []
    for match in pattern.finditer(text):
        try:
            metadata = json.loads(
                base64.urlsafe_b64decode(match.group(1)).decode("ascii")
            )
        except Exception:
            continue
        document_text = match.group(2).strip()
        documents.append(
            SourceDocument(
                source=str(metadata.get("source", "unknown")),
                source_url=str(metadata.get("source_url", "")),
                primary=bool(metadata.get("primary")),
                text=document_text,
                sha256=str(metadata.get("sha256", ""))
                or hashlib.sha256(document_text.encode("utf-8")).hexdigest(),
                fetched_at=str(metadata.get("fetched_at", "")),
                document_id=str(metadata.get("document_id", "")),
            )
        )
    if documents:
        return documents
    if not text.strip():
        return []
    return [make_source_document("legacy-text", "", True, text)]
