"""Tests for the benchmark harness.

These cover the properties that make the score trustworthy, and nothing else — a
benchmark whose own scoring is wrong is worse than no benchmark, but its table
formatting is not load-bearing.

The properties:

* a node that slept on a usage cap is NEVER flagged as a hang, while one that did the
  same wall-clock in ACTIVE work is;
* a judge's behavioral claim is capped unless it cites paths that actually exist;
* the structural trace never invents a behavioral claim of its own;
* a run that predates the workflow source is called stale — the check that had itself
  gone stale, silently, by globbing a layout that no longer existed;
* churn is a cycle repeating, never merely a node running often — a loop over a queue
  re-enters the same nodes once per item and that is the workflow working;
* `babysit` recognises a run that stopped without deciding — a budget stop leaves no
  `terminal` on purpose, so a loop reading only that field waits out its whole ceiling
  on exactly the stop it was built to catch;
* the debugging task set stays inside the hour it exists to fit in.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tomllib
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("bench", Path(__file__).parents[1] / "bench.py")
# A spec and a loader are what a real file on disk always yields; the import machinery
# answers None for the cases this is not (a namespace package, an unimportable path).
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
sys.modules["bench"] = bench
_spec.loader.exec_module(bench)


# ── fixtures ──────────────────────────────────────────────────────────────────────────


def write_events(base: Path, node: str, enter: str, done: str, *, flow: bool = False) -> Path:
    d = base / node / "_flow" if flow else base
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text(
        json.dumps({"ts": enter, "phase": "enter", "node": node}) + "\n"
        + json.dumps({"ts": done, "phase": "done", "node": node}) + "\n",
        encoding="utf-8")
    return base


@pytest.fixture
def spec(tmp_path: Path) -> "bench.Spec":
    """A minimal benchmark app: one surface, one backlog bullet, a real target dir."""
    target = tmp_path / "app"
    (target / "docs").mkdir(parents=True)
    (target / "docs" / "backlog.md").write_text(
        "# Backlog\n\n- [todo-create] A person adds a todo and it appears immediately.\n"
        "- [todo-delete] A person deletes a todo and is protected from doing so by accident.\n",
        encoding="utf-8")
    spec_path = tmp_path / "benchmark.yaml"
    spec_path.write_text(
        f"target: {target}\nbacklog: docs/backlog.md\n"
        "surfaces:\n  - service: api\n    service_root: api\n    marker: go.mod\n",
        encoding="utf-8")
    return bench.load_spec(spec_path)


def add_epic(spec: "bench.Spec", name: str, bullets: list[str],
             stories: dict[str, str]) -> None:
    d = spec.target / "docs" / "epics" / name
    d.mkdir(parents=True, exist_ok=True)
    covered = "\n".join(f"- [{b}] whatever the bullet said" for b in bullets)
    (d / "epic.md").write_text(
        f"---\ntype: epic\nid: T-1\n---\n# Epic\n\n## Backlog bullets covered\n\n{covered}\n",
        encoding="utf-8")
    for slug, status in stories.items():
        s = d / "stories" / slug
        s.mkdir(parents=True, exist_ok=True)
        (s / "story.md").write_text(
            f"---\ntype: story\nslug: {slug}\nstatus: {status}\n---\n# Story\n",
            encoding="utf-8")


# ── timing: cap-wait is never a hang ──────────────────────────────────────────────────


def test_cap_wait_is_never_flagged_as_a_hang(spec: "bench.Spec"):
    """3h35m of wall-clock that was 3h35m of cap-wait is a healthy node, not a hang.

    Workhorse waits caps out by design ("run unattended for days"), so this is the one
    property the timing report must never get wrong.
    """
    write_events(spec.artifacts / "run1", "review_story_documentation",
                 "2026-07-21T00:00:00+00:00", "2026-07-21T03:35:00+00:00")
    spec.logs.mkdir(parents=True, exist_ok=True)
    (spec.logs / "coder.log").write_text(
        "[review_story_documentation] ⏸ spending/usage cap reached — pausing ~12900s (resuming …)\n",
        encoding="utf-8")

    node = next(n for n in bench.hang_candidates(spec)
                if n["node"] == "review_story_documentation")
    assert not node["hang"]
    assert node["active_per_run"] < 600, "cap-wait must be subtracted from active time"


def test_genuine_active_work_is_flagged(spec: "bench.Spec"):
    """The same wall-clock with no cap-wait behind it is a real hang / retry-churn."""
    write_events(spec.artifacts / "run1", "stuck_agent",
                 "2026-07-21T00:00:00+00:00", "2026-07-21T02:00:00+00:00")
    spec.logs.mkdir(parents=True, exist_ok=True)
    (spec.logs / "coder.log").write_text("no cap here\n", encoding="utf-8")

    node = next(n for n in bench.hang_candidates(spec) if n["node"] == "stuck_agent")
    assert node["hang"], "2h of ACTIVE work must exceed the 30-min threshold"


def test_flow_containers_are_excluded(spec: "bench.Spec"):
    """A container's time is its children's — flagging it points at the wrong node."""
    write_events(spec.artifacts / "run1", "qa_phase",
                 "2026-07-21T00:00:00+00:00", "2026-07-21T04:00:00+00:00", flow=True)
    assert "qa_phase" in bench.flow_containers(spec.artifacts)
    assert "qa_phase" not in {n["node"] for n in bench.hang_candidates(spec)}


# ── reliability ───────────────────────────────────────────────────────────────────────


def test_escalation_outranks_repair(spec: "bench.Spec", monkeypatch):
    """An operator-gate escalation is a would-have-halted run, not an ordinary rework."""
    monkeypatch.setattr(bench, "WORKFLOW_SRC", spec.target)  # dated by the fixture, not the tree
    run = spec.artifacts / "run1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text("\n".join(
        json.dumps({"ts": "2026-07-21T00:00:00+00:00", "phase": "enter", "node": n})
        for n in ("plan_story", "fix_story", "await_operator")), encoding="utf-8")

    row = bench.read_runs(spec)[0]
    assert row["repairs"] == ["fix_story"]
    assert row["escalations"] == ["await_operator"]


# ── the backlog trace ─────────────────────────────────────────────────────────────────


def test_bullets_trace_to_the_epic_that_claims_them(spec: "bench.Spec"):
    add_epic(spec, "core", ["todo-create"],
             {"api-create": "QA passed", "web-create": "Not started"})

    by_id = {b["id"]: b for b in bench.trace_bullets(spec)}
    assert by_id["todo-create"]["epics"] == ["core"]
    assert len(by_id["todo-create"]["stories"]) == 2
    assert [s["slug"] for s in by_id["todo-create"]["stories_done"]] == ["api-create"]
    # An unclaimed bullet must surface as unclaimed, not go missing from the score.
    assert by_id["todo-delete"]["epics"] == []


def test_structural_scoring_never_claims_built(spec: "bench.Spec", capsys):
    """`--no-judge` may say `planned`; claiming `built` is precisely what it cannot know."""
    add_epic(spec, "core", ["todo-create"], {"api-create": "QA passed"})
    bench.cmd_score(spec, judge=False, jobs=1, only=[])

    card = json.loads((spec.logs / "scorecard.json").read_text(encoding="utf-8"))
    levels = {b["id"]: b["level"] for b in card["bullets"]}
    assert levels == {"todo-create": 1, "todo-delete": 0}
    # A story marked "QA passed" must not lift the bullet past `planned` on its own.
    assert card["satisfaction_pct"] == pytest.approx(100 * 1 / 6, abs=0.1)


# ── the judge, and the citation check that keeps it honest ────────────────────────────


class FakeBackend:
    """Stands in for the agent CLI: returns one canned response for every turn."""

    name = "fake"

    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def run_turn(self, prompt, node_id, session_id_path, **kw):
        self.prompts.append(prompt)
        return self.response


def fake_judge(response: str) -> "bench.Judge":
    """A `Judge` whose agent turn is canned — the two collaborators are real.

    `judge_one` takes the whole `Judge`, not a bare backend, so the resilience and clock
    it hands to the turn are the run's rather than module state. Only the backend is
    substituted here; a real `AgentResilience` keeps the retry budget the shipped code
    would use, and no retry is reached anyway because a canned turn never fails.
    """
    return bench.Judge(FakeBackend(response), bench.AgentResilience(), bench.SYSTEM_CLOCK)


def judge(spec: "bench.Spec", bullet: dict, response: str) -> dict:
    rubric = (Path(__file__).parents[1] / "rubric.md").read_text(encoding="utf-8")
    return bench.judge_one(spec, bullet, rubric, fake_judge(response))


def test_a_real_citation_keeps_its_level(spec: "bench.Spec"):
    (spec.target / "api").mkdir()
    (spec.target / "api" / "service.go").write_text("package api\n", encoding="utf-8")
    bullet = bench.trace_bullets(spec)[0]

    got = judge(spec, bullet, json.dumps(
        {"level": 3, "evidence": ["api/service.go:CreateTodo"], "reason": "implemented + tested"}))
    assert got["level"] == 3
    assert not got["capped"]


def test_a_hallucinated_citation_is_capped_at_planned(spec: "bench.Spec"):
    """The judge's commonest failure: a confident claim citing a file that isn't there."""
    bullet = bench.trace_bullets(spec)[0]

    got = judge(spec, bullet, json.dumps(
        {"level": 3, "evidence": ["api/does_not_exist.go"], "reason": "looks done to me"}))
    assert got["level"] == 1, "an unverifiable behavioral claim must not score as built"
    assert got["capped"]
    assert got["unverified_citations"] == ["api/does_not_exist.go"]


def test_an_uncited_claim_is_capped(spec: "bench.Spec"):
    bullet = bench.trace_bullets(spec)[0]
    got = judge(spec, bullet, json.dumps({"level": 2, "evidence": [], "reason": "trust me"}))
    assert got["level"] == 1
    assert got["capped"]


def test_level_1_needs_no_citation(spec: "bench.Spec"):
    """Only *behavioral* claims need evidence — `planned` and `absent` are not capped."""
    bullet = bench.trace_bullets(spec)[0]
    got = judge(spec, bullet, json.dumps({"level": 1, "evidence": [], "reason": "story only"}))
    assert got["level"] == 1
    assert not got["capped"]


def test_an_unparseable_or_failed_judgement_scores_zero(spec: "bench.Spec"):
    """A judge that errors or rambles must not silently award credit."""
    bullet = bench.trace_bullets(spec)[0]
    assert judge(spec, bullet, "I could not determine this, sorry.")["level"] == 0


def test_rubric_placeholders_are_all_filled(spec: "bench.Spec"):
    """A typo'd placeholder would ship the judge a literal `{{stories}}` and it would
    invent the context instead of being given it."""
    add_epic(spec, "core", ["todo-create"], {"api-create": "QA passed"})
    bullet = next(b for b in bench.trace_bullets(spec) if b["id"] == "todo-create")
    judging = fake_judge(json.dumps({"level": 0, "evidence": [], "reason": "x"}))
    rubric = (Path(__file__).parents[1] / "rubric.md").read_text(encoding="utf-8")

    bench.judge_one(spec, bullet, rubric, judging)
    prompt = judging.backend.prompts[0]
    assert "{{" not in prompt
    assert "todo-create" in prompt and "api-create" in prompt and "QA passed" in prompt


def test_render_leaves_json_braces_alone(spec: "bench.Spec"):
    """The rubric shows the judge a JSON shape; single braces must survive rendering."""
    out = bench.render('{"level": 2} and {{bullet_id}}', bullet_id="todo-create")
    assert out == '{"level": 2} and todo-create'


# ── staleness: the check that had gone stale itself ───────────────────────────────────


def test_a_run_older_than_the_workflow_source_is_stale(spec: "bench.Spec", monkeypatch):
    """The whole point of the reliability half: a report on code that no longer exists.

    This regressed invisibly. The mtime scan globbed `workflow.yaml` / `scripts/*.py` /
    `prompts/*.md` under `base-library/workflows/*` — the YAML engine's layout, deleted
    with it. The globs matched nothing, `newest_src` fell to its `0.0` default, and the
    `bool(newest_src)` guard turned every verdict False. A benchmark reporting on runs
    from before the change under test is exactly the vacuous success the check exists to
    catch, so it went unnoticed in precisely the way it was written to prevent.
    """
    src = spec.target / "fake_workflow_src"
    src.mkdir(parents=True)
    monkeypatch.setattr(bench, "WORKFLOW_SRC", src)

    run = spec.artifacts / "run1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text(
        json.dumps({"ts": "2026-07-21T00:00:00+00:00", "phase": "enter", "node": "a"}),
        encoding="utf-8")
    # The source is edited after the run recorded its last event. Stamped rather than
    # merely written second: both writes land inside one filesystem timestamp tick, so
    # ordering the calls proves nothing about the mtimes the comparison actually reads.
    (src / "workflow.py").write_text("# edited after the run\n", encoding="utf-8")
    os.utime(run / "events.jsonl", (0, 0))

    assert bench.read_runs(spec)[0]["stale"], "a run predating its own source must be flagged"


def test_the_real_workflow_source_dates_something(spec: "bench.Spec"):
    """The globs must match the tree as it actually is, not as it once was.

    The test above proves the comparison works against a fixture, which is exactly what
    the broken version would also have passed. This one is the guard that failed to
    exist: point the scan at the shipped source tree and require it to find a file. If
    the layout moves again, this goes red instead of the staleness verdict going quiet.
    """
    assert bench.WORKFLOW_SRC.is_dir(), f"{bench.WORKFLOW_SRC} — bench.py is out of date"
    run = spec.artifacts / "run1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text(
        json.dumps({"ts": "2000-01-01T00:00:00+00:00", "phase": "enter", "node": "a"}),
        encoding="utf-8")
    os.utime(run / "events.jsonl", (0, 0))  # older than any file in the tree

    assert bench.read_runs(spec)[0]["stale"], "the shipped source tree dated nothing"


# ── churn: a repeating cycle, not a busy node ─────────────────────────────────────────


def test_a_queue_loop_is_not_churn():
    """Five stories through plan → implement → qa is the workflow working, not churn.

    The naive signal — "this node ran a lot" — flags exactly this, which would make the
    churn row fire on every healthy multi-story run and therefore be ignored on the one
    run where it mattered.
    """
    entered = []
    for story in range(5):
        entered += ["select_story", "plan", f"implement_{story}", "qa", "commit"]
    assert bench.cycles(entered) == [] or all(
        c["cycle"] != ["plan"] for c in bench.cycles(entered))


def test_a_node_retrying_itself_is_churn():
    """Period 1: the same node three times running, with nothing in between."""
    found = bench.cycles(["plan", "fix_story", "fix_story", "fix_story", "commit"])
    assert {"cycle": ["fix_story"], "repeats": 3} in found


def test_a_two_node_ping_pong_is_churn():
    """Period 2: a transition condition that never becomes false.

    Reported as one 3× period-2 cycle rather than as two separate busy nodes, because
    the fix is different — a self-retrying node needs a bounded attempt count, a
    ping-pong needs the guard that decides between the two states.
    """
    found = bench.cycles(["setup", "plan", "implement", "plan", "implement",
                          "plan", "implement", "done"])
    assert {"cycle": ["plan", "implement"], "repeats": 3} in found


def test_churn_reads_subflows_too(spec: "bench.Spec"):
    """A spinning subflow is invisible from the parent, which sees one slow container."""
    d = spec.artifacts / "run1" / "qa_phase" / "_flow"
    d.mkdir(parents=True)
    d.joinpath("events.jsonl").write_text("\n".join(
        json.dumps({"ts": "2026-07-21T00:00:00+00:00", "phase": "enter", "node": n})
        for n in ["check", "repair"] * 4), encoding="utf-8")

    found = bench.churn_candidates(spec)
    assert found and found[0]["cycle"] == ["check", "repair"]
    assert "qa_phase" in found[0]["where"]


# ── when babysit believes a run is over ───────────────────────────────────────────────


def write_run_json(spec: "bench.Spec", name: str, **fields) -> Path:
    d = spec.artifacts / name
    d.mkdir(parents=True, exist_ok=True)
    record = {"workflow": name.split("-")[0], "run_id": name, "terminal": None,
              "interrupted_at": None, "error": None, **fields}
    (d / "run.json").write_text(json.dumps(record), encoding="utf-8")
    return d


def test_a_run_still_going_is_not_settled(spec: "bench.Spec"):
    write_run_json(spec, "coder-a")
    assert bench.settled_run(spec) is None


def test_a_terminal_settles_the_run(spec: "bench.Spec"):
    write_run_json(spec, "coder-a", terminal="terminal")
    assert bench.settled_run(spec) == ("coder-a", "terminal", "")


def test_a_budget_stop_settles_the_run_too(spec: "bench.Spec"):
    """The case that reads `terminal` alone would miss entirely.

    `RunBudgetExceeded` deliberately does not stamp a terminal — that field is workhorse's
    "this run is over" signal and a budget stop must stay visible to `--resume-latest`. So
    the process is gone with `terminal` still null, and a babysitter watching only that
    field would poll on to its ceiling waiting for something that is never written.
    """
    write_run_json(spec, "coder-a", interrupted_at="2026-07-31T16:32:24+00:00",
                   error="run exceeded its WORKHORSE_MAX_RUNTIME_S wall-clock budget")
    run, verdict, detail = bench.settled_run(spec)
    assert (run, verdict) == ("coder-a", "stopped")
    assert "WORKHORSE_MAX_RUNTIME_S" in detail, "the reason must survive to the report"


def test_a_resumed_run_reads_as_open_again(spec: "bench.Spec"):
    """A stop is not sticky. `writer.resume` rewrites `run.json` without the stamp, so a
    run picked back up must stop counting as settled — otherwise `babysit` would return
    the instant it was pointed at a resumed run, which is the one it most needs to watch."""
    write_run_json(spec, "coder-a", interrupted_at="2026-07-31T16:32:24+00:00", error="out of clock")
    write_run_json(spec, "coder-a")  # what a resume leaves behind
    assert bench.settled_run(spec) is None


# ── what --resume points at ───────────────────────────────────────────────────────────


def test_resume_is_a_no_op_without_the_flag(spec: "bench.Spec"):
    assert bench.resume_flags(spec, "coder", False) == []


def test_resume_names_the_newest_checkpointed_run(spec: "bench.Spec"):
    """The dir, not `--resume-latest`. Which one it is has to be this harness's choice."""
    old = write_run_json(spec, "coder-a")
    (old / "checkpoint.json").write_text("{}", encoding="utf-8")
    new = write_run_json(spec, "coder-b")
    (new / "checkpoint.json").write_text("{}", encoding="utf-8")
    os.utime(old / "checkpoint.json", (1_000, 1_000))

    assert bench.resume_flags(spec, "coder", True) == ["--resume-run", str(new)]


