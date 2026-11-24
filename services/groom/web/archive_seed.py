"""The script that gives the book an archived run: groom's own code freezes a run it holds
spans, a failed step and two turn transcripts for, so the files are the ones groom writes."""

SEED = '''
import json
import shutil
import sys
import time
from datetime import UTC, datetime

from groom import archive, store, turns

run, gone = sys.argv[1], sys.argv[2] == "gone"
session = "sess-1"
first, second = "001-00001-document-story", "001-00002-qa-story"
base = time.time() - 4000.0


def span(span_id, parent, node, name, at, seconds, attrs, status="OK"):
    return {
        "span_id": span_id, "trace_id": "t1", "parent_id": parent, "run_id": run, "workflow": "coder",
        "repo": "acme", "branch": "story/acme-sign-in", "node": node, "name": name,
        "run_dir": "/workspace/.agents/runs/" + run, "start_ts": at, "end_ts": at + seconds,
        "status": status, "attrs": attrs, "resume_generation": 1,
    }


def turn_attrs(slug, activity, cost, tokens):
    return {
        "workhorse.visit.slug": slug, "session.id": session + "-" + slug[:9], "work_id": "sign-in-with-a-code",
        "model": "claude-sonnet-5", "activity": activity, "usage.output_tokens": tokens,
        "usage.cache_read_input_tokens": 2100000, "total_cost_usd": cost, "backend": "claude",
    }


def record(at, role, content):
    stamp = datetime.fromtimestamp(at, UTC).isoformat()
    return json.dumps({"timestamp": stamp, "type": role, "message": {"role": role, "content": content}}) + "\\n"


state = {"workhorse.span_kind": "state", "workhorse.depth": 0}
store.insert_spans([
    span("r1", "", "coder", "run:coder", base, 3900, {}),
    span("f1", "r1", "qa", "qa", base + 1, 3800, {"workhorse.depth": 0}),
    span("s1", "f1", "work", "work", base + 2, 3700, state),
    span("n1", "s1", "document-story", "document-story", base + 3, 600, {"workhorse.depth": 2}),
    span("a1", "n1", "document-story", "agent_turn", base + 10, 120, turn_attrs(first, "Documented the reset email flow.", 1.25, 3100)),
    span("n2", "s1", "qa-story", "qa-story", base + 700, 1500, {"workhorse.depth": 2}),
    span("a2", "n2", "qa-story", "agent_turn", base + 710, 2460, turn_attrs(second, "Stack up on a free port. 7 of 9 pass", 6.12, 21400)),
    span("e1", "n2", "ensure_stack", "ensure_stack", time.time() - 3200, 4, {"error.class": "StackStartFailed", "status_message": "port 5432 is already allocated"}, "ERROR"),
])
indexed = []
for slug, seq, start, message in ((first, 1, base + 10, "Documented the flow."), (second, 2, base + 710, "Port 5432 is held, so I will use a free port.")):
    seen = session + "-" + slug[:9]
    root = turns.transcripts_root() / run / (slug + "__" + seen)
    root.mkdir(parents=True, exist_ok=True)
    tool = {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": "make up"}}
    (root / "transcript.jsonl").write_text(record(start + 1, "assistant", message) + record(start + 2, "assistant", [tool]))
    indexed.append({"run_id": run, "node": slug.split("-", 2)[2], "session_id": seen, "generation": 1, "seq": seq, "ts": start, "path": run + "/" + slug + "__" + seen})
store.insert_turns(indexed)
at = time.time() - 3200
store.insert_logs([{"run_id": run, "node": "lint", "severity": "INFO", "body": f"line {number}", "ts": at + 10 + number * 0.01} for number in range(260)])
store.insert_metrics([{"run_id": run, "name": "workhorse.gas", "ts": at + 20 + number, "value": float(number), "attrs": {"node": "lint"}} for number in range(3)])
with store.STORE.writing() as conn:
    conn.execute("UPDATE spans SET attrs_json = ? WHERE run_id = ? AND span_id = 'r1'", ('{"workhorse.terminal": "terminal"}', run))
destination, _ = archive.archive_run(store.run_bounds()[run], time.time())
if destination is None:
    raise SystemExit("the run was not archived")
if gone:
    shutil.rmtree(destination)
'''
