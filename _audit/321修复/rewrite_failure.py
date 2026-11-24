"""用官方 write_failure_output 重建失败清单（只保留仍未修复的站点），保证分类文案一致。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")
from repair import scoped_pipeline, OUT_DIR
from pingte.fetch.http_fetcher import FetchSession
from pingte.storage.output import write_failure_output

LABEL, ISSUE = "11.21", "324"
NAMES = sys.argv[1:]
runtime, subset, pipeline = scoped_pipeline(NAMES)
results = pipeline.run(ISSUE, 30, session=FetchSession())
failures = []
for item in results:
    if item.outcome and item.outcome.ok:
        print("意外成功：", item.target.name, item.outcome.result.candidate.zodiac)
        continue
    if item.outcome and item.outcome.failure:
        failures.append(item.outcome.failure)
    else:
        print("无 failure 对象：", item.target.name, item.error)
path = OUT_DIR / f"{LABEL}平特肖-失败.txt"
write_failure_output(path, failures)
print("失败条数", len(failures), "已写", path)
print(path.read_text(encoding="utf-8"))