def test_a_failed_run_is_still_resumable_here(spec: "bench.Spec"):
    """The debugging loop's central move, and the reason `--resume-latest` is wrong for it.

    `--resume-latest` resolves through `rundir.find_latest_resumable`, which skips any run
    carrying a `terminal` — correct for an operator, since a run that reached an end state
    is over. But this harness exists to *fix the workflow the run failed on and continue*,
    and a failed run has a checkpoint with hours of story work behind it. Refusing it would
    mean re-running the whole story to reach the state under test, every single iteration.
    """
    failed = write_run_json(spec, "coder-a", terminal="fail",
                            error="documentation did not converge in 4 passes")
    (failed / "checkpoint.json").write_text("{}", encoding="utf-8")

    assert bench.resume_flags(spec, "coder", True) == ["--resume-run", str(failed)]


def test_a_run_with_no_checkpoint_is_not_resumable(spec: "bench.Spec"):
    """A run dir that never reached a checkpoint has nothing to continue from, and saying
    so beats handing workhorse a dir it will reject with a less specific message."""
    write_run_json(spec, "coder-a")

    with pytest.raises(SystemExit, match="no coder run with a checkpoint"):
        bench.resume_flags(spec, "coder", True)


# ── the phase environment: tier and budget are spec data ──────────────────────────────


