from __future__ import annotations

import base64

import pytest

from pingte.domain.models import Target
from pingte.fetch.dynamic_record import (
    dynamic_forum_issue_record,
    dynamic_user_issue_record,
)


def make_target(url: str = "https://example.test/#/users/1") -> Target:
    return Target(url, "top", "目录A", "成语平特", "PT-DYNAMIC", 1)


def make_rule() -> dict[str, str]:
    return {"record_topic": "成语平特"}


def make_row(
    record_id: str,
    *,
    draw: str = "164",
    content: str = "<p>164期成语平特【鼠】开00准</p>",
) -> dict:
    return {
        "id": record_id,
        "user_id": "1",
        "user": {"id": "1", "nickname": "目录A"},
        "status": "published",
        "topic": {"title": "成语平特"},
        "draw": draw,
        "content": content,
    }


def test_dynamic_user_rejects_two_records_for_the_same_issue():
    target = make_target()
    data = {"items": [make_row("100"), make_row("101", content="<p>164期成语平特【牛】开00准</p>")]}

    with pytest.raises(RuntimeError, match="存在多条文章记录"):
        dynamic_user_issue_record(data, target, make_rule(), "164")


def test_dynamic_forum_locks_the_url_record_id_before_parsing_content():
    target = Target(
        "https://example.test/#/forums/99",
        "top",
        "目录A",
        "成语平特",
        "PT-DYNAMIC",
        1,
    )
    data = {"items": [make_row("98"), make_row("99", content="<p>164期成语平特【牛】开00准</p>")]}

    record = dynamic_forum_issue_record(data, target, make_rule(), "99", "164")

    assert record["id"] == "99"
    assert record["content"] == "164期成语平特【牛】开00准"


def test_dynamic_record_does_not_expand_stale_encoded_script_fragments():
    target = make_target()
    encoded = base64.b64encode(
        "<p>164期成语平特【鼠】开00准</p>".encode("utf-8")
    ).decode("ascii")
    row = make_row(
        "100",
        content=f'<script>strdecode("{encoded}")</script>',
    )

    with pytest.raises(RuntimeError, match="正文解析后为空"):
        dynamic_user_issue_record(
            {"items": [row]},
            target,
            make_rule(),
            "164",
        )
