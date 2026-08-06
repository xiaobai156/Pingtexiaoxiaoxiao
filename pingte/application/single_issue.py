from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.models import RunResult, Target, ValidatedResult
from pingte.storage.cache import CacheStore, CacheUpdateOutcome
from pingte.storage.evidence import EvidenceStore
from pingte.storage.output import (
    atomic_write_text,
    build_output,
    build_failure_output,
    date_label,
    default_output_paths,
)
from pingte.validation.identity import target_cache_key

from .site_pipeline import PipelineTargetResult, SitePipeline


@dataclass(frozen=True)
class SingleRunOutcome:
    return_code: int
    run_result: RunResult
    success_path: Path
    failure_path: Path
    evidence_path: Path | None = None
    cache_update: CacheUpdateOutcome | None = None


class SingleIssueRunner:
    def __init__(
        self,
        targets: Iterable[Target],
        pipeline: SitePipeline,
        *,
        cache_store: CacheStore,
        output_dir: Path,
        evidence_dir: Path,
        today: date | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.targets = tuple(targets)
        self.pipeline = pipeline
        self.cache_store = cache_store
        self.output_dir = Path(output_dir)
        self.evidence_dir = Path(evidence_dir)
        self.today = today
        self.log = log or (lambda message: print(message, flush=True))

    @staticmethod
    def _fetch_failure(item: PipelineTargetResult, issue: str) -> FailureDetail:
        code = FailureCode.WEB_FETCH_FAILED
        prefix = "浏览器DOM抓取失败" if item.used_browser else "网页抓取失败"
        return FailureDetail(
            code=code,
            message=f"{prefix}：{item.error or '没有返回正文'}",
            target_id=item.target.target_id,
            name=item.target.name,
            url=item.target.url,
            position=item.target.position,
            keyword=item.target.keyword,
            issue=str(int(issue)),
        )

    def _failure_for_item(self, item: PipelineTargetResult, issue: str) -> FailureDetail | None:
        if item.error:
            return self._fetch_failure(item, issue)
        if item.outcome is None:
            return FailureDetail(
                FailureCode.INTERNAL_ERROR,
                "流水线没有返回校验结果",
                item.target.target_id,
                item.target.name,
                item.target.url,
                item.target.position,
                item.target.keyword,
                str(int(issue)),
            )
        return item.outcome.failure

    def _cache_conflicts(
        self,
        successes: list[ValidatedResult],
        issue: str,
    ) -> tuple[list[ValidatedResult], list[FailureDetail], bool]:
        try:
            history = self.cache_store.load_strict()
        except ValueError as exc:
            return successes, [
                FailureDetail(
                    FailureCode.CACHE_UPDATE_FAILED,
                    f"{exc}；原缓存已保留",
                    "",
                    "全站缓存",
                    str(self.cache_store.path),
                    "",
                    "",
                    issue,
                )
            ], True

        conflicts: list[FailureDetail] = []
        conflict_keys: set[tuple[str, str, str, str]] = set()
        for result in successes:
            cached = self.cache_store.cached_target_value(
                result.target,
                issue,
                cache=history,
            )
            if not cached or cached == result.candidate.zodiac:
                continue
            conflict_keys.add(target_cache_key(result.target))
            conflicts.append(
                FailureDetail(
                    FailureCode.SOURCE_CONFLICT,
                    f"历史缓存同一期数据冲突：缓存{cached}，当前{result.candidate.zodiac}；"
                    "历史解析错误或源站内容变更待确认",
                    result.target.target_id,
                    result.target.name,
                    result.target.url,
                    result.target.position,
                    result.target.keyword,
                    issue,
                    result.candidate.raw_line,
                )
            )
        if conflicts:
            return [
                result
                for result in successes
                if target_cache_key(result.target) not in conflict_keys
            ], conflicts, True
        return successes, [], False

    def run(
        self,
        issue: str,
        timeout: int,
        *,
        update_cache: bool = True,
        audit: bool = False,
        session: object = None,
        success_path: Path | None = None,
        failure_path: Path | None = None,
    ) -> SingleRunOutcome:
        normalized_issue = str(int(issue))
        default_success, default_failure = default_output_paths(
            normalized_issue,
            output_dir=self.output_dir,
            today=self.today,
        )
        success_path = Path(success_path or default_success)
        failure_path = Path(failure_path or default_failure)
        self.log(
            f"开始抓取 {normalized_issue} 期，共 {len(self.targets)} 个目录。"
        )
        pipeline_results = self.pipeline.run(
            normalized_issue,
            timeout,
            session=session,
        )
        successes: list[ValidatedResult] = []
        failures: list[FailureDetail] = []
        for index, item in enumerate(pipeline_results, start=1):
            if item.outcome is not None and item.outcome.ok and item.outcome.result:
                successes.append(item.outcome.result)
            else:
                failure = self._failure_for_item(item, normalized_issue)
                if failure is not None:
                    failures.append(failure)
            self.log(
                f"[进度 {index}/{len(pipeline_results)}] 成功 {len(successes)} "
                f"失败 {len(failures)} 当前：{item.target.name}"
            )

        cache_update: CacheUpdateOutcome | None = None
        evidence_path: Path | None = None
        cache_blocked = False
        if audit or update_cache:
            successes, cache_failures, cache_blocked = self._cache_conflicts(
                successes,
                normalized_issue,
            )
            failures.extend(cache_failures)
        if not audit:
            if successes:
                evidence_path = self.evidence_dir / (
                    f"{date_label(self.today)}-{normalized_issue}期.json"
                )
                EvidenceStore(evidence_path).write(normalized_issue, successes)

            atomic_write_text(
                success_path,
                build_output(
                    f"{item.candidate.zodiac} {item.target.name}"
                    for item in successes
                ),
            )
            atomic_write_text(
                failure_path,
                build_failure_output(failures),
            )

            if update_cache and not cache_blocked:
                cache_update = self.cache_store.update(
                    successes,
                    self.targets,
                    normalized_issue,
                )
                if not cache_update.ok:
                    failures.append(
                        FailureDetail(
                            FailureCode.CACHE_UPDATE_FAILED,
                            cache_update.message,
                            "",
                            "全站缓存",
                            str(self.cache_store.path),
                            "",
                            "",
                            normalized_issue,
                        )
                    )
                    atomic_write_text(
                        failure_path,
                        build_failure_output(failures),
                    )
            elif update_cache and cache_blocked:
                cache_update = CacheUpdateOutcome(
                    False,
                    "历史缓存冲突或损坏，已停止缓存写入",
                )
            else:
                self.log("最近10期缓存：已跳过更新")
        else:
            for failure in failures:
                self.log("审计失败：" + failure.render())
            self.log(
                f"审计完成：成功 {len(successes)} 条，失败 {len(failures)} 条；"
                "未写入缓存、TXT或证据。"
            )

        run_result = RunResult(
            issue=normalized_issue,
            successes=tuple(successes),
            failures=tuple(failures),
        )
        return SingleRunOutcome(
            return_code=0 if successes else 1,
            run_result=run_result,
            success_path=success_path,
            failure_path=failure_path,
            evidence_path=evidence_path,
            cache_update=cache_update,
        )