def test_a_budget_becomes_workhorses_own_ceiling(tmp_path: Path):
    """`budget:` must reach workhorse, which stops between states with the checkpoint
    intact — not a `timeout(1)` that kills mid-node and destroys the evidence."""
    spec_path = tmp_path / "benchmark.yaml"
    spec_path.write_text(
        f"target: {tmp_path / 'app'}\nsurfaces: [{{service: api, service_root: api}}]\n"
        "budget: {author: 900, coder: 2700}\n", encoding="utf-8")
    spec = bench.load_spec(spec_path)

    assert bench.phase_env(spec, "author")["WORKHORSE_MAX_RUNTIME_S"] == "900.0"
    assert bench.phase_env(spec, "coder")["WORKHORSE_MAX_RUNTIME_S"] == "2700.0"
    # An unbudgeted phase stays unbounded rather than inheriting another phase's ceiling.
    assert "WORKHORSE_MAX_RUNTIME_S" not in bench.phase_env(spec, "genesis")


def test_the_power_overlay_keeps_the_machines_own_keys(tmp_path: Path, monkeypatch):
    """Overlay, never replace: `load_config` does not merge, so an explicit
    `$STABLEMATE_CONFIG` that dropped `library_dir` would silently unfind the library."""
    monkeypatch.setattr(bench, "load_config", lambda: {
        "library_dir": "/machine/specific/path",
        "power": {"low": {"claude": {"model": "opus"}}, "high": {"codex": {"effort": "high"}}},
    })
    spec_path = tmp_path / "benchmark.yaml"
    spec_path.write_text(
        f"target: {tmp_path / 'app'}\nsurfaces: [{{service: api, service_root: api}}]\n"
        "power: {low: {claude: {model: sonnet, effort: low}}}\n", encoding="utf-8")
    spec = bench.load_spec(spec_path)

    written = tomllib.loads(Path(bench.phase_env(spec, "author")["STABLEMATE_CONFIG"])
                            .read_text(encoding="utf-8"))
    assert written["library_dir"] == "/machine/specific/path", "machine truth was dropped"
    assert written["power"]["low"]["claude"] == {"model": "sonnet", "effort": "low"}
    assert written["power"]["high"]["codex"] == {"effort": "high"}, "untouched tier was lost"


