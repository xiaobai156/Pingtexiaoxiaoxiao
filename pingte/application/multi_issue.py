from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pingte.domain.models import Target
from pingte.storage.output import atomic_write_text

from .single_issue import SingleIssueRunner, SingleRunOutcome


@dataclass(frozen=True)
class MultiRunOutcome:
    return_code: int
    issue_outcomes: dict[str, SingleRunOutcome]
    summary_path: Path


def normalize_issues(values: Iterable[str]) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in re.split(r"[\s,，]+", str(value).strip()):
            if not item:
                continue
            if not re.fullmatch(r"\d{1,3}", item):
                raise ValueError(f"期数必须是数字：{item}")
            normalized = str(int(item))
            if normalized not in seen:
                seen.add(normalized)
                issues.append(normalized)
    return issues


class MultiIssueRunner:
    def __init__(
        self,
        targets: Iterable[Target],
        single_runner: SingleIssueRunner,
        *,
        output_dir: Path,
        today=None,
        session: object = None,
    ) -> None:
        self.targets = tuple(targets)
        self.single = single_runner
        self.output_dir = Path(output_dir)
        self.today = today
        self.session = session

    @staticmethod
    def _success_ids(outcome: SingleRunOutcome) -> set[str]:
        run_result = outcome.run_result
        explicit = getattr(run_result, "success_target_ids", None)
        if explicit is not None:
            return set(explicit)
        return {item.target.target_id for item in run_result.successes}

    def _summary(
        self,
        issues: list[str],
        outcomes: dict[str, SingleRunOutcome],
        errors: dict[str, str],
    ) -> str:
        success_ids = {
            issue: self._success_ids(outcome)
            for issue, outcome in outcomes.items()
        }
        failed_targets = [
            target
            for target in self.targets
            if not any(target.target_id in success_ids.get(issue, set()) for issue in issues)
        ]
        lines = [
            "多期平特一肖失败汇总",
            f"期数：{' '.join(issues)}",
            f"总目录：{len(self.targets)}",
            f"任意一期通过：{len(self.targets) - len(failed_targets)}",
            f"全部失败目录数：{len(failed_targets)}",
            "",
        ]
        if errors:
            lines.append("程序错误：")
            for issue in issues:
                if issue in errors:
                    lines.append(f"{issue}期：{errors[issue]}")
            lines.append("")
        for target in failed_targets:
            lines.append(
                f"{target.name} | 网址：{target.url} | 位置：{target.position} | 关键字：{target.keyword}"
            )
            for issue in issues:
                outcome = outcomes.get(issue)
                reason = None
                if outcome:
                    reason = next(
                        (
                            failure.render()
                            for failure in outcome.run_result.failures
                            if failure.target_id == target.target_id
                        ),
                        None,
                    )
                lines.append(f"{issue}期：{reason or '该期没有成功记录，也没有找到明确失败原因'}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def run(self, issues: Iterable[str], timeout: int) -> MultiRunOutcome:
        normalized = normalize_issues(list(issues))
        if not normalized:
            raise ValueError("没有指定期数")
        outcomes: dict[str, SingleRunOutcome] = {}
        errors: dict[str, str] = {}
        for issue in normalized:
            success_path = self.output_dir / f"{issue}期平特一肖.txt"
            failure_path = self.output_dir / f"{issue}期平特一肖-失败.txt"
            try:
                outcome = self.single.run(
                    issue,
                    timeout,
                    update_cache=False,
                    session=self.session,
                    success_path=success_path,
                    failure_path=failure_path,
                )
                outcomes[issue] = outcome
            except Exception as exc:
                errors[issue] = f"{type(exc).__name__}: {exc}"
        summary_path = self.output_dir / (
            f"多期{'_'.join(normalized)}平特一肖-失败汇总.txt"
        )
        atomic_write_text(summary_path, self._summary(normalized, outcomes, errors))
        if errors:
            code = 2
        else:
            code = 0 if any(outcome.return_code == 0 for outcome in outcomes.values()) else 1
        return MultiRunOutcome(code, outcomes, summary_path)
