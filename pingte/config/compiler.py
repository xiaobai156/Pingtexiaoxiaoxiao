from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .loader import load_site_configs
from .schema import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    SiteConfig,
    validate_compiled_config,
)


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _check_site_uniqueness(sites: list[SiteConfig]) -> None:
    errors: list[str] = []
    ids: set[str] = set()
    names: set[str] = set()
    identities: set[tuple[str, str, str, str]] = set()
    for site in sites:
        target = site.target
        if target.target_id in ids:
            errors.append(f"target_id 重复：{target.target_id}")
        ids.add(target.target_id)
        if target.name in names:
            errors.append(f"目录名重复：{target.name}")
        names.add(target.name)
        identity = (
            target.url,
            target.position,
            target.name,
            target.keyword,
        )
        if identity in identities:
            errors.append(f"目标字段重复：{target.name}")
        identities.add(identity)
    if errors:
        raise ConfigValidationError("站点配置重复：" + "；".join(errors))


def build_compiled_config(sites: list[SiteConfig]) -> dict[str, Any]:
    ordered = sorted(sites, key=lambda site: site.target.target_id)
    _check_site_uniqueness(ordered)
    targets: list[dict[str, Any]] = []
    parsers: list[dict[str, Any]] = []
    image_targets: list[dict[str, Any]] = []
    followup_labels: list[dict[str, Any]] = []

    for site in ordered:
        target, parser = site.to_runtime_parts()
        targets.append(target)
        parsers.append(parser)
        image = site.auxiliary.get("image_target")
        if isinstance(image, dict):
            image_targets.append(dict(image))
        followup = site.auxiliary.get("followup_label")
        if isinstance(followup, dict):
            followup_labels.append(dict(followup))

    return validate_compiled_config(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "targets": targets,
            "special_image_targets": image_targets,
            "special_followup_labels": followup_labels,
            "special_parse_targets": parsers,
        }
    )


def compile_site_configs(directory: Path, output_path: Path) -> dict[str, Any]:
    compiled = build_compiled_config(load_site_configs(directory))
    _atomic_write_json(output_path, compiled)
    return compiled


def _legacy_identity_match(rule: object, target: dict[str, Any]) -> bool:
    return (
        isinstance(rule, dict)
        and str(rule.get("url_contains", "")) == str(target.get("url", ""))
        and all(
            str(rule.get(key, "")) == str(target.get(key, ""))
            for key in ("position", "name", "keyword")
        )
    )


def migrate_legacy_config(
    legacy_path: Path,
    sites_directory: Path,
) -> list[SiteConfig]:
    if sites_directory.exists() and any(sites_directory.iterdir()):
        raise ConfigValidationError(
            f"站点配置目录非空，拒绝覆盖：{sites_directory}"
        )
    try:
        with legacy_path.open("r", encoding="utf-8") as file:
            legacy = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigValidationError(f"无法读取旧配置：{exc}") from exc
    targets = legacy.get("targets") if isinstance(legacy, dict) else None
    rules = legacy.get("special_parse_targets") if isinstance(legacy, dict) else None
    if not isinstance(targets, list) or not targets:
        raise ConfigValidationError("旧配置 targets 必须是非空列表")
    if not isinstance(rules, list):
        raise ConfigValidationError("旧配置 special_parse_targets 必须是列表")

    image_rules = legacy.get("special_image_targets", [])
    followup_rules = legacy.get("special_followup_labels", [])
    migrated: list[SiteConfig] = []
    pending_files: list[tuple[Path, dict[str, Any]]] = []
    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            raise ConfigValidationError(f"旧配置 targets[{index - 1}] 必须是对象")
        matches = [rule for rule in rules if _legacy_identity_match(rule, target)]
        if len(matches) != 1:
            raise ConfigValidationError(
                f"目录 {target.get('name', '')} 必须精确匹配1条旧专属规则，"
                f"实际{len(matches)}条"
            )
        target_id = f"PT-{index:04d}"
        auxiliary: dict[str, Any] = {}
        images = [
            dict(item)
            for item in image_rules
            if isinstance(item, dict)
            and str(item.get("url_contains", "")) == str(target.get("url", ""))
            and str(item.get("name", "")) == str(target.get("name", ""))
        ]
        if len(images) > 1:
            raise ConfigValidationError(f"目录 {target.get('name', '')} 图片来源重复")
        if images:
            auxiliary["image_target"] = images[0]
        followups = [
            dict(item)
            for item in followup_rules
            if isinstance(item, dict)
            and str(item.get("url_contains", "")) == str(target.get("url", ""))
        ]
        if len(followups) > 1:
            raise ConfigValidationError(f"目录 {target.get('name', '')} 跟随标签重复")
        if followups:
            auxiliary["followup_label"] = followups[0]

        payload = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "target_id": target_id,
            "rule_version": 1,
            "target": {
                "url": str(target.get("url", "")),
                "position": str(target.get("position", "")),
                "name": str(target.get("name", "")),
                "keyword": str(target.get("keyword", "")),
            },
            "parser": dict(matches[0]),
            "auxiliary": auxiliary,
        }
        site = SiteConfig.from_dict(payload)
        migrated.append(site)
        pending_files.append((sites_directory / f"{target_id}.json", payload))
    _check_site_uniqueness(migrated)
    sites_directory.mkdir(parents=True, exist_ok=True)
    for path, payload in pending_files:
        _atomic_write_json(path, payload)
    return migrated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="编译平特站点配置")
    parser.add_argument(
        "--sites",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "config" / "sites",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "targets.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    compiled = compile_site_configs(args.sites, args.output)
    print(
        f"配置编译完成：{len(compiled['targets'])} 个目录，"
        f"{len(compiled['special_parse_targets'])} 条专属规则"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
