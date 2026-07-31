"""End-to-end drives of the dream flow (`coder/flows/dream.py`).

Dream is the cheapest parity check in the coder port: four YAML nodes, three states, no
branch, so the two engines run the same shape and any difference is a real one. Nothing is
stubbed but the reflection turn — `gather_run_evidence` digests a hand-written
`events.jsonl` for real, and `record_improvements` drains a real inbox into a real ledger.

What is under test that the port could get wrong:

* the digest itself, which is the whole reason this flow exists — repeated `enter`s are a
  loop, and the loop count comes from the event log rather than from `output.json` because
  a re-run overwrites the latter;
* the JSON divergence: the YAML rendered the digest mapping into the prompt as a Python
  repr while the prompt asked the turn to read it as JSON, and the port hands it JSON;
* the `run_dir` **alias**, which is the first reserved-name collision the coder port hit —
  `run_dir` is already a property on `Workflow`. The operator's documented `--params
  '{"run_dir": ...}'` and the checkpoint's field-name round trip must both work, and they
  are two different mechanisms;
* the ledger's dedup, which is the signal the flow produces: friction seen in a second run
  bumps a count rather than landing twice.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.flows.dream import Dream
from workhorse_workflows.coder.paths import DREAM_INBOX, DREAM_LEDGER
from workhorse_workflows.coder.schemas.dream import ImprovementsRecorded

RUNS = ".agents/runs"


def _events(*rows: tuple[str, str, str]) -> str:
    """An `events.jsonl` from `(node, phase, ts)` triples, in the order given."""
    return "".join(
        json.dumps({"node": node, "phase": phase, "ts": ts}) + "\n" for node, phase, ts in rows
    )


#: One finished coder run: `implement` entered three times (a loop), and a `qa` node that
#: took four minutes (a stall). Both are invisible in the run's final artifacts, which is
#: the case for digesting the event log at all.
RUN_EVENTS = _events(
    ("plan", "enter", "2026-07-29T10:00:00+00:00"),
    ("plan", "done", "2026-07-29T10:00:20+00:00"),
    ("implement", "enter", "2026-07-29T10:00:20+00:00"),
    ("implement", "done", "2026-07-29T10:01:00+00:00"),
    ("implement", "enter", "2026-07-29T10:01:00+00:00"),
    ("implement", "done", "2026-07-29T10:01:30+00:00"),
    ("implement", "enter", "2026-07-29T10:01:30+00:00"),
    ("implement", "done", "2026-07-29T10:02:00+00:00"),
    ("qa", "enter", "2026-07-29T10:02:00+00:00"),
    ("qa", "done", "2026-07-29T10:06:00+00:00"),
)

PROPOSALS = [
    {
        "layer": "workflow-dag",
        "title": "Implement loops without a bounded budget",
        "detail": "implement re-entered three times with no ceiling",
        "where": "coder/flows/dev.py",
        "impact": "runs stall",
    },
    {
        "layer": "not-a-layer",
        "title": "QA stalls on a cold docker stack",
        "detail": "qa took four minutes, most of it waiting",
    },
]


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def past_run(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """A finished coder run to reflect on, plus a dream run that must be ignored."""
    run = repo / RUNS / "coder-20260729-100000"
    write(run / "events.jsonl", RUN_EVENTS)
    write(run / "implement" / ".session_id", "ses_abc123\n")
    # Newer, and a dream run: reflecting on the last reflection is the degenerate case.
    write(repo / RUNS / "dream-20260729-120000" / "events.jsonl",
          _events(("reflect", "enter", "2026-07-29T12:00:00+00:00")))
    return run


class _Reflector:
    """A scripted reflection turn that writes the inbox its reply claims to have written.

    That is the honest stub: the flow's state does not live in the reply — `record` reads
    `docs/.dream-improvements.inbox.json` off disk — so a stub that only replied would
    leave the state below it with nothing to drain.
    """

    def __init__(self, repo: Path, proposals: Any = None, *, write_inbox: bool = True) -> None:
        self.repo = repo
        self.proposals = PROPOSALS if proposals is None else proposals
        self.write_inbox = write_inbox
        self.calls: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        data = ctx.as_dict()
        self.calls.append(data)
        if self.write_inbox:
            inbox = self.repo / DREAM_INBOX
            inbox.parent.mkdir(parents=True, exist_ok=True)
            inbox.write_text(json.dumps(self.proposals, indent=2), encoding="utf-8")
        return "(scripted) reflection", {
            "status": "done",
            "proposals": len(self.proposals) if isinstance(self.proposals, list) else 0,
            "top_layer": "workflow-dag",
            "notes": "",
        }


# ------------------------------------------------------------------- the whole flow


def test_a_finished_run_becomes_ledger_entries_and_the_inbox_is_drained(
    repo: Path,
    past_run: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    read_json: Callable[[Path], Any],
) -> None:
    """digest → reflect → record, with both ledger files written and the inbox gone."""
    reflector = _Reflector(repo)
    result = drive_flow(Dream(run_dir=str(past_run)), env(), reflector)

    assert isinstance(result, ImprovementsRecorded), result
    assert (result.added, result.bumped, result.total) == (2, 0, 2), result

    ledger = read_json(repo / f"{DREAM_LEDGER}.json")
    assert [row["title"] for row in ledger] == [p["title"] for p in PROPOSALS], ledger
    assert [row["observed"] for row in ledger] == [1, 1], ledger
    assert [row["runs"] for row in ledger] == [[past_run.name]] * 2, ledger
    # A bad label is filed under `infra`, not dropped — a ledger that silently loses
    # proposals is a ledger nobody can trust.
    assert ledger[1]["layer"] == "infra", ledger[1]

    md = (repo / f"{DREAM_LEDGER}.md").read_text(encoding="utf-8")
    assert "**[workflow-dag]** Implement loops without a bounded budget" in md, md
    assert f"Runs: {past_run.name}" in md, md

    # Deleted, so the next run does not re-bump every proposal in it and manufacture
    # evidence of a recurrence that never happened.
    assert not (repo / DREAM_INBOX).exists()


def test_the_digest_carries_the_loop_the_final_artifacts_hide(
    repo: Path, past_run: Path, env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> None:
    """The loop count comes from the event log, and it is what reflection is handed.

    `implement/output.json` would show one result no matter how many times the node ran,
    which is exactly why the digest counts `enter` events instead.
    """
    reflector = _Reflector(repo)
    drive_flow(Dream(run_dir=str(past_run)), env(), reflector)

    digest = json.loads(reflector.calls[0]["run_digest"])
    assert digest["loops"] == [{"node": "implement", "entered": 3}], digest["loops"]
    assert digest["total_node_visits"] == 5, digest
    assert digest["wall_time_seconds"] == 360, digest
    assert digest["slow_nodes"][0] == {"node": "qa", "seconds": 240}, digest["slow_nodes"]
    assert digest["path_tail"][-1] == "qa", digest["path_tail"]
    # The transcript pointer, which is too large to inline and too useful to lose.
    assert digest["sessions"] == {"implement": "ses_abc123"}, digest["sessions"]


def test_the_reflection_turn_is_handed_json_not_a_python_repr(
    repo: Path, past_run: Path, env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> None:
    """The one divergence from the YAML, and the reason it is one.

    `{{ run_digest }}` rendered a mapping through `str()`: single-quoted keys, `True`,
    `None`. The prompt asks the turn to read it as JSON, and it parsed often enough to
    look fine. `json.loads` succeeding here is the whole assertion.
    """
    reflector = _Reflector(repo)
    drive_flow(Dream(run_dir=str(past_run), epic="EPIC-1"), env(), reflector)

    raw = reflector.calls[0]["run_digest"]
    assert isinstance(raw, str) and raw.startswith("{\n"), raw[:40]
    assert "'" not in raw.split("hint")[0], raw
    json.loads(raw)  # would raise on a repr

    assert reflector.calls[0]["epic"] == "EPIC-1", reflector.calls[0]
    # Every state below `start` reads the *resolved* run dir, not the input var.
    assert reflector.calls[0]["run_dir"] == str(past_run.resolve()), reflector.calls[0]


def test_run_dir_is_settable_by_its_documented_param_name_and_by_its_field_name(
    past_run: Path,
) -> None:
    """`run_dir` is a property on `Workflow`, so the input field had to be renamed.

    The alias keeps `--params '{"run_dir": "..."}'` — the invocation the YAML documents —
    working unchanged, and `populate_by_name` keeps the *checkpoint* working, because the
    checkpoint records inputs by field name. Both, or the flow accepts the operator and
    then refuses its own resume.
    """
    assert Dream(run_dir=str(past_run)).reflect_on == str(past_run)
    assert Dream(reflect_on=str(past_run)).reflect_on == str(past_run)
    assert Dream(run_dir=str(past_run)).model_dump(mode="json")["reflect_on"] == str(past_run)


# ---------------------------------------------------------------- resolution + dedup


def test_no_run_dir_reflects_on_the_newest_run_that_is_not_itself_a_dream(
    repo: Path, past_run: Path, env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> None:
    """The normal invocation: reflection follows the run it reads.

    The dream run seeded beside it is newer, and taking it would mean reflecting on the
    last reflection — reachable simply by running dream twice.
    """
    reflector = _Reflector(repo)
    drive_flow(Dream(), env(), reflector)

    assert reflector.calls[0]["run_dir"] == str(past_run.resolve()), reflector.calls[0]


def test_a_mistyped_run_dir_falls_back_rather_than_failing(
    repo: Path, past_run: Path, env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> None:
    """A path with no `events.jsonl` is a typo, and the useful run is one directory over."""
    reflector = _Reflector(repo)
    drive_flow(Dream(run_dir=str(repo / RUNS / "coder-nope")), env(), reflector)

    assert reflector.calls[0]["run_dir"] == str(past_run.resolve()), reflector.calls[0]


def test_the_same_friction_seen_twice_bumps_a_count_instead_of_landing_twice(
    repo: Path,
    past_run: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write_json: Callable[[Path, Any], Path],
    read_json: Callable[[Path], Any],
) -> None:
    """Recurrence rising to the top on its own is the signal the ledger exists to produce.

    The dedup key is case- and whitespace-normalised because that is exactly how two runs
    describe the same friction differently, and in no other way.
    """
    write_json(repo / f"{DREAM_LEDGER}.json", [{
        "layer": "workflow-dag",
        "title": "implement  loops   WITHOUT a bounded budget",
        "detail": "seen before",
        "where": "",
        "impact": "",
        "observed": 2,
        "runs": ["coder-20260701-090000"],
        "status": "open",
    }])

    result = drive_flow(Dream(run_dir=str(past_run)), env(), _Reflector(repo))

    assert (result.added, result.bumped, result.total) == (1, 1, 2), result
    ledger = read_json(repo / f"{DREAM_LEDGER}.json")
    bumped = ledger[0]
    assert bumped["observed"] == 3, bumped
    assert bumped["runs"] == ["coder-20260701-090000", past_run.name], bumped
    # The freshest detail wins; the title keeps the spelling the ledger already had.
    assert bumped["detail"] == "implement re-entered three times with no ceiling", bumped
    assert bumped["title"] == "implement  loops   WITHOUT a bounded budget", bumped

    md = (repo / f"{DREAM_LEDGER}.md").read_text(encoding="utf-8")
    assert md.index("observed ×3") < md.index("observed ×1"), md


def test_an_empty_reflection_records_nothing_and_says_so(
    repo: Path, past_run: Path, env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> None:
    """A turn that proposed nothing leaves no inbox, and that is not an error.

    The YAML's `record-improvements.py` reported the same thing the same way; keeping it
    matters because a dream run over a clean run is the expected common case.
    """
    result = drive_flow(
        Dream(run_dir=str(past_run)), env(), _Reflector(repo, write_inbox=False)
    )

    assert (result.added, result.bumped, result.total) == (0, 0, 0), result
    assert result.note == "no inbox — nothing to record", result
    assert not (repo / f"{DREAM_LEDGER}.json").exists()


# ------------------------------------------------------------------------- resume


def test_a_run_killed_in_reflection_resumes_on_reflection_and_re_uses_the_digest(
    repo: Path, past_run: Path, env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> None:
    """`reflect` is a state of its own because the inbox it writes is on disk.

    A resume that re-ran the digest with it would be harmless; one that re-ran a
    *completed* reflection would append a second round of proposals for the same run. So
    the checkpoint has to land between them, and this is the assertion that it does.

    It is also the test that `populate_by_name` earns its place: the checkpoint records
    inputs by FIELD name (`reflect_on`), and `Dream(**resume.inputs)` is how a resume
    rebuilds the instance.
    """
    class _Killed(_Reflector):
        def __call__(self, node: Any, ctx: Any, *a: Any, **kw: Any) -> Any:
            raise RuntimeError("killed while reflecting")

    run_env = env()
    run_dir = run_env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while reflecting"):
        drive_flow(Dream(run_dir=str(past_run)), run_env, _Killed(repo))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "reflect", resume
    assert resume.flow == "Dream", resume
    assert resume.inputs["reflect_on"] == str(past_run), resume.inputs
    assert "run_dir" not in resume.inputs, resume.inputs

    reflector = _Reflector(repo)
    result = drive_flow(Dream(**resume.inputs), env(run_dir=run_dir), reflector, resume)

    assert result.total == 2, result
    assert len(reflector.calls) == 1, reflector.calls
    # The digest was read back off the first run's artifacts, not re-derived.
    assert reflector.calls[0]["run_dir"] == str(past_run.resolve()), reflector.calls[0]
