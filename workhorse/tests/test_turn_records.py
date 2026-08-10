"""What a run keeps of each individual visit to a node.

The per-node directory holds one prompt and one output, overwritten on every visit, so by
the time lap 5 of a loop is the one in trouble the prompts that produced laps 1-4 no
longer exist anywhere. They are what an improved prompt would have to be tested against,
so the run keeps a copy of each visit beside them.

    ./.venv/bin/python tests/test_turn_records.py
    ./.venv/bin/python -m pytest tests/test_turn_records.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from workhorse import turnkey
from workhorse.artifacts import ArtifactWriter


def _writer(tmp: str, run_id: str = "t") -> ArtifactWriter:
    return ArtifactWriter("coder", Path(tmp) / "runs", run_id=run_id)


def _turns(writer: ArtifactWriter) -> list[str]:
    root = writer.run_dir / ArtifactWriter.TURNS_DIR
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def test_every_visit_of_a_looping_node_keeps_its_own_prompt():
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        writer = _writer(tmp)

        for lap in range(1, 4):
            turnkey.begin(writer.run_dir, "qa-plan")
            writer.write_step("qa-plan", f"lap {lap}", {"lap": lap}, {}, next_node="done")

        visits = _turns(writer)
        assert len(visits) == 3, visits
        prompts = [
            (writer.run_dir / ArtifactWriter.TURNS_DIR / v / "prompt.md").read_text()
            for v in visits
        ]
        # The whole point: three visits, three *different* prompts still on disk.
        assert prompts == ["lap 1", "lap 2", "lap 3"]


def test_the_per_node_directory_still_holds_the_latest_visit():
    """Additive, not instead-of: resume reads `<run>/<node>/context_after.json`, and
    everything reading a run dir today addresses a node by its id."""
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        writer = _writer(tmp)

        for lap in (1, 2):
            turnkey.begin(writer.run_dir, "qa-plan")
            writer.write_step("qa-plan", f"lap {lap}", {"lap": lap}, {"ctx": lap})

        assert (writer.run_dir / "qa-plan" / "prompt.md").read_text() == "lap 2"
        assert writer.read_output("qa-plan") == {"lap": 2}
        assert writer.read_context_after("qa-plan") == {"ctx": 2}


def test_a_visit_directory_is_named_by_the_visit_key():
    """The same name the session map and the transcript use, which is what lets three
    writers that cannot see each other be assembled into one turn record."""
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        writer = _writer(tmp)
        key = turnkey.begin(writer.run_dir, "implement")

        writer.write_step("implement", "p", {"ok": True}, {})

        assert _turns(writer) == [key.slug]
        kept = writer.run_dir / ArtifactWriter.TURNS_DIR / key.slug
        assert json.loads((kept / "output.json").read_text()) == {"ok": True}
        assert (kept / "context_after.json").exists()


def test_a_branch_records_which_way_this_visit_went():
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        writer = _writer(tmp)
        turnkey.begin(writer.run_dir, "gate")
        writer.write_branch("gate", "verdict", "pass", "publish")
        turnkey.begin(writer.run_dir, "gate")
        writer.write_branch("gate", "verdict", "fail", "repair")

        taken = [
            json.loads((writer.run_dir / ArtifactWriter.TURNS_DIR / v / "branch.json").read_text())[
                "value"
            ]
            for v in _turns(writer)
        ]
        assert taken == ["pass", "fail"]


def test_a_step_written_outside_a_visit_is_not_filed_under_someone_elses():
    """turnkey names *agent* visits. A plain call node writing a step while the last
    agent visit is still current would otherwise put its output in that node's directory,
    where a reader would take it for what the agent answered."""
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        writer = _writer(tmp)
        key = turnkey.begin(writer.run_dir, "implement")
        writer.write_step("implement", "p", {}, {})

        writer.write_step("summarise", "p", {"from": "a call node"}, {})

        assert _turns(writer) == [key.slug]
        assert not (writer.run_dir / ArtifactWriter.TURNS_DIR / key.slug / "branch.json").exists()


def test_a_nested_flows_visits_survive_the_next_entry_to_that_scope():
    """`subscope` empties itself on every entry — one story's Qa flow must not start
    holding the previous story's answers. The visit archive is exactly the thing that
    must NOT be emptied, so it lives at the top of the run rather than in the scope."""
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        parent = _writer(tmp)

        first = parent.subscope("qa", "Qa")
        turnkey.begin(parent.run_dir, "assess")
        first.write_step("assess", "story one", {"verdict": "pass"}, {})

        second = parent.subscope("qa", "Qa")
        turnkey.begin(parent.run_dir, "assess")
        second.write_step("assess", "story two", {"verdict": "fail"}, {})

        assert second.read_output("assess") == {"verdict": "fail"}, "the scope still resets"
        kept = [
            (parent.run_dir / ArtifactWriter.TURNS_DIR / v / "prompt.md").read_text()
            for v in _turns(parent)
        ]
        assert kept == ["story one", "story two"]


def test_keeping_the_copy_never_fails_the_node():
    """Bookkeeping about a run that is doing something else. A turns/ path that cannot be
    created costs the copy and nothing more."""
    turnkey.clear()
    with tempfile.TemporaryDirectory() as tmp:
        writer = _writer(tmp)
        (writer.run_dir / ArtifactWriter.TURNS_DIR).write_text("not a directory")
        turnkey.begin(writer.run_dir, "implement")

        writer.write_step("implement", "p", {"ok": True}, {})

        assert writer.read_output("implement") == {"ok": True}
        assert writer.read_done("implement") is not None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
