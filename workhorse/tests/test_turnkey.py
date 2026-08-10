"""The per-visit identity, and the session map that carries it.

A node visited five times in a loop is the case that matters: without a visit key the
run dir records five turns that all say *this node, some session*, and the one that
thrashed cannot be told from the four that did not.

    ./.venv/bin/python tests/test_turnkey.py
    ./.venv/bin/python -m pytest tests/test_turnkey.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from workhorse import gitstate, turnkey
from workhorse.runner import failure

TIMEOUT = 30.0
HAVE_GIT = shutil.which("git") is not None


def _run_dir() -> Path:
    return Path(tempfile.mkdtemp())


def _repo(path: Path) -> Path:
    """A real repository with one commit — the head stamped on a row is observed, not
    faked, so the row and the tree cannot drift apart in the test but not in the run."""
    path.mkdir(parents=True)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    (path / "file.txt").write_text("one")
    subprocess.run(["git", "-C", str(path), "add", "file.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "one"], check=True, capture_output=True
    )
    return path


def test_a_visit_key_names_the_node_the_generation_and_the_visit():
    turnkey.clear()
    run_dir = _run_dir()
    (run_dir / turnkey.GENERATION_FILE).write_text("3")

    key = turnkey.begin(run_dir, "plan")

    assert (key.generation, key.seq, key.node) == (3, 1, "plan")
    assert turnkey.current() == key


def test_the_slug_sorts_lexically_in_the_order_the_visits_happened():
    turnkey.clear()
    run_dir = _run_dir()
    (run_dir / turnkey.GENERATION_FILE).write_text("1")

    slugs = [turnkey.begin(run_dir, "plan").slug for _ in range(11)]

    # Zero padding is the whole point: unpadded, visit 11 sorts before visit 2 and an
    # `ls` of the run's visits reads in an order they never happened in.
    assert slugs == sorted(slugs)
    assert slugs[0] == "001-00001-plan"
    assert slugs[-1] == "001-00011-plan"


def test_the_counter_survives_a_restart_and_never_repeats_a_visit():
    """Two processes over one run dir must not both call their first visit number 1.

    The generation would separate them — except that it is only bumped when telemetry
    builds, so a run with telemetry off restarts on the same generation. The counter is
    durable for exactly that case.
    """
    turnkey.clear()
    run_dir = _run_dir()
    first = [turnkey.begin(run_dir, "plan").seq for _ in range(3)]

    turnkey.clear()  # a fresh process over the same run dir
    second = [turnkey.begin(run_dir, "plan").seq for _ in range(2)]

    assert first == [1, 2, 3]
    assert second == [4, 5]


def test_a_counter_that_cannot_be_written_still_never_repeats_within_the_run():
    turnkey.clear()
    run_dir = _run_dir()
    (run_dir / turnkey.SEQ_FILE).mkdir()  # a directory where the counter should be

    # A file that cannot be read or written costs durability across restarts, not
    # uniqueness within one — and never an exception, because this is bookkeeping about
    # a run that is doing something else.
    assert [turnkey.begin(run_dir, "plan").seq for _ in range(3)] == [1, 2, 3]


def test_no_run_dir_still_yields_a_key_rather_than_a_failure():
    turnkey.clear()
    key = turnkey.begin(None, "plan")
    assert (key.generation, key.seq, key.node) == (0, 1, "plan")


def test_outside_a_visit_there_is_no_current_key():
    turnkey.clear()
    # None rather than a zeroed key, so a writer stamps nothing rather than stamping
    # `000-00000-` on something no visit produced.
    assert turnkey.current() is None


def test_each_turn_of_a_revisited_node_gets_its_own_addressable_row():
    turnkey.clear()
    run_dir = _run_dir()
    sidp = run_dir / ".session_id"
    (run_dir / turnkey.GENERATION_FILE).write_text("2")

    for session in ("ses_a", "ses_b"):
        turnkey.begin(run_dir, "plan-qa")
        failure.classify_turn(
            "claude",
            "plan-qa",
            result_text="ok",
            diagnostics="",
            timed_out=False,
            returncode=0,
            timeout=TIMEOUT,
            session_id=session,
            session_id_path=sidp,
        )

    rows = [json.loads(x) for x in (run_dir / "sessions.jsonl").read_text().splitlines()]
    assert [(r["generation"], r["seq"], r["node"], r["session_id"]) for r in rows] == [
        (2, 1, "plan-qa", "ses_a"),
        (2, 2, "plan-qa", "ses_b"),
    ]
    assert all(r["backend"] == "claude" for r in rows)
    # (generation, ts) is the order that survives a rewind; ts alone is what places a
    # row against the run's spans without counting lines.
    assert all(isinstance(r["ts"], int) and r["ts"] > 0 for r in rows)


def test_a_turn_outside_the_engines_visit_is_left_unnumbered():
    """A library caller driving the runner directly takes turns the engine never opened.

    Numbering those with whatever key happens to be current would attribute them to
    somebody else's visit, which is worse than leaving them unaddressed.
    """
    turnkey.clear()
    run_dir = _run_dir()
    turnkey.begin(run_dir, "plan")

    failure.record_session_map(run_dir / ".session_id", "some-other-node", "ses_x", "codex")

    row = json.loads((run_dir / "sessions.jsonl").read_text().splitlines()[0])
    assert "seq" not in row and "generation" not in row
    assert (row["node"], row["session_id"]) == ("some-other-node", "ses_x")


def test_a_row_records_the_commit_the_tree_was_on():
    if not HAVE_GIT:
        return
    turnkey.clear()
    run_dir = _run_dir()
    repo = _repo(run_dir / "acme")

    gitstate.bind(repo)
    try:
        failure.record_session_map(run_dir / ".session_id", "plan", "ses_h", "claude")
    finally:
        gitstate.unbind()

    row = json.loads((run_dir / "sessions.jsonl").read_text().splitlines()[0])
    assert row["head"] == gitstate.observe(repo, dirty=False).head


def test_no_repo_observed_leaves_the_row_without_a_head():
    turnkey.clear()
    gitstate.unbind()
    run_dir = _run_dir()

    failure.record_session_map(run_dir / ".session_id", "plan", "ses_n", "claude")

    row = json.loads((run_dir / "sessions.jsonl").read_text().splitlines()[0])
    # Absent, not blank: a store can tell "nothing observed a tree" from "a hash we
    # failed to read", which an empty string would collapse together.
    assert "head" not in row


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
