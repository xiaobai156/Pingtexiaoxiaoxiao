from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pingte.application.runtime import build_runtime


def parse_issue(value: str) -> str:
    issue = value.strip()
    if not re.fullmatch(r"\d{1,3}", issue):
        raise ValueError("期数必须是数字，例如：164")
    return str(int(issue))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按手动指定期数抓取平特肖")
    parser.add_argument("issue", nargs="?", help="期数，例如 164")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--no-cache-update", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("-o", "--output", help="自定义成功TXT路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_issue = args.issue
    if raw_issue is None:
        raw_issue = input("请输入期数，例如 164：").strip()
    try:
        issue = parse_issue(raw_issue)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    runtime = build_runtime(Path(__file__).resolve().parent)
    runner = runtime.single_runner()
    success_path = Path(args.output) if args.output else None
    failure_path = None
    if success_path:
        failure_path = success_path.with_name(
            f"{success_path.stem}-失败{success_path.suffix}"
        )
    outcome = runner.run(
        issue,
        args.timeout,
        update_cache=not args.no_cache_update,
        audit=args.audit,
        success_path=success_path,
        failure_path=failure_path,
    )
    return outcome.return_code


if __name__ == "__main__":
    raise SystemExit(main())