def test_no_power_means_no_config_override(tmp_path: Path):
    """A spec that states no tier must leave the operator's config alone entirely —
    writing one anyway would silently pin every future run to a snapshot of it."""
    spec_path = tmp_path / "benchmark.yaml"
    spec_path.write_text(
        f"target: {tmp_path / 'app'}\nsurfaces: [{{service: api, service_root: api}}]\n",
        encoding="utf-8")
    assert "STABLEMATE_CONFIG" not in bench.phase_env(bench.load_spec(spec_path), "author")


# ── the shipped task set ──────────────────────────────────────────────────────────────


def test_every_task_spec_loads_and_is_selectable():
    """Every task, whatever its size, must load and carry a backlog with bullets — and
    must be reachable by tag, since an untagged task is invisible to every `--tag` sweep
    and so gets run only by whoever remembers its name."""
    specs = sorted((Path(__file__).parents[1] / "suites").glob("*/benchmark.yaml"))
    assert specs, "the task set is missing"
    for path in specs:
        spec = bench.load_spec(path)
        assert spec.tags, f"{path.parent.name}: no tags — nothing can select it"
        assert (path.parent / spec.backlog).is_file(), f"{path.parent.name}: no backlog"
        assert bench.parse_backlog(path.parent / spec.backlog), \
            f"{path.parent.name}: backlog has no `- [id] …` bullets"


