"""The by-node dataset export: the transpose of the archive, materialized on demand.

What is asserted here is mostly *shape* — a dataset consumer reads these files without a
human in the loop, so a field that quietly changed name is a silent corpus regression.
The other half is that classification comes from the index and is exact: no heading
regex, and therefore no bucket of sessions nobody can attribute to a node.

Run: uv run pytest tests/test_export.py
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from groom import export, store, turns


@contextlib.contextmanager
def _archive() -> Iterator[Path]:
    """A throwaway groom.db with two archived turns of one node and one of another."""
    with tempfile.TemporaryDirectory() as tmp:
        previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(tmp) / "groom.db")
        store.reset()
        try:
            root = turns.transcripts_root()
            rows = []
            for generation, seq, node, session, source in (
                (1, 1, "plan-qa", "s1", "store"),
                (1, 2, "plan-qa", "s2", "tee"),
                (1, 3, "write-docs", "s3", ""),
            ):
                relative = f"R1/{generation:03d}-{seq:05d}-{node}__{session}"
                record = root / relative
                record.mkdir(parents=True)
                (record / "transcript.jsonl").write_text(
                    json.dumps({"cwd": "/workspace/acme", "message": {"role": "user", "content": "go"}})
                    + "\n"
                    + json.dumps(
                        {"message": {"role": "assistant", "content": "ok", "model": "acme-model"}}
                    )
                    + "\n"
                    + json.dumps({"type": "attachment", "path": "a.png"})  # not a message
                    + "\n{ this line never parses\n",
                    encoding="utf-8",
                )
                (record / "prompt.md").write_text("do it", encoding="utf-8")
                rows.append(
                    {
                        "run_id": "R1", "workflow": "coder", "flow": "main", "node": node,
                        "session_id": session, "generation": generation, "seq": seq,
                        "ts": 1000.0 + seq, "backend": "acme-cli", "source": source,
                        "path": relative, "bytes": 10, "sha256": f"d{seq}", "head": "aaa111",
                    }
                )
            store.insert_turns(rows)
            yield Path(tmp)
        finally:
            store.reset()
            if previous is None:
                os.environ.pop("GROOM_DB", None)
            else:
                os.environ["GROOM_DB"] = previous


def _read(target: Path, relative: str) -> dict:
    return json.loads((target / relative).read_text(encoding="utf-8"))


def test_the_layout_is_workflow_then_node_then_session():
    """The transpose of the archive: every session that ran a node, in one directory, so
    a prompt edit can be evaluated against all of them at once."""
    with _archive() as tmp:
        target = tmp / "dataset"
        result = export.export_by_node(target)

        assert result["sessions"] == 3
        written = sorted(p.relative_to(target).as_posix() for p in target.rglob("*.json"))
        assert written == [
            "INDEX.json",
            "coder/plan-qa/store__s1.json",
            "coder/plan-qa/tee__s2.json",
            "coder/write-docs/unknown__s3.json",
        ]
        assert not list(target.rglob("*.part"))  # nothing half-written left behind


def test_a_session_carries_the_fields_the_dataset_reads():
    with _archive() as tmp:
        target = tmp / "dataset"
        export.export_by_node(target)
        session = _read(target, "coder/plan-qa/store__s1.json")

    assert session["task"] == "plan-qa"  # from the index join, not from the prompt text
    assert session["source"] == "store"
    assert session["session_id"] == "s1"
    assert session["cwd"] == "/workspace/acme"
    assert session["model"] == "acme-model"
    assert session["time_created"].startswith("19") or session["time_created"].startswith("20")
    assert session["n_messages"] == 2
    assert [m["role"] for m in session["messages"]] == ["user", "assistant"]
    assert session["head"] == "aaa111"


def test_a_non_message_line_and_a_broken_line_are_not_messages():
    """A capture truncated at a byte cap ends mid-line by construction, and a session
    store holds attachments and queue records beside the conversation. Neither is a
    reason to lose the session."""
    with _archive() as tmp:
        target = tmp / "dataset"
        export.export_by_node(target)
        session = _read(target, "coder/plan-qa/tee__s2.json")

    assert session["n_messages"] == 2
    assert all("role" in message for message in session["messages"])


def test_the_index_names_every_exported_session():
    with _archive() as tmp:
        target = tmp / "dataset"
        export.export_by_node(target)
        index = _read(target, "INDEX.json")

    assert index["sessions"] == 3
    assert sorted(record["path"] for record in index["records"]) == [
        "coder/plan-qa/store__s1.json",
        "coder/plan-qa/tee__s2.json",
        "coder/write-docs/unknown__s3.json",
    ]
    assert all(record["has_prompt"] for record in index["records"])
    assert {record["task"] for record in index["records"]} == {"plan-qa", "write-docs"}


def test_a_filter_narrows_the_export_to_one_node():
    with _archive() as tmp:
        target = tmp / "dataset"
        result = export.export_by_node(target, node="write-docs")

        assert result["sessions"] == 1
        assert not (target / "coder" / "plan-qa").exists()


def test_a_record_whose_bodies_are_gone_still_exports():
    """Dropping it would make the export disagree with `transcript ls` about how many
    times a node ran — which is the number the thrashing question turns on."""
    with _archive() as tmp:
        import shutil

        shutil.rmtree(turns.transcripts_root() / "R1/001-00001-plan-qa__s1")
        target = tmp / "dataset"
        export.export_by_node(target)
        session = _read(target, "coder/plan-qa/store__s1.json")

    assert session["n_messages"] == 0
    assert session["messages"] == []


def test_a_hostile_node_name_cannot_escape_the_target_directory():
    """Node and workflow names are engine data, not attacker data — but they are
    free-form, and one containing a slash would write outside the tree the caller named."""
    with _archive() as tmp:
        store.insert_turns([
            {
                "run_id": "R1", "workflow": "../../etc", "flow": "main", "node": "a/b",
                "session_id": "s9", "generation": 2, "seq": 1, "ts": 1010.0,
                "backend": "acme-cli", "source": "store", "path": "R1/missing",
                "bytes": 0, "sha256": "d9", "head": None,
            }
        ])
        target = tmp / "dataset"
        export.export_by_node(target)

        assert (target / "etc" / "a_b" / "store__s9.json").is_file()
        assert not (tmp / "etc").exists()


if __name__ == "__main__":
    import sys
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    sys.exit(1 if failures else 0)
