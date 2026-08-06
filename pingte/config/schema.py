from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pingte.domain.models import TargetProfile


CONFIG_SCHEMA_VERSION = 1
TARGET_ID_PATTERN = re.compile(r"PT-\d{4}")

DATA_STRUCTURE_BY_MODE = {
    "header_section": "confirmed_result_line",
    "followup_label": "label_followup_result",
    "next_line_zodiac": "issue_following_result",
    "nearest_keyword_line": "exact_keyword_result_line",
    "linked_topic": "linked_topic_result",
    "named_section": "confirmed_result_line",
    "ai_public_label": "public_label_followup_result",
    "anchored_section": "confirmed_result_line",
    "anchored_formula_section": "terminal_formula_result",
    "author_section": "confirmed_result_line",
}

SECTION_BOUNDARY_BY_MODE = {
    "header_section": "target_header_section",
    "followup_label": "issue_followup_block",
    "next_line_zodiac": "issue_followup_block",
    "nearest_keyword_line": "single_exact_line",
    "linked_topic": "linked_record",
    "named_section": "target_name_section",
    "ai_public_label": "public_label_block",
    "anchored_section": "explicit_anchors",
    "anchored_formula_section": "explicit_anchors",
    "author_section": "explicit_anchors",
}

ALLOWED_SOURCE_STRATEGIES = {
    "browser_main",
    "dynamic_record",
    "image_resource",
    "linked_record",
    "http_main",
}


class ConfigValidationError(ValueError):
    pass


def _text(value: object) -> str:
    return str(value if value is not None else "").strip()


def _validate_rule(rule: dict[str, Any], label: str, errors: list[str]) -> None:
    required = {
        "url_contains",
        "name",
        "position",
        "keyword",
        "mode",
        "issue_format",
        "data_structure",
        "section_boundary",
        "source_strategy",
    }
    missing = sorted(key for key in required if not _text(rule.get(key)))
    if missing:
        errors.append(f"{label} 缺少字段：{','.join(missing)}")
        return

    mode = _text(rule.get("mode"))
    if mode not in DATA_STRUCTURE_BY_MODE:
        errors.append(f"{label} mode 无效：{mode}")
        return
    if rule.get("position") not in {"top", "tail"}:
        errors.append(f"{label} position 必须是 top 或 tail")
    if rule.get("issue_format") != "arabic_issue_exact":
        errors.append(f"{label} 期数格式必须是 arabic_issue_exact")
    if rule.get("data_structure") != DATA_STRUCTURE_BY_MODE[mode]:
        errors.append(f"{label} 数据结构与 mode 不匹配")
    if rule.get("section_boundary") != SECTION_BOUNDARY_BY_MODE[mode]:
        errors.append(f"{label} 区块边界与 mode 不匹配")

    if mode in {
        "anchored_section",
        "anchored_formula_section",
        "author_section",
        "ai_public_label",
        "followup_label",
    }:
        missing_anchors = [
            key
            for key in ("section_anchor", "section_end")
            if not _text(rule.get(key))
        ]
        if missing_anchors:
            errors.append(
                f"{label} {mode} 必须绑定显式区块锚点："
                f"{','.join(missing_anchors)}"
            )
    if (
        "section_anchor_position" in rule
        and rule.get("section_anchor_position") not in {"first", "last"}
    ):
        errors.append(f"{label} section_anchor_position 必须是 first 或 last")
    if (
        rule.get("section_anchor_position")
        and rule.get("section_anchor_position")
        != ("first" if rule.get("position") == "top" else "last")
    ):
        errors.append(f"{label} section_anchor_position 不能覆盖 target.position")
    if (
        "allow_many_zodiac_candidate" in rule
        and not isinstance(rule.get("allow_many_zodiac_candidate"), bool)
    ):
        errors.append(f"{label} allow_many_zodiac_candidate 必须是布尔值")
    if (
        "result_line_format" in rule
        and rule.get("result_line_format") not in {"compact_zodiac_suffix"}
    ):
        errors.append(f"{label} result_line_format 无效")
    if rule.get("result_line_format") == "compact_zodiac_suffix":
        if not _text(rule.get("result_suffix")):
            errors.append(f"{label} compact_zodiac_suffix 必须绑定 result_suffix")
        if (
            "result_marker_required" not in rule
            or not isinstance(rule.get("result_marker_required"), bool)
        ):
            errors.append(
                f"{label} compact_zodiac_suffix 必须绑定布尔 result_marker_required"
            )
    if mode == "followup_label" and not _text(rule.get("followup_label")):
        errors.append(f"{label} followup_label 必须绑定目标结果标签")

    source_strategy = _text(rule.get("source_strategy"))
    if source_strategy not in ALLOWED_SOURCE_STRATEGIES:
        errors.append(f"{label} 权威来源策略无效：{source_strategy}")
    if source_strategy == "dynamic_record" and not _text(rule.get("record_topic")):
        errors.append(f"{label} 动态记录必须绑定 record_topic 栏目")
    if mode == "linked_topic" and source_strategy != "linked_record":
        errors.append(f"{label} linked_topic 必须使用 linked_record 来源")
    if source_strategy == "linked_record" and mode != "linked_topic":
        errors.append(f"{label} linked_record 必须使用 linked_topic mode")
    if source_strategy == "browser_main" and (
        rule.get("frame_scope") != "main"
        or rule.get("browser_selector") != "body"
    ):
        errors.append(f"{label} 浏览器规则必须绑定主框架和 body DOM")


