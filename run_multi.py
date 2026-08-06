from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pingte.application.multi_issue import MultiIssueRunner, normalize_issues
from pingte.application.runtime import build_runtime
from pingte.fetch.http_fetcher import FetchSession


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="多期抓取：任意一期成功即通过")
    parser.add_argument("issues", nargs="*", help="期数，例如：187 188 189")
    parser.add_argument("--timeout", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_issues = args.issues
    if not raw_issues:
        raw_issues = [input("请输入期数，例如 187 188 189：").strip()]
    try:
        issues = normalize_issues(raw_issues)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not issues:
        print("必须手动指定至少一个期数", file=sys.stderr)
        return 2

    runtime = build_runtime(Path(__file__).resolve().parent)
    runner = MultiIssueRunner(
        runtime.targets,
        runtime.single_runner(),
        output_dir=runtime.output_dir,
        session=FetchSession(),
    )
    return runner.run(issues, args.timeout).return_code


if __name__ == "__main__":
    raise SystemExit(main())
