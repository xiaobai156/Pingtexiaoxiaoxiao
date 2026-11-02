from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pingte.config.compiler import _atomic_write_json, compile_site_configs
from pingte.config.loader import load_compiled_config, load_site_configs
from pingte.config.schema import SiteConfig
from pingte.domain.zodiac import ZODIACS
from pingte.storage.cache import CacheStore
from pingte.validation.identity import target_cache_key

TARGET_ID_PATTERN = re.compile(r"PT-(\d{4})")
SPECIAL_APPROVALS = frozenset(
    {
        "history_shortage",
        "recent_issue_range",
        "suspected_duplicate",
    }
)
RECENT_ISSUE_RANGE = frozenset({"225", "226", "227", "228", "229"})


class OnboardingError(ValueError):
    """A formal onboarding gate rejected a candidate or a transaction."""


@dataclass(frozen=True)
class OnboardCandidate:
    """A live-verified candidate prepared by the parsing/validation layer."""

    site: SiteConfig
    values: Mapping[str, str]
    evidence: Mapping[str, Any]
    special_approval: str = ""


@dataclass(frozen=True)
class DuplicateRun:
    candidate_name: str
    existing_name: str
    existing_target_id: str
    issues: tuple[str, ...]

    @property
    def length(self) -> int:
        return len(self.issues)


@dataclass(frozen=True)
class OnboardingCheck:
    accepted: tuple[OnboardCandidate, ...] = ()
    rejected: Mapping[str, str] = field(default_factory=dict)
    duplicate_runs: tuple[DuplicateRun, ...] = ()


@dataclass(frozen=True)
class OnboardingCommit:
    target_ids: tuple[str, ...]
    cache_issues: tuple[str, ...]


def normalize_values(values: Mapping[str, str]) -> dict[str, str]:
    """Normalize and fail closed on malformed single-period values."""

    normalized: dict[str, str] = {}
    for raw_issue, raw_value in values.items():
        issue = str(raw_issue).strip()
        value = str(raw_value).strip()
        if not issue.isdigit() or not value:
            continue
        if not 1 <= len(value) <= 2:
            raise OnboardingError(
                f"期数 {issue} 的生肖数量不合法：{value}"
            )
        if len(set(value)) != len(value) or any(
            zodiac not in ZODIACS for zodiac in value
        ):
            raise OnboardingError(
                f"期数 {issue} 的生肖值不合法或重复：{value}"
            )
        normalized[str(int(issue))] = value
    return normalized