@dataclass(frozen=True)
class SiteConfig:
    schema_version: int
    target: TargetProfile
    parser: dict[str, Any]
    auxiliary: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: object) -> SiteConfig:
        if not isinstance(payload, dict):
            raise ConfigValidationError("站点配置必须是对象")
        errors: list[str] = []
        schema_version = payload.get("schema_version")
        target_id = _text(payload.get("target_id"))
        rule_version = payload.get("rule_version")
        target_data = payload.get("target")
        parser = payload.get("parser")
        auxiliary = payload.get("auxiliary", {})

        if schema_version != CONFIG_SCHEMA_VERSION:
            errors.append(
                f"schema_version 必须是 {CONFIG_SCHEMA_VERSION}"
            )
        if not TARGET_ID_PATTERN.fullmatch(target_id):
            errors.append("target_id 必须使用 PT-0001 格式")
        if not isinstance(rule_version, int) or rule_version < 1:
            errors.append("rule_version 必须是大于0的整数")
        if not isinstance(target_data, dict):
            errors.append("target 必须是对象")
            target_data = {}
        if not isinstance(parser, dict):
            errors.append("parser 必须是对象")
            parser = {}
        if not isinstance(auxiliary, dict):
            errors.append("auxiliary 必须是对象")
            auxiliary = {}

        missing_target = sorted(
            key
            for key in ("url", "position", "name", "keyword")
            if not _text(target_data.get(key))
        )
        if missing_target:
            errors.append(f"target 缺少字段：{','.join(missing_target)}")
        if target_data.get("position") not in {"top", "tail"}:
            errors.append("target.position 必须是 top 或 tail")

        _validate_rule(parser, "parser", errors)
        for key in ("url", "position", "name", "keyword"):
            parser_key = "url_contains" if key == "url" else key
            if _text(parser.get(parser_key)) != _text(target_data.get(key)):
                errors.append(f"parser.{parser_key} 必须与 target.{key} 精确一致")

        if errors:
            raise ConfigValidationError("站点配置校验失败：" + "；".join(errors))

        return cls(
            schema_version=CONFIG_SCHEMA_VERSION,
            target=TargetProfile(
                url=_text(target_data["url"]),
                position=_text(target_data["position"]),
                name=_text(target_data["name"]),
                keyword=_text(target_data["keyword"]),
                target_id=target_id,
                rule_version=int(rule_version),
            ),
            parser=dict(parser),
            auxiliary=dict(auxiliary),
        )

    def to_runtime_parts(self) -> tuple[dict[str, Any], dict[str, Any]]:
        target = {
            "target_id": self.target.target_id,
            "rule_version": self.target.rule_version,
            "url": self.target.url,
            "position": self.target.position,
            "name": self.target.name,
            "keyword": self.target.keyword,
        }
        parser = {
            "target_id": self.target.target_id,
            "rule_version": self.target.rule_version,
            **self.parser,
        }
        return target, parser


