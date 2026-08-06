from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from pingte.domain.models import TargetProfile

from .html import html_fragment_to_text


RECORD_CONTAINER_KEYS = (
    "data",
    "items",
    "results",
    "forums",
    "articles",
    "records",
    "list",
)
ANY_ISSUE_PATTERN = r"(?<!\d)\d{1,3}(?!\d)\s*期"


def issue_pattern(issue: str) -> str:
    return rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)\s*期"


def dynamic_id(value: object) -> str:
    if isinstance(value, bool):
        return ""
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text):
        return ""
    return str(int(text))


def dynamic_record_candidates(data: object) -> list[tuple[str, dict]]:
    records: list[tuple[str, dict]] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if not isinstance(value, dict):
            return
        if (
            "id" in value
            and "content" in value
            and ("user_id" in value or isinstance(value.get("user"), dict))
        ):
            records.append((path, value))
            return
        for key in RECORD_CONTAINER_KEYS:
            if key in value:
                visit(value[key], f"{path}.{key}")

    visit(data, "$")
    return records


def rule_matches_target(rule: dict, target: TargetProfile) -> bool:
    rule_target_id = str(rule.get("target_id", ""))
    if target.target_id and rule_target_id:
        return rule_target_id == target.target_id
    return (
        str(rule.get("url_contains", "")) == target.url
        and str(rule.get("name", "")) == target.name
        and str(rule.get("position", "")) == target.position
        and str(rule.get("keyword", "")) == target.keyword
    )


def resolve_target(
    url: str,
    targets: Iterable[TargetProfile],
    rules: Iterable[dict],
) -> tuple[TargetProfile, dict]:
    matches = [target for target in targets if target.url == url]
    if len(matches) != 1:
        raise RuntimeError(
            f"动态页面没有唯一精确站点配置：{len(matches)}条"
        )
    target = matches[0]
    target_rules = [rule for rule in rules if rule_matches_target(rule, target)]
    if len(target_rules) != 1:
        raise RuntimeError(f"动态页面专属解析规则不唯一：{len(target_rules)}条")
    return target, target_rules[0]


def dynamic_record_fields(
    path: str,
    row: dict,
    target: TargetProfile,
    rule: dict,
) -> dict[str, str]:
    record_id = dynamic_id(row.get("id"))
    if not record_id:
        raise RuntimeError(f"接口记录缺少有效文章ID，路径：{path}")
    owner_id = dynamic_id(row.get("user_id"))
    user = row.get("user")
    if not isinstance(user, dict):
        raise RuntimeError(
            f"接口记录缺少作者对象，路径：{path}，文章ID：{record_id}"
        )
    nested_owner_id = dynamic_id(user.get("id"))
    nickname = html_fragment_to_text(str(user.get("nickname", ""))).strip()
    if not owner_id or owner_id != nested_owner_id or nickname != target.name:
        raise RuntimeError(
            f"接口记录作者校验失败，路径：{path}，文章ID：{record_id}"
        )
    if str(row.get("status", "")).strip().lower() != "published":
        raise RuntimeError(
            f"接口记录不是已发布状态，路径：{path}，文章ID：{record_id}"
        )
    content = row.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            f"接口记录正文为空，路径：{path}，文章ID：{record_id}"
        )
    topic = row.get("topic")
    topic_title = html_fragment_to_text(
        str(topic.get("title", "") if isinstance(topic, dict) else topic or "")
    ).strip()
    expected_topic = str(rule.get("record_topic", "")).strip()
    if expected_topic and topic_title != expected_topic:
        raise RuntimeError(
            f"接口记录栏目校验失败，路径：{path}，文章ID：{record_id}，"
            f"期望：{expected_topic}，实际：{topic_title or '空'}"
        )
    title = html_fragment_to_text(str(row.get("title") or topic_title))
    if expected_topic and not title.strip():
        raise RuntimeError(
            f"接口记录标题为空，路径：{path}，文章ID：{record_id}"
        )
    # The API record is the document boundary. Do not expand encoded script
    # fragments here; those fragments can be stale embedded documents.
    record_content = html_fragment_to_text(content)
    if not record_content.strip():
        raise RuntimeError(
            f"接口记录正文解析后为空，路径：{path}，文章ID：{record_id}"
        )
    return {
        "path": path,
        "id": record_id,
        "user_id": owner_id,
        "draw": dynamic_id(row.get("draw")),
        "title": title,
        "content": record_content,
    }


def exact_issue_blocks(text: str, issue: str) -> list[str]:
    marker = issue_pattern(issue)
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]
    blocks: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(marker, line):
            continue
        segment = line
        for next_line in lines[index + 1 :]:
            if re.search(ANY_ISSUE_PATTERN, next_line):
                break
            segment = f"{segment} {next_line}"
        blocks.append(segment)
    return blocks


