"""用当前配置重抓指定站点，把 evidence 中这些站的记录整行替换为最新（含 rule_version）。"""
import json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")
from repair import scoped_pipeline, ROOT, HERE
from pingte.fetch.http_fetcher import FetchSession
from pingte.storage.evidence import EvidenceStore
from pingte.storage.output import atomic_write_text

ISSUE = "324"
NAMES = sys.argv[1:]
runtime, subset, pipeline = scoped_pipeline(NAMES)
results = pipeline.run(ISSUE, 30, session=FetchSession())
fresh = [i.outcome.result for i in results if i.outcome and i.outcome.ok]
missing = [i.target.name for i in results if not (i.outcome and i.outcome.ok)]
tmp = HERE / "delta-refresh.json"
EvidenceStore(tmp).write(ISSUE, fresh)
delta = json.loads(tmp.read_text(encoding="utf-8"))["results"]
path = ROOT.parent / "平特" / "evidence" / f"11.20-{ISSUE}期.json"
payload = json.loads(path.read_text(encoding="utf-8-sig"))
by_id = {row["target_id"]: row for row in delta}
for index, row in enumerate(payload["results"]):
    if row["target_id"] in by_id:
        payload["results"][index] = by_id.pop(row["target_id"])
atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print("替换", len(delta), "条；未取到", missing, "；总", len(payload["results"]))