def continuous_equal_runs(
    candidate_values: Mapping[str, str],
    existing_values: Mapping[str, str],
    issue_keys: Sequence[str] | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Return exact-equal runs, stopping at every missing/non-consecutive issue."""

    candidate = normalize_values(candidate_values)
    existing = normalize_values(existing_values)
    common = {
        int(issue)
        for issue in (issue_keys or tuple(candidate))
        if str(issue).isdigit()
        and str(int(issue)) in candidate
        and str(int(issue)) in existing
    }
    ordered = sorted(common, reverse=True)
    runs: list[tuple[str, ...]] = []
    current: list[str] = []
    previous: int | None = None
    for issue in ordered:
        issue_key = str(issue)
        same = candidate[issue_key] == existing[issue_key]
        consecutive = previous is None or previous - issue == 1
        if same and consecutive:
            current.append(issue_key)
        else:
            if current:
                runs.append(tuple(current))
            current = [issue_key] if same else []
        previous = issue
    if current:
        runs.append(tuple(current))
    return tuple(runs)


def _site_payload(site: SiteConfig, evidence: Mapping[str, Any]) -> dict[str, Any]:
    target = site.target
    auxiliary = dict(site.auxiliary)
    auxiliary["onboarding"] = dict(evidence)
    return {
        "schema_version": 1,
        "target_id": target.target_id,
        "rule_version": target.rule_version,
        "target": {
            "url": target.url,
            "position": target.position,
            "name": target.name,
            "keyword": target.keyword,
        },
        "parser": dict(site.parser),
        "auxiliary": auxiliary,
    }


def _read_json_strict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise OnboardingError(f"无法读取 {path.name}：{exc}") from exc
    if not isinstance(payload, dict):
        raise OnboardingError(f"{path.name} 必须是JSON对象")
    return payload


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".rollback.tmp",
            delete=False,
        ) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise


class SiteOnboarder:
    """Atomic active-config/cache onboarding transaction for verified sites."""

    def __init__(
        self,
        project_dir: Path,
        *,
        history_minimum: int = 10,
        cache_window_size: int = 10,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.config_dir = self.project_dir / "config" / "sites"
        self.targets_path = self.project_dir / "targets.json"
        self.archived_path = self.project_dir / "archived_targets.json"
        self.cache_path = self.project_dir / "recent_10_cache.json"
        self.history_minimum = max(1, int(history_minimum))
        self.cache_window_size = max(1, int(cache_window_size))

    def _load_active(self) -> list[SiteConfig]:
        try:
            return load_site_configs(self.config_dir)
        except Exception as exc:
            raise OnboardingError(f"活跃站点配置读取失败：{exc}") from exc

    def _load_cache(self) -> dict[str, Any]:
        try:
            cache = CacheStore(self.cache_path).load_strict()
        except Exception as exc:
            raise OnboardingError(str(exc)) from exc
        if cache.get("window_size") != self.cache_window_size:
            raise OnboardingError("正式缓存窗口大小与新增流程不一致")
        if not isinstance(cache.get("sites"), list):
            raise OnboardingError("正式缓存 sites 不是列表")
        return cache

    def _archived_identities(self) -> set[tuple[str, str, str, str]]:
        if not self.archived_path.exists():
            return set()
        payload = _read_json_strict(self.archived_path)
        identities: set[tuple[str, str, str, str]] = set()
        for item in payload.get("sites", []):
            if not isinstance(item, dict):
                continue
            target = item.get("original_target", item)
            if not isinstance(target, dict):
                continue
            identities.add(
                tuple(
                    str(target.get(key, ""))
                    for key in ("url", "name", "position", "keyword")
                )
            )
        return identities

    @staticmethod
    def _cache_entries(cache: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        for item in cache.get("sites", []):
            if not isinstance(item, dict):
                continue
            target_id = str(item.get("target_id", ""))
            if target_id:
                if target_id in entries:
                    raise OnboardingError(f"正式缓存 target_id 重复：{target_id}")
                entries[target_id] = item
        return entries

    def _validate_current_cache(
        self,
        active: Sequence[SiteConfig],
        cache: Mapping[str, Any],
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        issue_keys = sorted(
            {
                int(item)
                for item in cache.get("issues", [])
                if str(item).isdigit()
            },
            reverse=True,
        )
        if not issue_keys:
            raise OnboardingError("正式缓存没有有效期数")
        entries = self._cache_entries(cache)
        active_ids = [site.target.target_id for site in sorted(active, key=lambda item: item.target.target_id)]
        if list(entries) != active_ids:
            raise OnboardingError("正式缓存身份、数量或顺序与活跃配置不一致")
        for site in active:
            entry = entries[site.target.target_id]
            identity = (
                str(entry.get("url", "")),
                str(entry.get("name", "")),
                str(entry.get("position", "")),
                str(entry.get("keyword", "")),
            )
            if identity != target_cache_key(site.target):
                raise OnboardingError(
                    f"正式缓存身份与配置不一致：{site.target.name}"
                )
            if not isinstance(entry.get("values"), dict):
                raise OnboardingError(
                    f"正式缓存 values 不是对象：{site.target.name}"
                )
        return [str(issue) for issue in issue_keys], entries

    def _validate_candidate(
        self,
        candidate: OnboardCandidate,
        cache_issue_keys: Sequence[str],
        active_names: set[str],
        active_identities: set[tuple[str, str, str, str]],
        archived_identities: set[tuple[str, str, str, str]],
    ) -> dict[str, str]:
        target = candidate.site.target
        identity = target_cache_key(target)
        special_approval = candidate.special_approval.strip()
        if special_approval not in SPECIAL_APPROVALS | {""}:
            raise OnboardingError(
                f"特例授权类型无效：{target.name}（{special_approval}）"
            )
        evidence = dict(candidate.evidence)
        if str(evidence.get("special_approval", "")).strip() != special_approval:
            raise OnboardingError(f"特例授权记录不一致：{target.name}")
        if special_approval and not str(evidence.get("authorization", "")).strip():
            raise OnboardingError(f"特例授权缺少授权记录：{target.name}")
        if target.name in active_names:
            raise OnboardingError(f"目录名已存在：{target.name}")
        if identity in active_identities or identity in archived_identities:
            raise OnboardingError(f"站点身份已存在或已封存：{target.name}")
        if not TARGET_ID_PATTERN.fullmatch(target.target_id):
            raise OnboardingError(f"target_id 无效：{target.target_id}")

        values = normalize_values(candidate.values)
        recent_issue_range = special_approval == "recent_issue_range"
        if recent_issue_range:
            raw_allowed_issues = evidence.get("allowed_issues")
            if not isinstance(
                raw_allowed_issues,
                (list, tuple, set, frozenset),
            ):
                raise OnboardingError(
                    f"近期特例缺少允许期数范围：{target.name}"
                )
            try:
                allowed_issues = {
                    str(int(item)) for item in raw_allowed_issues
                }
            except (TypeError, ValueError) as exc:
                raise OnboardingError(
                    f"近期特例允许期数范围无效：{target.name}"
                ) from exc
            if allowed_issues != RECENT_ISSUE_RANGE:
                raise OnboardingError(
                    f"近期特例期数范围必须固定为225—229期：{target.name}"
                )
            if not RECENT_ISSUE_RANGE.intersection(values):
                raise OnboardingError(
                    f"近期特例未抓到225—229期有效结果：{target.name}"
                )
        if (
            len(values) < self.history_minimum
            and (
                special_approval not in {"history_shortage", "recent_issue_range"}
                or not values
            )
        ):
            raise OnboardingError(
                f"有效历史不足{self.history_minimum}期：{target.name}（{len(values)}期）"
            )
        if not recent_issue_range and not set(cache_issue_keys[:2]).intersection(values):
            raise OnboardingError(
                f"没有命中正式缓存最新期或上一期：{target.name}"
            )

        required_evidence = (
            "source_url",
            "source_strategy",
            "parser_mode",
            "section_start",
            "verified_issue",
            "direction_window",
            "raw_lines",
        )
        missing = [key for key in required_evidence if not evidence.get(key)]
        if missing:
            raise OnboardingError(
                f"候选证据不完整：{target.name} 缺少{','.join(missing)}"
            )
        if str(evidence["source_url"]) != target.url:
            raise OnboardingError(f"候选来源URL不匹配：{target.name}")
        unexpected = evidence.get("unexpected_issues", ())
        if unexpected:
            raise OnboardingError(
                f"目标区块存在未解释期数：{target.name}（{','.join(map(str, unexpected))}）"
            )
        verified_issue = str(int(evidence["verified_issue"]))
        direction_window = {
            str(int(item)) for item in evidence["direction_window"]
        }
        if verified_issue not in values or verified_issue not in direction_window:
            raise OnboardingError(
                f"指定期不在已验证方向窗口：{target.name} {verified_issue}期"
            )
        raw_lines = evidence["raw_lines"]
        if not isinstance(raw_lines, Mapping) or not raw_lines.get(verified_issue):
            raise OnboardingError(f"指定期缺少原始结果行证据：{target.name}")
        return values

    def evaluate(
        self,
        candidates: Sequence[OnboardCandidate],
        *,
        active: Sequence[SiteConfig] | None = None,
        cache: Mapping[str, Any] | None = None,
    ) -> OnboardingCheck:
        active_sites = list(active) if active is not None else self._load_active()
        current_cache = dict(cache) if cache is not None else self._load_cache()
        cache_issue_keys, cache_entries = self._validate_current_cache(
            active_sites,
            current_cache,
        )
        active_names = {site.target.name for site in active_sites}
        active_identities = {target_cache_key(site.target) for site in active_sites}
        archived_identities = self._archived_identities()

        rejected: dict[str, str] = {}
        normalized_by_name: dict[str, dict[str, str]] = {}
        for candidate in candidates:
            try:
                normalized_by_name[candidate.site.target.name] = self._validate_candidate(
                    candidate,
                    cache_issue_keys,
                    active_names,
                    active_identities,
                    archived_identities,
                )
            except OnboardingError as exc:
                rejected[candidate.site.target.name] = str(exc)

        seen_names: set[str] = set()
        seen_ids: set[str] = set()
        seen_identities: set[tuple[str, str, str, str]] = set()
        for candidate in candidates:
            target = candidate.site.target
            identity = target_cache_key(target)
            if target.name in seen_names:
                rejected[target.name] = "本批次目录名重复"
            if target.target_id in seen_ids:
                rejected[target.name] = "本批次 target_id 重复"
            if identity in seen_identities:
                rejected[target.name] = "本批次站点身份重复"
            seen_names.add(target.name)
            seen_ids.add(target.target_id)
            seen_identities.add(identity)

        duplicate_runs: list[DuplicateRun] = []
        for candidate in candidates:
            name = candidate.site.target.name
            values = normalized_by_name.get(name)
            if values is None:
                continue
            for entry in cache_entries.values():
                runs = continuous_equal_runs(
                    values,
                    entry.get("values", {}),
                    cache_issue_keys,
                )
                for issues in runs:
                    if len(issues) >= 6:
                        rejected[name] = "与正式缓存连续6期以上相同，禁止加入"
                    elif (
                        len(issues) >= 3
                        and candidate.special_approval != "suspected_duplicate"
                    ):
                        rejected[name] = "与正式缓存连续3期以上相同，需人工审核"
                    if len(issues) >= 3:
                        duplicate_runs.append(
                            DuplicateRun(
                                candidate_name=name,
                                existing_name=str(entry.get("name", "")),
                                existing_target_id=str(entry.get("target_id", "")),
                                issues=issues,
                            )
                        )
        accepted = tuple(
            candidate
            for candidate in candidates
            if candidate.site.target.name not in rejected
        )
        return OnboardingCheck(
            accepted=accepted,
            rejected=dict(rejected),
            duplicate_runs=tuple(duplicate_runs),
        )

    @staticmethod
    def _next_ids(active: Sequence[SiteConfig], count: int) -> tuple[str, ...]:
        numbers = [
            int(match.group(1))
            for site in active
            if (match := TARGET_ID_PATTERN.fullmatch(site.target.target_id))
        ]
        if not numbers:
            start = 1
        else:
            start = max(numbers) + 1
        return tuple(f"PT-{start + index:04d}" for index in range(count))

    def _build_cache_payload(
        self,
        active: Sequence[SiteConfig],
        candidates: Sequence[OnboardCandidate],
        values_by_name: Mapping[str, Mapping[str, str]],
        old_cache: Mapping[str, Any],
    ) -> dict[str, Any]:
        old_entries = self._cache_entries(old_cache)
        candidate_by_id = {
            candidate.site.target.target_id: candidate for candidate in candidates
        }
        all_sites = sorted(
            list(active) + [candidate.site for candidate in candidates],
            key=lambda site: site.target.target_id,
        )
        cache_issue_keys = sorted(
            {
                int(item)
                for item in old_cache.get("issues", [])
                if str(item).isdigit()
            },
            reverse=True,
        )
        sites: list[dict[str, Any]] = []
        for site in all_sites:
            target = site.target
            candidate = candidate_by_id.get(target.target_id)
            if candidate is None:
                old_entry = old_entries[target.target_id]
                values = {
                    str(key): str(value)
                    for key, value in old_entry.get("values", {}).items()
                    if str(key).isdigit() and str(value).strip()
                }
            else:
                values = {
                    str(key): str(value)
                    for key, value in values_by_name[target.name].items()
                    if int(key) in cache_issue_keys
                }
            sites.append(
                {
                    "target_id": target.target_id,
                    "name": target.name,
                    "url": target.url,
                    "position": target.position,
                    "keyword": target.keyword,
                    "values": {
                        key: values[key]
                        for key in sorted(values, key=int, reverse=True)
                    },
                }
            )
        return {
            "schema": 1,
            "description": "平特肖重复检测最近10期基准数据；由每日指定期抓取自动覆盖更新。",
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"
            ),
            "window_size": self.cache_window_size,
            "issues": cache_issue_keys,
            "sites": sites,
        }

    def _verify_commit(self, expected_ids: Sequence[str]) -> None:
        sites = load_site_configs(self.config_dir)
        compiled = load_compiled_config(self.targets_path)
        actual_ids = [site.target.target_id for site in sites]
        if actual_ids != list(expected_ids):
            raise OnboardingError("提交后站点配置顺序校验失败")
        compiled_ids = [str(item["target_id"]) for item in compiled["targets"]]
        if compiled_ids != list(expected_ids):
            raise OnboardingError("提交后编译配置顺序校验失败")
        cache = self._load_cache()
        cache_ids = [str(item["target_id"]) for item in cache["sites"]]
        if cache_ids != list(expected_ids):
            raise OnboardingError("提交后缓存顺序校验失败")

    def commit(self, candidates: Sequence[OnboardCandidate]) -> OnboardingCommit:
        if not candidates:
            raise OnboardingError("没有可提交的新增站点")
        cache_store = CacheStore(self.cache_path)
        with cache_store._process_lock():
            active = self._load_active()
            old_cache = self._load_cache()
            check = self.evaluate(candidates, active=active, cache=old_cache)
            if check.rejected or len(check.accepted) != len(candidates):
                details = "；".join(
                    f"{name}：{reason}"
                    for name, reason in check.rejected.items()
                )
                if check.duplicate_runs:
                    details += "；判重=" + ";".join(
                        f"{item.candidate_name}/{item.existing_name}:"
                        f"{','.join(item.issues)}"
                        for item in check.duplicate_runs
                    )
                raise OnboardingError("新增门禁未通过：" + details)

            expected_new_ids = self._next_ids(active, len(candidates))
            candidate_ids = tuple(
                candidate.site.target.target_id for candidate in candidates
            )
            if candidate_ids != expected_new_ids:
                raise OnboardingError(
                    "新增 target_id 必须从当前最大编号连续递增："
                    f"应为{','.join(expected_new_ids)}，实际{','.join(candidate_ids)}"
                )

            values_by_name: dict[str, dict[str, str]] = {}
            for candidate in candidates:
                values_by_name[candidate.site.target.name] = normalize_values(
                    candidate.values
                )

            all_sites = sorted(
                list(active) + [candidate.site for candidate in candidates],
                key=lambda site: site.target.target_id,
            )
            expected_ids = tuple(site.target.target_id for site in all_sites)
            cache_payload = self._build_cache_payload(
                active,
                candidates,
                values_by_name,
                old_cache,
            )

            with tempfile.TemporaryDirectory(
                prefix=".onboard-",
                dir=self.project_dir,
            ) as stage_name:
                stage = Path(stage_name)
                stage_sites = stage / "config" / "sites"
                stage_sites.mkdir(parents=True, exist_ok=True)
                for path in self.config_dir.glob("PT-*.json"):
                    shutil.copy2(path, stage_sites / path.name)
                for candidate in candidates:
                    payload = _site_payload(
                        candidate.site,
                        candidate.evidence,
                    )
                    _atomic_write_json(
                        stage_sites / f"{candidate.site.target.target_id}.json",
                        payload,
                    )
                stage_targets = stage / "targets.json"
                compile_site_configs(stage_sites, stage_targets)
                stage_cache = stage / "recent_10_cache.json"
                _atomic_write_json(stage_cache, cache_payload)

                old_targets_bytes = self.targets_path.read_bytes()
                old_cache_bytes = self.cache_path.read_bytes()
                written_site_paths: list[Path] = []
                try:
                    self.config_dir.mkdir(parents=True, exist_ok=True)
                    for candidate in candidates:
                        destination = self.config_dir / (
                            f"{candidate.site.target.target_id}.json"
                        )
                        _atomic_write_json(
                            destination,
                            _site_payload(candidate.site, candidate.evidence),
                        )
                        written_site_paths.append(destination)
                    _atomic_write_json(
                        self.targets_path,
                        json.loads(stage_targets.read_text(encoding="utf-8")),
                    )
                    _atomic_write_json(self.cache_path, cache_payload)
                    self._verify_commit(expected_ids)
                except Exception:
                    for path in written_site_paths:
                        if path.exists():
                            path.unlink()
                    _atomic_write_bytes(self.targets_path, old_targets_bytes)
                    _atomic_write_bytes(self.cache_path, old_cache_bytes)
                    raise

        return OnboardingCommit(
            target_ids=expected_new_ids,
            cache_issues=tuple(str(item) for item in cache_payload["issues"]),
        )