def dynamic_user_issue_record(
    data: object,
    target: TargetProfile,
    rule: dict,
    issue: str,
) -> dict[str, str]:
    parsed_records = dynamic_record_candidates(data)
    if not parsed_records:
        raise RuntimeError("接口没有结构化文章记录")
    records = []
    seen_ids: set[str] = set()
    for path, row in parsed_records:
        record = dynamic_record_fields(path, row, target, rule)
        if record["id"] in seen_ids:
            raise RuntimeError(f"接口存在重复文章ID：{record['id']}")
        seen_ids.add(record["id"])
        records.append(record)

    issue_key = str(int(issue))
    matches = [record for record in records if record["draw"] == issue_key]
    if not matches:
        raise RuntimeError(
            f"指定{issue_key}期没有唯一文章记录，禁止从其他文章兜底"
        )
    if len(matches) != 1:
        ids = ",".join(record["id"] for record in matches)
        raise RuntimeError(f"指定{issue_key}期存在多条文章记录：{ids}")

    record = matches[0]
    if target.keyword not in record["content"]:
        raise RuntimeError(
            f"指定文章ID {record['id']} 的正文没有目标关键字：{target.keyword}"
        )
    blocks = [
        block
        for block in exact_issue_blocks(record["content"], issue_key)
        if target.keyword in block
    ]
    if not blocks:
        raise RuntimeError(
            f"指定文章ID {record['id']} 没有目标期数和关键字的有效数据块"
        )
    record["content"] = "\n".join(blocks)
    return record


def dynamic_forum_issue_record(
    data: object,
    target: TargetProfile,
    rule: dict,
    forum_id: str,
    issue: str,
) -> dict[str, str]:
    parsed_records = dynamic_record_candidates(data)
    matches = []
    for path, row in parsed_records:
        record_id = dynamic_id(row.get("id"))
        if record_id == forum_id:
            matches.append(dynamic_record_fields(path, row, target, rule))
    if not matches:
        raise RuntimeError(f"接口没有找到唯一文章ID：{forum_id}")
    if len(matches) != 1:
        raise RuntimeError(f"接口找到多个相同文章ID：{forum_id}")
    record = matches[0]
    if target.keyword not in record["content"]:
        raise RuntimeError(
            f"指定文章ID {forum_id} 正文没有目标关键字：{target.keyword}"
        )
    blocks = [
        block
        for block in exact_issue_blocks(record["content"], str(int(issue)))
        if target.keyword in block
    ]
    if not blocks:
        raise RuntimeError(f"指定文章ID {forum_id} 没有目标期数有效数据块")
    record["content"] = "\n".join(blocks)
    return record


def dynamic_record_text(record: dict[str, str]) -> str:
    return "\n".join(
        (
            f"[[FORUM:{record['id']}]]",
            record["title"],
            record["content"],
            f"[[/FORUM:{record['id']}]]",
        )
    )


def fetch_vue_hash_text(
    url: str,
    timeout: int,
    issue: str | None,
    session: object,
    *,
    targets: Iterable[TargetProfile],
    rules: Iterable[dict],
    fetch_raw: Callable[[str, int, object], str],
) -> str:
    parsed = urlsplit(url)
    if "zcphjs.ce83x-ms2rz-orwude.work" not in parsed.netloc or not parsed.fragment:
        return ""

    api_base = f"{parsed.scheme}://{parsed.netloc}/api"
    fragment = parsed.fragment.lstrip("/")
    user_match = re.fullmatch(r"users/(\d+)", fragment)
    if user_match:
        user_id = user_match.group(1)
        api_url = f"{api_base}/v1/users/{user_id}/forums?page=1&per_page=20"
        data = json.loads(fetch_raw(api_url, timeout, session))
        target, rule = resolve_target(url, targets, rules)
        if not issue:
            raise RuntimeError("动态页面必须指定期数")
        record = dynamic_user_issue_record(data, target, rule, issue)
        if dynamic_id(user_id) != record["user_id"]:
            raise RuntimeError(f"URL用户ID与文章作者不一致：{user_id}")
        return dynamic_record_text(record)
    forum_match = re.fullmatch(r"forums/(\d+)", fragment)
    if forum_match:
        forum_id = forum_match.group(1)
        api_url = f"{api_base}/v1/forums/{forum_id}"
        data = json.loads(fetch_raw(api_url, timeout, session))
        target, rule = resolve_target(url, targets, rules)
        if not issue:
            raise RuntimeError("动态页面必须指定期数")
        record = dynamic_forum_issue_record(data, target, rule, forum_id, issue)
        return dynamic_record_text(record)
    return ""
