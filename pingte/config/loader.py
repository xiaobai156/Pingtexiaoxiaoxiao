from __future__ import annotations

import json
from pathlib import Path

from pingte.domain.models import TargetProfile

from .schema import ConfigValidationError, SiteConfig, validate_compiled_config


def _read_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigValidationError(f"无法读取配置 {path}：{exc}") from exc


def load_site_configs(directory: Path) -> list[SiteConfig]:
    if not directory.is_dir():
        raise ConfigValidationError(f"站点配置目录不存在：{directory}")
    paths = sorted(directory.glob("PT-*.json"))
    if not paths:
        raise ConfigValidationError(f"站点配置目录没有 PT-*.json：{directory}")

    sites: list[SiteConfig] = []
    for path in paths:
        site = SiteConfig.from_dict(_read_json(path))
        if path.stem != site.target.target_id:
            raise ConfigValidationError(
                f"站点配置文件名 {path.name} 与 target_id "
                f"{site.target.target_id} 不一致"
            )
        sites.append(site)
    return sites


def load_compiled_config(path: Path) -> dict:
    return validate_compiled_config(_read_json(path))


def load_targets(config: dict) -> list[TargetProfile]:
    return [
        TargetProfile(
            url=str(item["url"]),
            position=str(item["position"]),
            name=str(item["name"]),
            keyword=str(item["keyword"]),
            target_id=str(item["target_id"]),
            rule_version=int(item["rule_version"]),
        )
        for item in config.get("targets", [])
    ]
