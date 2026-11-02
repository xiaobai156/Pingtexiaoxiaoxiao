from __future__ import annotations

from collections.abc import Iterable

from pingte.domain.models import TargetProfile
from pingte.parse.context import RuleBook


def target_cache_key(target: TargetProfile) -> tuple[str, str, str, str]:
    return target.url, target.name, target.position, target.keyword


def unique_urls(targets: Iterable[TargetProfile]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for target in targets:
        if target.url in seen:
            continue
        seen.add(target.url)
        result.append(target.url)
    return result


def target_has_required_image_source(target: TargetProfile, rules: RuleBook) -> bool:
    return rules.rule_for(target).get("source_strategy") == "image_resource"


def target_has_required_dynamic_source(target: TargetProfile, rules: RuleBook) -> bool:
    return rules.rule_for(target).get("source_strategy") == "dynamic_record"


def target_allows_browser_dom(target: TargetProfile, rules: RuleBook) -> bool:
    return rules.rule_for(target).get("source_strategy") in {
        "browser_main",
        "http_main",
    }


def target_requires_browser_dom(
    target: TargetProfile,
    text: str,
    zodiac: str | None,
    conflict_reason: str | None,
    rules: RuleBook,
    deserialize_documents,
) -> bool:
    strategy = rules.rule_for(target).get("source_strategy")
    if strategy == "browser_main":
        return True
    if strategy != "http_main":
        return False
    if conflict_reason and conflict_reason.startswith("同一目标文档"):
        return False
    documents = deserialize_documents(text)
    if any(
        document.source.startswith(("page-decoded:", "external-script"))
        for document in documents
    ):
        return True
    return zodiac is None
