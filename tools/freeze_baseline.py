import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": file_sha256(resolved),
    }


def result_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line == "排行榜":
            break
        if line:
            lines.append(line)
    return lines


def nonempty_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def success_target_names(lines: list[str]) -> list[str]:
    names: list[str] = []
    for line in lines:
        _zodiac, separator, name = line.partition(" ")
        if not separator or not name.strip():
            raise ValueError(f"成功行格式无效：{line}")
        names.append(name.strip())
    return names


def failure_target_names(lines: list[str]) -> list[str]:
    return [
        match.group(1).strip()
        for line in lines
        if (match := re.search(r"目录：([^，\r\n]+)", line))
    ]


def validate_run_coverage(
    config: dict,
    success_lines: list[str],
    failure_lines: list[str],
) -> dict[str, int]:
    target_names = [str(item.get("name", "")).strip() for item in config.get("targets", [])]
    success_names = success_target_names(success_lines)
    failure_names = failure_target_names(failure_lines)
    duplicate_success = sorted(
        name for name in set(success_names) if success_names.count(name) > 1
    )
    if duplicate_success:
        raise ValueError("成功文件存在重复目录：" + "、".join(duplicate_success))
    overlap = sorted(set(success_names) & set(failure_names))
    if overlap:
        raise ValueError("目录同时出现在成功和失败：" + "、".join(overlap))
    configured = set(target_names)
    covered = set(success_names) | set(failure_names)
    unknown = sorted(covered - configured)
    if unknown:
        raise ValueError("输出包含未配置目录：" + "、".join(unknown))
    missing = sorted(configured - covered)
    if missing:
        raise ValueError("输出缺少目录：" + "、".join(missing))
    return {
        "target_count": len(target_names),
        "success_target_count": len(success_names),
        "failure_target_count": len(set(failure_names)),
    }


def build_manifest(
    *,
    issue: str,
    config_path: Path,
    cache_path: Path,
    success_path: Path,
    failure_path: Path,
    test_summary: str,
    compile_summary: str,
    created_at: str | None = None,
) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    success_lines = result_lines(success_path)
    failure_lines = nonempty_lines(failure_path)
    coverage_summary = validate_run_coverage(config, success_lines, failure_lines)
    cache_issue_values = [
        {"name": str(site.get("name", "")), "value": str(site.get("values", {}).get(issue, ""))}
        for site in cache.get("sites", [])
        if str(site.get("values", {}).get(issue, ""))
    ]
    return {
        "schema_version": 1,
        "issue": str(int(issue)),
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "config_summary": {
            "target_count": len(config.get("targets", [])),
            "dedicated_rule_count": len(config.get("special_parse_targets", [])),
        },
        "coverage_summary": coverage_summary,
        "success_lines": success_lines,
        "failure_lines": failure_lines,
        "cache_issue_values": cache_issue_values,
        "files": {
            "config": file_record(config_path),
            "cache": file_record(cache_path),
            "success": file_record(success_path),
            "failure": file_record(failure_path),
        },
        "verification": {
            "tests": test_summary,
            "py_compile": compile_summary,
        },
    }


def atomic_write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze one verified issue as a refactor baseline")
    parser.add_argument("--issue", required=True)
    parser.add_argument("--success", required=True, type=Path)
    parser.add_argument("--failure", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", default=Path("targets.json"), type=Path)
    parser.add_argument("--cache", default=Path("recent_10_cache.json"), type=Path)
    parser.add_argument("--tests", required=True)
    parser.add_argument("--compile", dest="compile_summary", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(
        issue=args.issue,
        config_path=args.config,
        cache_path=args.cache,
        success_path=args.success,
        failure_path=args.failure,
        test_summary=args.tests,
        compile_summary=args.compile_summary,
    )
    atomic_write_json(args.manifest, manifest)
    print(
        f"基线已冻结：{args.manifest}，"
        f"成功 {len(manifest['success_lines'])} 条，失败 {len(manifest['failure_lines'])} 条。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
