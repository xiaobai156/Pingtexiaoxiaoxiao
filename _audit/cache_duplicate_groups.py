"""只读审计：汇报平特缓存窗口内「近 N 期逐期完全一致」的目录组。

用法：python _audit/cache_duplicate_groups.py [项目根]
默认项目根为脚本上一级；不写任何正式文件。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent


def main() -> int:
    cache_path = PROJECT / "recent_10_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    issues = [str(i) for i in cache["issues"]]
    sites = cache["sites"]

    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for site in sites:
        values = site.get("values", {})
        signature = tuple(str(values.get(issue, "")).strip() for issue in issues)
        groups[signature].append(site)

    dup = {sig: members for sig, members in groups.items() if len(members) > 1}
    all_empty = [sig for sig in dup if not any(sig)]

    print(f"项目：{PROJECT}")
    print(f"缓存：{cache_path.name}  updated_at={cache.get('updated_at')}  window={len(issues)}  sites={len(sites)}")
    print(f"期数：{' → '.join([issues[0], issues[-1]])}（{'、'.join(issues)}）")
    print(f"完全一致的目录组：{len(dup)} 组（覆盖 {sum(len(v) for v in dup.values())} 站），其中全空组 {len(all_empty)} 组")
    if not dup:
        print("（无重复组）")
        return 0

    for index, (sig, members) in enumerate(sorted(dup.items(), key=lambda kv: (-len(kv[1]), kv[1][0]["target_id"])), start=1):
        non_empty = sum(1 for value in sig if value)
        print("")
        print(f"组 {index}：{len(members)} 站，非空期数 {non_empty}/{len(issues)}")
        for member in members:
            print(f"   {member['target_id']} {member['name']} | {member['position']} | {member['keyword']} | {member['url']}")
        print("   逐期值：" + " ".join(f"{issue}={value or '空'}" for issue, value in zip(issues, sig)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