def test_the_hour_sized_tasks_fit_the_hour():
    """The task set's one promise is that a chain finishes inside an hour. A spec that
    silently lost its `budget:` would keep that promise only by luck.

    The hour is `author + coder`, not every phase. Genesis scaffolds the repo once — it is
    network-bound setup that a fix-and-rerun cycle skips, so charging it against the hour
    would price the debugging loop by a step the loop does not take.

    A task may sit outside the hour, but only by saying so in `over_hour:` and why —
    `todo-app` is the one that does, and it pins neither tier nor budget on purpose. The
    exception is data rather than a list of names this test learns, so a budget that grows
    past the hour by accident still fails, which is the case the assertions are for.
    """
    specs = sorted((Path(__file__).parents[1] / "suites").glob("*/benchmark.yaml"))
    held = [p for p in specs if not bench.load_spec(p).over_hour]
    assert held, "every task claims `over_hour:` — the hour-sized set is gone"
    for path in held:
        spec = bench.load_spec(path)
        assert spec.power, f"{path.parent.name}: no tier pinned — the hour is not the spec's"
        total = sum(float(spec.budget.get(p) or 0) for p in ("author", "coder"))
        assert total > 0, f"{path.parent.name}: no author/coder budget"
        assert total <= 3600, \
            f"{path.parent.name}: budgets total {total}s, not an hour — and no `over_hour:` " \
            f"saying why that is deliberate"


# ── the grill gate: the one operator block a benchmark has to answer itself ───────────


GRILL_NOTES = "Run /bench-grill to grill this backlog before it is split into epics."


def gate(tmp_path: Path, status: str = bench.AWAITING, notes: str = GRILL_NOTES) -> Path:
    path = tmp_path / "docs" / "epics" / "_author-context.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{status}\n\n## Questions from the agent\n\n{notes}\n", encoding="utf-8")
    return path


def test_the_shipped_answer_settles_nothing_the_backlog_had_not() -> None:
    """The answer is what keeps the grill from becoming the leak that voids the metric.

    A grill asks exactly the held-out questions, so an operator who answers one has told
    the workflow what to design. This asserts the shipped answer names none of the shipped
    expectations — the check that would have caught a well-meaning edit adding "and yes,
    people need to sign out".
    """
    answer = bench.grill_answer(bench.load_spec(DESIGN_SUITES[0])).lower()
    for path in DESIGN_SUITES:
        spec = bench.load_spec(path)
        for exp in bench.load_expectations(spec):
            assert exp["id"] not in answer
            content = re.findall(r"[a-z]{4,}", exp["rendering"].lower())
            hits = sum(w in answer for w in content)
            assert hits < len(content) / 2, f"{exp['id']} reads as leaked into the answer"