def validate_compiled_config(config: object) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ConfigValidationError("编译配置必须是对象")

    errors: list[str] = []
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {CONFIG_SCHEMA_VERSION}")
    targets = config.get("targets")
    rules = config.get("special_parse_targets")
    image_rules = config.get("special_image_targets", [])
    followup_rules = config.get("special_followup_labels", [])
    if not isinstance(targets, list) or not targets:
        errors.append("targets 必须是非空列表")
        targets = []
    if not isinstance(rules, list):
        errors.append("special_parse_targets 必须是列表")
        rules = []
    if not isinstance(image_rules, list):
        errors.append("special_image_targets 必须是列表")
        image_rules = []
    if not isinstance(followup_rules, list):
        errors.append("special_followup_labels 必须是列表")

    target_ids: set[str] = set()
    names: set[str] = set()
    identities: set[tuple[str, str, str, str]] = set()
    for index, target in enumerate(targets):
        label = f"targets[{index}]"
        if not isinstance(target, dict):
            errors.append(f"{label} 必须是对象")
            continue
        target_id = _text(target.get("target_id"))
        rule_version = target.get("rule_version")
        if not TARGET_ID_PATTERN.fullmatch(target_id):
            errors.append(f"{label} target_id 无效")
        elif target_id in target_ids:
            errors.append(f"target_id 重复：{target_id}")
        target_ids.add(target_id)
        if not isinstance(rule_version, int) or rule_version < 1:
            errors.append(f"{label} rule_version 无效")
        missing = sorted(
            key
            for key in ("url", "position", "name", "keyword")
            if not _text(target.get(key))
        )
        if missing:
            errors.append(f"{label} 缺少字段：{','.join(missing)}")
        if target.get("position") not in {"top", "tail"}:
            errors.append(f"{label} position 必须是 top 或 tail")
        name = _text(target.get("name"))
        if name in names:
            errors.append(f"目录名重复：{name}")
        names.add(name)
        identity = tuple(
            _text(target.get(key))
            for key in ("url", "position", "name", "keyword")
        )
        if identity in identities:
            errors.append(f"目标字段重复：{name}")
        identities.add(identity)

    rule_ids: set[str] = set()
    rules_by_id: dict[str, list[dict[str, Any]]] = {}
    for index, rule in enumerate(rules):
        label = f"special_parse_targets[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{label} 必须是对象")
            continue
        _validate_rule(rule, label, errors)
        target_id = _text(rule.get("target_id"))
        if not TARGET_ID_PATTERN.fullmatch(target_id):
            errors.append(f"{label} target_id 无效")
        elif target_id in rule_ids:
            errors.append(f"专属规则 target_id 重复：{target_id}")
        rule_ids.add(target_id)
        if not isinstance(rule.get("rule_version"), int) or rule.get("rule_version") < 1:
            errors.append(f"{label} rule_version 无效")
        rules_by_id.setdefault(target_id, []).append(rule)

    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            continue
        target_id = _text(target.get("target_id"))
        matches = rules_by_id.get(target_id, [])
        if len(matches) != 1:
            errors.append(
                f"targets[{index}] 必须且只能匹配1条站点级专属解析，"
                f"实际{len(matches)}条"
            )
            continue
        rule = matches[0]
        if rule.get("rule_version") != target.get("rule_version"):
            errors.append(f"targets[{index}] 规则版本不一致")
        for key in ("position", "name", "keyword"):
            if _text(rule.get(key)) != _text(target.get(key)):
                errors.append(f"targets[{index}] 专属解析字段 {key} 不一致")
        if _text(rule.get("url_contains")) != _text(target.get("url")):
            errors.append(
                f"targets[{index}] 专属解析必须绑定完整URL/topic"
            )
        if rule.get("source_strategy") == "image_resource":
            if not any(
                isinstance(item, dict)
                and _text(item.get("url_contains")) == _text(target.get("url"))
                and _text(item.get("name")) == _text(target.get("name"))
                for item in image_rules
            ):
                errors.append(
                    f"targets[{index}] image_resource 缺少对应图片来源绑定"
                )

    if target_ids != rule_ids:
        missing = sorted(target_ids - rule_ids)
        orphaned = sorted(rule_ids - target_ids)
        if missing:
            errors.append(f"缺少专属规则：{','.join(missing)}")
        if orphaned:
            errors.append(f"存在无目标专属规则：{','.join(orphaned)}")

    if errors:
        raise ConfigValidationError("配置启动校验失败：" + "；".join(errors))
    return config
