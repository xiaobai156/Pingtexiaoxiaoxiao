import argparse
import re
import sys
from pathlib import Path

from tests.compat import zodiac_scraper
from tests.compat.zodiac_scraper import OUTPUT_DIR, TARGETS, Target


def parse_success_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        if line == "排行榜":
            break
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            names.add(parts[1])
    return names


def parse_failure_reasons(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    reasons: dict[tuple[str, str], str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        name_match = re.search(r"目录：([^，]+)", line)
        url_match = re.search(r"网址：([^，]+)", line)
        if name_match and url_match:
            reasons[(name_match.group(1), url_match.group(1))] = line
    return reasons


def build_multi_failure_summary(
    issues: list[str],
    targets: list[Target],
    issue_results: dict[str, dict[str, Path]],
    issue_errors: dict[str, str] | None = None,
) -> str:
    success_by_issue = {
        issue: parse_success_names(paths["success"])
        for issue, paths in issue_results.items()
    }
    failure_by_issue = {
        issue: parse_failure_reasons(paths["failure"])
        for issue, paths in issue_results.items()
    }
    failed_targets = []
    for target in targets:
        identity = (target.name, target.url)
        passed = any(
            target.name in success_by_issue.get(issue, set())
            and identity not in failure_by_issue.get(issue, {})
            for issue in issues
        )
        if not passed:
            failed_targets.append(target)

    lines = [
        "多期平特一肖失败汇总",
        f"期数：{' '.join(issues)}",
        f"总目录：{len(targets)}",
        f"任意一期通过：{len(targets) - len(failed_targets)}",
        f"全部失败目录数：{len(failed_targets)}",
        "",
    ]
    if issue_errors:
        lines.append("程序错误：")
        for issue in issues:
            if issue in issue_errors:
                lines.append(f"{issue}期：{issue_errors[issue]}")
        lines.append("")
    for target in failed_targets:
        lines.append(
            f"{target.name} | 网址：{target.url} | 位置：{target.position} | 关键字：{target.keyword}"
        )
        for issue in issues:
            reason = failure_by_issue.get(issue, {}).get((target.name, target.url))
            lines.append(f"{issue}期：{reason or '该期没有成功记录，也没有找到明确失败原因'}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def issue_output_paths(issue: str) -> dict[str, Path]:
    success = OUTPUT_DIR / f"{issue}期平特一肖.txt"
    return {
        "success": success,
        "failure": success.with_suffix(".errors.txt"),
    }


def run_multi(issues: list[str], timeout: int) -> int:
    issue_results: dict[str, dict[str, Path]] = {}
    issue_errors: dict[str, str] = {}
    return_codes: list[int] = []
    program_error = False
    fetch_session = zodiac_scraper.FetchSession()
    for issue in issues:
        paths = issue_output_paths(issue)
        issue_results[issue] = paths
        paths["success"].parent.mkdir(parents=True, exist_ok=True)
        zodiac_scraper.atomic_write_text(paths["success"], "")
        zodiac_scraper.atomic_write_text(paths["failure"], "")
        print(f"开始多期抓取：{issue}期", flush=True)
        try:
            code = zodiac_scraper.run(
                issue,
                paths["success"],
                timeout,
                update_cache=False,
                fetch_session=fetch_session,
            )
        except Exception as exc:
            program_error = True
            code = 2
            issue_errors[issue] = f"{type(exc).__name__}: {exc}"
            print(f"{issue}期程序错误：{issue_errors[issue]}", file=sys.stderr, flush=True)
        if code not in (0, 1):
            program_error = True
        return_codes.append(code)

    summary = build_multi_failure_summary(issues, TARGETS, issue_results, issue_errors)
    summary_name = f"多期{'_'.join(issues)}平特一肖-失败汇总.txt"
    summary_path = OUTPUT_DIR / summary_name
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    zodiac_scraper.atomic_write_text(summary_path, summary)
    print(f"多期失败汇总：{summary_path}", flush=True)
    if program_error:
        return 2
    return 1 if all(code != 0 for code in return_codes) else 0


def normalize_issues(values: list[str]) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in re.split(r"[\s,，]+", value.strip()):
            if not item:
                continue
            if not re.fullmatch(r"\d{1,3}", item):
                raise ValueError(f"期数必须是数字：{item}")
            issue = str(int(item))
            if issue not in seen:
                seen.add(issue)
                issues.append(issue)
    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="多期抓取：任意一期成功即通过，并输出全部失败目录汇总")
    parser.add_argument("issues", nargs="*", help="期数，例如：187 188 189 190")
    parser.add_argument("--timeout", type=int, default=15, help="单个网页超时时间，秒")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_issues = args.issues
    if not raw_issues:
        entered = input("Input issue numbers, for example 187 188 189: ").strip()
        raw_issues = [entered]
    try:
        issues = normalize_issues(raw_issues)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not issues:
        print("No issue number entered.", file=sys.stderr)
        return 2
    return run_multi(issues, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