def test_an_answered_gate_carries_the_answer_in_the_first_status_line(tmp_path: Path) -> None:
    """Only the first `STATUS:` line is read — an answer written anywhere else is inert."""
    path = gate(tmp_path)
    assert bench.answer_grill(path, "decide it yourself") is True
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "STATUS: ANSWERED"
    assert bench.AWAITING not in text
    assert "decide it yourself" in text


def test_a_gate_that_is_not_the_grill_is_left_parked(tmp_path: Path) -> None:
    """Every other block reached a person because the resolver could not ground it.

    Answering one of those with a canned non-answer is a give-up wearing an answer's
    clothes: the run continues past a question nobody settled.
    """
    path = gate(tmp_path, notes="The story's acceptance criteria contradict the epic.")
    assert bench.answer_grill(path, "decide it yourself") is False
    assert bench.AWAITING in path.read_text(encoding="utf-8")


def test_an_already_answered_gate_is_not_stamped_twice(tmp_path: Path) -> None:
    path = gate(tmp_path, status="STATUS: ANSWERED")
    assert bench.answer_grill(path, "decide it yourself") is False


def test_a_missing_answers_file_is_fatal(design_spec: "bench.Spec") -> None:
    """Silently skipping the answer would park every run until its budget expired."""
    object.__setattr__(design_spec, "grill", "nope.md")
    with pytest.raises(SystemExit):
        bench.grill_answer(design_spec)


def test_answers_without_the_rule_are_fatal(tmp_path: Path, design_spec: "bench.Spec") -> None:
    """The prose above the rule explains the file to a person; below it is the answer."""
    (tmp_path / "bare.md").write_text("just some prose\n", encoding="utf-8")
    object.__setattr__(design_spec, "grill", "bare.md")
    with pytest.raises(SystemExit):
        bench.grill_answer(design_spec)


# ── design completeness: the metric whose whole validity is that it was held out ──────


DESIGN_SUITES = [p for p in sorted((Path(__file__).parents[1] / "suites").glob("*/benchmark.yaml"))
                 if bench.load_spec(p).hidden]


@pytest.fixture
def design_spec(tmp_path: Path) -> "bench.Spec":
    """A minimal design suite: an underspecified backlog, and a hidden pack beside it."""
    target = tmp_path / "app"
    (target / "docs").mkdir(parents=True)
    # The brief lives beside the SPEC, not in the target: `bench.py backlog` copies it in,
    # and that copy is the only thing that crosses into the sandbox.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "backlog.md").write_text(
        "# Backlog\n\n- [page-create] A person creates a page.\n", encoding="utf-8")
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "expectations.yaml").write_text(
        "- id: page-delete\n  invariant: every created thing is destroyable\n"
        "  rendering: a user who can create a page can delete one, with confirmation\n",
        encoding="utf-8")
    (hidden / "journeys.yaml").write_text(
        "- id: tidy-up\n  persona: a documentation lead\n"
        "  steps:\n    - create a page\n    - delete the stale one\n",
        encoding="utf-8")
    spec_path = tmp_path / "benchmark.yaml"
    spec_path.write_text(
        f"target: {target}\nbacklog: docs/backlog.md\nhidden: hidden\n"
        "surfaces:\n  - service: api\n    service_root: api\n    marker: go.mod\n",
        encoding="utf-8")
    return bench.load_spec(spec_path)


def design_judge(spec: "bench.Spec", response: str, *, live: bool = False) -> dict:
    rubric = (Path(__file__).parents[1] / "design-rubric.md").read_text(encoding="utf-8")
    exp = bench.load_expectations(spec)[0]
    return bench.judge_expectation(spec, exp, rubric, fake_judge(response),
                                   bench.authored_docs(spec), live=live)


def test_nothing_hidden_reaches_the_target(design_spec: "bench.Spec", tmp_path: Path):
    """The invariant the whole metric rests on: the workflow is never shown the answers.

    `bench.py backlog` is the only thing that writes into the target before author runs,
    and it copies exactly one file. If a hidden expectation ever appears in the sandbox —
    or is paraphrased into the brief — the benchmark stops measuring design and starts
    measuring transcription, and it does so silently: the scores keep printing.
    """
    bench.cmd_backlog(design_spec)
    seeded = [p for p in design_spec.target.rglob("*") if p.is_file()]
    assert [p.relative_to(design_spec.target).as_posix() for p in seeded] == ["docs/backlog.md"]

    hay = "\n".join(p.read_text(encoding="utf-8") for p in seeded)
    for exp in bench.load_expectations(design_spec):
        assert exp["id"] not in hay and exp["invariant"] not in hay
    for journey in bench.load_journeys(design_spec):
        assert journey["id"] not in hay


