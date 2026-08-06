from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pingte.domain.models import Target, ValidatedResult
from pingte.validation.identity import target_cache_key


@dataclass(frozen=True)
class CacheUpdateOutcome:
    ok: bool
    message: str = ""


class CacheStore:
    def __init__(self, path: Path, window_size: int = 10) -> None:
        self.path = Path(path)
        self.window_size = max(1, int(window_size))
        self._thread_lock = threading.Lock()

    @contextmanager
    def _process_lock(self):
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def load_strict(self) -> dict:
        """Read the cache without converting corruption into an empty cache."""
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise ValueError(
                f"recent_10_cache.json 读取失败：{type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError("recent_10_cache.json 格式无效")
        return value

    @staticmethod
    def _entry_key(entry: dict) -> tuple[str, str, str, str]:
        return (
            str(entry.get("url", "")),
            str(entry.get("name", "")),
            str(entry.get("position", "")),
            str(entry.get("keyword", "")),
        )

    def update(
        self,
        results: Iterable[ValidatedResult],
        targets: Iterable[Target],
        issue: str,
    ) -> CacheUpdateOutcome:
        normalized_issue = str(int(issue))
        validated = list(results)
        if any(item.issue != normalized_issue for item in validated):
            return CacheUpdateOutcome(False, "缓存候选包含与指定期数不一致的结果")
        by_key: dict[tuple[str, str, str, str], str] = {}
        for item in validated:
            key = target_cache_key(item.target)
            old = by_key.get(key)
            if old and old != item.candidate.zodiac:
                return CacheUpdateOutcome(False, "同一期同目录出现不同缓存候选")
            by_key[key] = item.candidate.zodiac

        with self._thread_lock:
            with self._process_lock():
                return self._update_locked(list(targets), by_key, normalized_issue)

    def update_values(
        self,
        targets: Iterable[Target],
        values_by_key: dict[tuple[str, str, str, str], str],
        issue: str,
    ) -> CacheUpdateOutcome:
        normalized_issue = str(int(issue))
        with self._thread_lock:
            with self._process_lock():
                return self._update_locked(
                    list(targets),
                    {
                        key: str(value)
                        for key, value in values_by_key.items()
                        if str(value).strip()
                    },
                    normalized_issue,
                )

    def _update_locked(
        self,
        targets: list[Target],
        values_by_key: dict[tuple[str, str, str, str], str],
        issue: str,
    ) -> CacheUpdateOutcome:
        if self.path.exists():
            try:
                old_cache = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                return CacheUpdateOutcome(
                    False,
                    f"recent_10_cache.json 读取失败，原缓存已保留：{type(exc).__name__}: {exc}",
                )
            if not isinstance(old_cache, dict):
                return CacheUpdateOutcome(
                    False,
                    "recent_10_cache.json 格式无效，原缓存已保留",
                )
        else:
            old_cache = {}
        old_entries = old_cache.get("sites") if isinstance(old_cache, dict) else []
        if not isinstance(old_entries, list):
            old_entries = []
        old_by_key = {
            self._entry_key(entry): entry
            for entry in old_entries
            if isinstance(entry, dict)
        }
        current_entries: list[dict] = []
        known_issues: set[int] = {int(issue)}
        for target in targets:
            key = target_cache_key(target)
            old_entry = old_by_key.get(key, {})
            old_values = old_entry.get("values", {}) if isinstance(old_entry, dict) else {}
            values = {
                str(item_key): str(value)
                for item_key, value in (old_values or {}).items()
                if str(item_key).isdigit() and str(value).strip()
            }
            new_value = values_by_key.get(key)
            old_value = values.get(issue, "")
            if new_value and old_value and new_value != old_value:
                return CacheUpdateOutcome(
                    False,
                    f"历史缓存同一期数据冲突：缓存{old_value}，当前{new_value}；历史解析错误或源站内容变更待确认",
                )
            if new_value:
                values[issue] = new_value
            known_issues.update(int(item_key) for item_key in values if item_key.isdigit())
            current_entries.append(
                {
                    "target_id": target.target_id,
                    "name": target.name,
                    "url": target.url,
                    "position": target.position,
                    "keyword": target.keyword,
                    "values": values,
                }
            )
        keep_issues = sorted(known_issues, reverse=True)[: self.window_size]
        keep_keys = {str(item) for item in keep_issues}
        for entry in current_entries:
            entry["values"] = {
                key: value
                for key, value in sorted(
                    entry["values"].items(),
                    key=lambda item: int(item[0]),
                    reverse=True,
                )
                if key in keep_keys
            }
        payload = {
            "schema": 1,
            "description": "平特肖重复检测最近10期基准数据；由每日指定期抓取自动覆盖更新。",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "window_size": self.window_size,
            "issues": keep_issues,
            "sites": current_entries,
        }
        try:
            self._atomic_json(payload)
        except Exception as exc:
            return CacheUpdateOutcome(
                False,
                f"recent_10_cache.json 更新失败，原缓存已保留：{type(exc).__name__}: {exc}",
            )
        return CacheUpdateOutcome(True)

    def _atomic_json(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
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

    def cached_target_value(
        self,
        target: Target,
        issue: str,
        *,
        cache: dict | None = None,
    ) -> str:
        key = target_cache_key(target)
        selected_cache = self.load() if cache is None else cache
        for entry in selected_cache.get("sites", []):
            if isinstance(entry, dict) and self._entry_key(entry) == key:
                values = entry.get("values", {})
                return str(values.get(str(int(issue)), "")) if isinstance(values, dict) else ""
        return ""

    def issue_keys(self, limit: int | None = None) -> list[str]:
        issues = {int(item) for item in self.load().get("issues", []) if str(item).isdigit()}
        values = [str(item) for item in sorted(issues, reverse=True)]
        return values if limit is None else values[:limit]

    def validate_candidate_latest_two(self, candidate_values: dict[str, str]) -> CacheUpdateOutcome:
        issue_keys = self.issue_keys(2)
        normalized = {
            str(key): str(value)
            for key, value in candidate_values.items()
            if str(key).isdigit() and str(value).strip()
        }
        if not issue_keys:
            return CacheUpdateOutcome(False, "recent_10_cache.json 没有基准期数，不能验证新增站点")
        if any(item in normalized for item in issue_keys):
            return CacheUpdateOutcome(True)
        return CacheUpdateOutcome(
            False,
            f"候选站没有抓到缓存最新近2期（{'、'.join(item + '期' for item in issue_keys)}）中的任意一期，不能视为有效",
        )

    def find_duplicates(self, candidate_values: dict[str, str]) -> list[dict]:
        normalized = {
            str(key): str(value)
            for key, value in candidate_values.items()
            if str(key).isdigit() and str(value).strip()
        }
        issue_keys = [item for item in self.issue_keys() if item in normalized]
        if not issue_keys:
            return []
        matches: list[dict] = []
        for entry in self.load().get("sites", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("values"), dict):
                continue
            common = [item for item in issue_keys if str(entry["values"].get(item, "")).strip()]
            if common and tuple(str(entry["values"][item]) for item in common) == tuple(normalized[item] for item in common):
                matches.append(entry)
        return matches