@pytest.mark.parametrize("path", DESIGN_SUITES, ids=lambda p: p.parent.name)
def test_a_shipped_design_suite_keeps_its_answers_out_of_its_brief(path: Path, tmp_path: Path):
    """The same invariant, on the suites that actually ship — including the words.

    The id check alone would pass a brief that says "and a person can sign out", which is
    the leak that matters: it is a paraphrase, not a copy, and it hands the workflow the
    exact thing the expectation exists to see whether it thought of.
    """
    spec = bench.load_spec(path)
    brief = (path.parent / spec.backlog).read_text(encoding="utf-8").lower()
    for exp in bench.load_expectations(spec):
        assert exp["id"] not in brief, f"{exp['id']}: its own id is in the brief"
        # Every content word of the rendering appearing together would be a paraphrase.
        words = {w for w in re.findall(r"[a-z]{5,}", exp["rendering"].lower())}
        present = {w for w in words if w in brief}
        assert len(present) < max(2, len(words) // 2), \
            f"{exp['id']}: the brief already says most of the rendering ({sorted(present)})"
    # A journey deliberately mixes steps the brief names (sign in, edit a page) with steps
    # it does not — the named ones are the control that says the walk is following a real
    # path. What it may not be is *entirely* named: a journey every step of which the brief
    # already asks for cannot produce a dead end author was not told about.
    for journey in bench.load_journeys(spec):
        unnamed = [s for s in journey["steps"] if s.lower() not in brief]
        assert unnamed, f"{journey['id']}: every step is already in the brief — it walks nowhere new"


@pytest.mark.parametrize("path", DESIGN_SUITES, ids=lambda p: p.parent.name)
def test_a_shipped_design_pack_is_well_formed(path: Path):
    spec = bench.load_spec(path)
    ids = [e["id"] for e in bench.load_expectations(spec)]
    assert ids and len(ids) == len(set(ids)), "expectation ids must be unique"
    for journey in bench.load_journeys(spec):
        assert journey["steps"], f"{journey['id']}: a journey with no steps walks nowhere"


def test_a_malformed_pack_is_fatal_not_empty(design_spec: "bench.Spec"):
    """A typo'd key would otherwise reach the judge as the literal string `None`, and the
    judge would grade whatever it made of that rather than refusing."""
    assert design_spec.hidden_dir is not None
    (design_spec.hidden_dir / "expectations.yaml").write_text(
        "- id: page-delete\n  invariant: every created thing is destroyable\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        bench.load_expectations(design_spec)


def test_a_covered_expectation_needs_a_planning_document(design_spec: "bench.Spec"):
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    got = design_judge(design_spec, json.dumps({
        "level": 2,
        "evidence": ["docs/epics/pages/stories/delete-page/story.md:acceptance criteria"],
        "reason": "the story requires a confirm step"}))
    assert got["level"] == 2 and not got["capped"]


def test_an_unverifiable_design_claim_scores_absent(design_spec: "bench.Spec"):
    """Stricter than `score`, and deliberately: there an unproven claim falls back to the
    structural fact that an epic claims the bullet. Here the citation IS the finding."""
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    got = design_judge(design_spec, json.dumps({
        "level": 2, "evidence": ["docs/epics/pages/stories/nope/story.md"], "reason": "trust me"}))
    assert got["level"] == 0 and got["capped"]
    assert got["unverified_citations"] == ["docs/epics/pages/stories/nope/story.md"]

    uncited = design_judge(design_spec, json.dumps(
        {"level": 1, "evidence": [], "reason": "the epic mentions it"}))
    assert uncited["level"] == 0 and uncited["capped"]


def test_the_paper_score_refuses_a_code_citation(design_spec: "bench.Spec"):
    """A citation of built code proves the coder shipped something and proves nothing
    about what author wrote — on the author-phase run it is no citation at all."""
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    (design_spec.target / "web").mkdir()
    (design_spec.target / "web" / "delete.tsx").write_text("export default null\n", encoding="utf-8")
    response = json.dumps({"level": 2, "evidence": ["web/delete.tsx"], "reason": "it is built"})

    assert design_judge(design_spec, response)["level"] == 0
    # The anchor run is the one place the built app is in scope.
    live = design_judge(design_spec, response, live=True)
    assert live["level"] == 2 and not live["capped"]


def test_only_the_live_run_can_reach_operable(design_spec: "bench.Spec"):
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    response = json.dumps({
        "level": 3, "evidence": ["docs/epics/pages/stories/delete-page/story.md"],
        "reason": "an e2e test deletes a page"})
    assert design_judge(design_spec, response)["level"] == bench.DESIGN_MAX
    assert design_judge(design_spec, response, live=True)["level"] == 3


def test_design_rubric_placeholders_are_all_filled(design_spec: "bench.Spec"):
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    grader = fake_judge(json.dumps({"level": 0, "evidence": [], "reason": "x"}))
    rubric = (Path(__file__).parents[1] / "design-rubric.md").read_text(encoding="utf-8")
    bench.judge_expectation(design_spec, bench.load_expectations(design_spec)[0], rubric,
                            grader, bench.authored_docs(design_spec), live=False)

    prompt = grader.backend.prompts[0]
    assert "{{" not in prompt
    assert "page-delete" in prompt and "destroyable" in prompt
    assert "docs/epics/pages/stories/delete-page/story.md" in prompt
    assert "Level 2 is the ceiling here." in prompt, "the paper run must forbid level 3"


def test_the_live_rubric_lets_operable_cite_something_that_is_not_a_story(
        design_spec: "bench.Spec") -> None:
    """A level-3 finding is by construction not a planning document.

    The paper citation rule says "cite an `epic.md` or a `story.md`". Left in place on the
    anchor run it makes `operable` uncitable, and an uncitable level is scored 0 by the
    verification pass — so the anchor would agree with the paper run for a reason that has
    nothing to do with the app it was built to look at.
    """
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    grader = fake_judge(json.dumps({"level": 0, "evidence": [], "reason": "x"}))
    rubric = (Path(__file__).parents[1] / "design-rubric.md").read_text(encoding="utf-8")
    bench.judge_expectation(design_spec, bench.load_expectations(design_spec)[0], rubric,
                            grader, bench.authored_docs(design_spec), live=True)

    prompt = grader.backend.prompts[0]
    assert "{{" not in prompt
    assert "Level 2 is the ceiling here." not in prompt
    assert "cite the test or script itself" in prompt


def test_journey_rubric_placeholders_are_all_filled(design_spec: "bench.Spec"):
    add_epic(design_spec, "pages", ["page-create"], {"delete-page": "Not started"})
    grader = fake_judge(json.dumps({"steps": []}))
    rubric = (Path(__file__).parents[1] / "journey-rubric.md").read_text(encoding="utf-8")
    bench.judge_journey(design_spec, bench.load_journeys(design_spec)[0], rubric, grader,
                        bench.authored_docs(design_spec))

    prompt = grader.backend.prompts[0]
    assert "{{" not in prompt
    assert "tidy-up" in prompt and "delete the stale one" in prompt


def journey_walk(spec: "bench.Spec", response: str) -> dict:
    rubric = (Path(__file__).parents[1] / "journey-rubric.md").read_text(encoding="utf-8")
    return bench.judge_journey(spec, bench.load_journeys(spec)[0], rubric,
                               fake_judge(response), bench.authored_docs(spec))


def test_a_step_the_judge_never_answered_is_a_dead_end(design_spec: "bench.Spec"):
    """Aligned by position, never by the judge's echo of the step: a judge that returns
    one answer for two steps must not silently shrink the denominator."""
    add_epic(design_spec, "pages", ["page-create"], {"create-page": "Not started"})
    got = journey_walk(design_spec, json.dumps({"steps": [
        {"step": "create a page", "delivered": True,
         "evidence": ["docs/epics/pages/stories/create-page/story.md"], "why": "criterion 2"}]}))

    assert [s["delivered"] for s in got["steps"]] == [True, False]
    assert got["dead_ends"] == ["delete the stale one"]


def test_a_delivered_step_citing_nothing_real_is_a_dead_end(design_spec: "bench.Spec"):
    add_epic(design_spec, "pages", ["page-create"], {"create-page": "Not started"})
    got = journey_walk(design_spec, json.dumps({"steps": [
        {"step": "create a page", "delivered": True, "evidence": ["docs/epics/ghost/epic.md"],
         "why": "it is there somewhere"},
        {"step": "delete the stale one", "delivered": True, "evidence": [], "why": "obviously"}]}))
    assert got["dead_ends"] == ["create a page", "delete the stale one"]


def test_the_crud_matrix_finds_a_created_thing_nobody_deletes(design_spec: "bench.Spec"):
    """The `page-delete` miss, found deterministically and for free — no agent turn."""
    add_epic(design_spec, "pages", ["page-create"], {"create-page": "Not started"})
    story = design_spec.target / "docs/epics/pages/stories/create-page/story.md"
    story.write_text(story.read_text(encoding="utf-8")
                     + "\nA person creates a page and later edits the page.\n", encoding="utf-8")

    rows = {r["entity"]: r for r in bench.crud_matrix(design_spec)}
    assert "page" in rows, "an entity a story creates must appear in the matrix"
    assert "create" in rows["page"]["operations"] and "update" in rows["page"]["operations"]
    assert "delete" in rows["page"]["missing"] and "read" in rows["page"]["missing"]


def test_the_matrix_only_crosses_things_that_get_created(design_spec: "bench.Spec"):
    add_epic(design_spec, "pages", ["page-create"], {"read-only": "Not started"})
    story = design_spec.target / "docs/epics/pages/stories/read-only/story.md"
    story.write_text(story.read_text(encoding="utf-8")
                     + "\nA person sees the audit log.\n", encoding="utf-8")
    assert [r["entity"] for r in bench.crud_matrix(design_spec)] == []


def test_structural_design_scoring_names_no_number(design_spec: "bench.Spec", capsys):
    """`score --no-judge` can still say `planned` — the epic graph records coverage.
    Nothing records whether acceptance criteria would deliver an unwritten expectation,
    so the honest structural answer is to decline to score."""
    add_epic(design_spec, "pages", ["page-create"], {"create-page": "Not started"})
    assert bench.cmd_design_score(design_spec, judge=False, jobs=1, only=[],
                                  live=False, journeys=True) == 0

    card = json.loads((design_spec.logs / "design-scorecard.json").read_text(encoding="utf-8"))
    assert card["judged"] is False
    assert card["design_satisfaction_pct"] is None
    assert card["expectations"] == []
    assert "design satisfaction:" not in capsys.readouterr().out


def test_a_task_without_a_hidden_pack_has_no_design_score(spec: "bench.Spec"):
    """Every other suite. Refused by name rather than scoring zero against nothing."""
    assert spec.hidden_dir is None
    with pytest.raises(SystemExit):
        bench.load_expectations(spec)
