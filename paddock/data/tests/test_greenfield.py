"""The greenfield round's ruler: the backlog trace, the judge, and the phase environment.

A benchmark whose own scoring is wrong is worse than no benchmark, and these are the
properties that make this one's score mean something:

* every bullet traces to the epic that claims it, and an *unclaimed* bullet surfaces as
  unclaimed rather than going missing from the score;
* a judge's behavioural claim is capped unless it cites paths that actually exist — the
  judge's commonest failure is a confident claim about a file that is not there;
* the structural score never claims `built`, which is precisely what static structure
  cannot know;
* a budget reaches workhorse, which stops *between states* with the checkpoint intact,
  rather than a `timeout(1)` that kills mid-node and destroys the evidence.

No agent runs here: the judge's backend is canned and everything else is a temp tree.
"""

from __future__ import annotations

import contextlib
import dataclasses
import importlib.util
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from paddock import loader
from paddock.registry import REGISTRY
from paddock.pointer import Pointer
from paddock.runner import Run

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


_spec = importlib.util.spec_from_file_location("_greenfield", DATA / "tasks" / "_greenfield.py")
assert _spec is not None and _spec.loader is not None  # noqa: S101 - a real file on disk
gf = importlib.util.module_from_spec(_spec)
with _tasks_dir_on_path():
    sys.modules["_greenfield"] = gf
    _spec.loader.exec_module(gf)


BACKLOG = (
    "# Backlog\n\n"
    "- [todo-create] A person adds a todo and it appears immediately.\n"
    "- [todo-delete] A person deletes a todo and is protected from doing so by accident.\n"
)


@pytest.fixture
def fixture() -> Any:
    return gf.Fixture(
        backlog="docs/backlog.md",
        surfaces=(gf.Surface(service="api", service_root="api", marker="go.mod"),),
        budget_s={"author": 900.0, "coder": 2700.0},
    )


@pytest.fixture
def run(tmp_path: Path) -> Run:
    """A `Run` over a temp data dir and a temp produced repo — the only two it reads here."""
    data_dir = tmp_path / "data"
    (data_dir / "docs").mkdir(parents=True)
    (data_dir / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (tmp_path / "repo").mkdir()
    return Run(
        task=loader.load_path(DATA / "tasks" / "link_shortener.py"),
        label="t1",
        stage=tmp_path / "stage",
        repo=tmp_path / "repo",
        scratch=tmp_path / "scratch",
        config=tmp_path / "config.toml",
        data_dir=data_dir,
        store=tmp_path / "store",
        seed=Pointer(name="link-shortener", repo_dir="repo", sha256="0" * 64, bytes=1),
    )


def add_epic(repo: Path, name: str, bullets: list[str], stories: dict[str, str]) -> None:
    directory = repo / "docs" / "epics" / name
    directory.mkdir(parents=True, exist_ok=True)
    covered = "\n".join(f"- [{b}] whatever the bullet said" for b in bullets)
    (directory / "epic.md").write_text(
        f"---\ntype: epic\nid: T-1\n---\n# Epic\n\n## {gf.COVERED_HEADING}\n\n{covered}\n",
        encoding="utf-8")
    for slug, status in stories.items():
        story = directory / "stories" / slug
        story.mkdir(parents=True, exist_ok=True)
        (story / "story.md").write_text(
            f"---\ntype: story\nslug: {slug}\nstatus: {status}\n---\n# Story\n", encoding="utf-8")


# ── the backlog trace ─────────────────────────────────────────────────────────────────


def test_bullets_trace_to_the_epic_that_claims_them(run: Run, fixture: Any) -> None:
    add_epic(run.repo, "core", ["todo-create"],
             {"api-create": "QA passed", "web-create": "Not started"})

    by_id = {b["id"]: b for b in gf.trace_bullets(run, fixture)}
    assert by_id["todo-create"]["epics"] == ["core"]
    assert len(by_id["todo-create"]["stories"]) == 2
    assert [s["slug"] for s in by_id["todo-create"]["stories_done"]] == ["api-create"]
    # An unclaimed bullet must surface as unclaimed, not go missing from the score.
    assert by_id["todo-delete"]["epics"] == []


def test_structural_scoring_never_claims_built(run: Run, fixture: Any) -> None:
    """A score with no judge may say `planned`; `built` is what it cannot know."""
    add_epic(run.repo, "core", ["todo-create"], {"api-create": "QA passed"})
    bullets = gf.structural_only(gf.trace_bullets(run, fixture))

    assert {b["id"]: b["level"] for b in bullets} == {"todo-create": 1, "todo-delete": 0}
    # A story marked "QA passed" must not lift the bullet past `planned` on its own.
    assert gf.satisfaction(bullets) == pytest.approx(100 * 1 / 6, abs=0.1)


# ── the judge, and the citation check that keeps it honest ────────────────────────────


class FakeBackend:
    """Stands in for the agent CLI: returns one canned response for every turn."""

    name = "fake"

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def run_turn(self, prompt: str, node_id: str, session_id_path: Any, **kw: Any) -> str:
        self.prompts.append(prompt)
        return self.response


def fake_judge(response: str) -> Any:
    """A `Judge` whose agent turn is canned — the two collaborators are real.

    `judge_one` takes the whole `Judge`, not a bare backend, so the resilience and clock it
    hands to the turn are the round's rather than module state. Only the backend is
    substituted; a real `AgentResilience` keeps the retry budget the shipped code would
    use, and no retry is reached anyway because a canned turn never fails.
    """
    return gf.Judge(FakeBackend(response), gf.AgentResilience(), gf.SYSTEM_CLOCK)


def judge(run: Run, bullet: dict[str, Any], response: str) -> dict[str, Any]:
    rubric = (DATA / "rubric.md").read_text(encoding="utf-8")
    return gf.judge_one(fake_judge(response), bullet, rubric, run.repo)


def test_a_real_citation_keeps_its_level(run: Run, fixture: Any) -> None:
    (run.repo / "api").mkdir()
    (run.repo / "api" / "service.go").write_text("package api\n", encoding="utf-8")
    bullet = gf.trace_bullets(run, fixture)[0]

    got = judge(run, bullet, json.dumps(
        {"level": 3, "evidence": ["api/service.go:CreateTodo"], "reason": "implemented + tested"}))
    assert got["level"] == 3
    assert not got["capped"]


def test_a_hallucinated_citation_is_capped_at_planned(run: Run, fixture: Any) -> None:
    """The judge's commonest failure: a confident claim citing a file that isn't there."""
    bullet = gf.trace_bullets(run, fixture)[0]

    got = judge(run, bullet, json.dumps(
        {"level": 3, "evidence": ["api/does_not_exist.go"], "reason": "looks done to me"}))
    assert got["level"] == 1, "an unverifiable behavioral claim must not score as built"
    assert got["capped"]
    assert got["unverified_citations"] == ["api/does_not_exist.go"]


def test_an_uncited_claim_is_capped(run: Run, fixture: Any) -> None:
    bullet = gf.trace_bullets(run, fixture)[0]
    got = judge(run, bullet, json.dumps({"level": 2, "evidence": [], "reason": "trust me"}))
    assert got["level"] == 1
    assert got["capped"]


def test_level_1_needs_no_citation(run: Run, fixture: Any) -> None:
    """Only *behavioral* claims need evidence — `planned` and `absent` are not capped."""
    bullet = gf.trace_bullets(run, fixture)[0]
    got = judge(run, bullet, json.dumps({"level": 1, "evidence": [], "reason": "story only"}))
    assert got["level"] == 1
    assert not got["capped"]


def test_an_unparseable_or_failed_judgement_scores_zero(run: Run, fixture: Any) -> None:
    """A judge that errors or rambles must not silently award credit."""
    bullet = gf.trace_bullets(run, fixture)[0]
    assert judge(run, bullet, "I could not determine this, sorry.")["level"] == 0


def test_rubric_placeholders_are_all_filled(run: Run, fixture: Any) -> None:
    """A typo'd placeholder ships the judge a literal `{{stories}}`, and it then invents
    the context instead of being given it."""
    add_epic(run.repo, "core", ["todo-create"], {"api-create": "QA passed"})
    bullet = next(b for b in gf.trace_bullets(run, fixture) if b["id"] == "todo-create")
    judging = fake_judge(json.dumps({"level": 0, "evidence": [], "reason": "x"}))
    rubric = (DATA / "rubric.md").read_text(encoding="utf-8")

    gf.judge_one(judging, bullet, rubric, run.repo)
    prompt = judging.backend.prompts[0]
    assert "{{" not in prompt
    assert "todo-create" in prompt and "api-create" in prompt and "QA passed" in prompt


def test_render_leaves_json_braces_alone() -> None:
    """The rubric shows the judge a JSON shape; single braces must survive rendering."""
    assert gf.render('{"level": 2} and {{bullet_id}}', bullet_id="todo-create") == \
        '{"level": 2} and todo-create'


# ── the phase environment: the budget is fixture data ─────────────────────────────────


def test_a_budget_becomes_workhorses_own_ceiling(run: Run, fixture: Any) -> None:
    """The budget must reach workhorse, which stops between states with the checkpoint
    intact — not a `timeout(1)` that kills mid-node and destroys the evidence."""
    assert gf.phase_env(run, fixture, "author")["WORKHORSE_MAX_RUNTIME_S"] == "900.0"
    assert gf.phase_env(run, fixture, "coder")["WORKHORSE_MAX_RUNTIME_S"] == "2700.0"
    # An unbudgeted phase stays unbounded rather than inheriting another phase's ceiling.
    assert "WORKHORSE_MAX_RUNTIME_S" not in gf.phase_env(run, fixture, "genesis")


def test_a_param_overrides_the_fixtures_budget(run: Run, fixture: Any) -> None:
    """A round shortened for a smoke test says so on the command line, not by editing the
    tracked fixture every other round then forgetting to put it back."""
    shortened = dataclasses.replace(run, params={"budget_coder": "60"})
    assert gf.phase_env(shortened, fixture, "coder")["WORKHORSE_MAX_RUNTIME_S"] == "60.0"


# ── the shipped tasks ─────────────────────────────────────────────────────────────────


def test_every_greenfield_task_carries_a_backlog_with_bullets() -> None:
    """A backlog that moved or lost its `- [id] …` bullets scores every bullet absent, and
    it does so quietly: the round still runs and the report still prints."""
    found = 0
    for path in loader.task_paths(DATA):
        spec = importlib.util.spec_from_file_location(f"_probe_{path.stem}", path)
        assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
        module = importlib.util.module_from_spec(spec)
        # In `sys.modules` before execution, exactly as `paddock.loader` does: a dataclass
        # resolves its own annotations through there, and a module absent from it dies.
        sys.modules[spec.name] = module
        REGISTRY.reset()
        try:
            with _tasks_dir_on_path():
                spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
            REGISTRY.reset()
        declared = getattr(module, "FIXTURE", None)
        if not isinstance(declared, gf.Fixture):
            continue
        found += 1
        backlog = DATA / declared.backlog
        assert backlog.is_file(), f"{path.name}: no backlog at {backlog}"
        assert gf.parse_backlog(backlog), f"{path.name}: backlog has no `- [id] …` bullets"
        if declared.decision_records:
            # The records version with the seed and `check_public.py` scans them, both of
            # which need a real tracked directory under `paddock/data/` — and a task that
            # names records it does not have sends every round's resolvers to an empty
            # shelf, where they escalate questions the operator already settled.
            records = DATA / declared.decision_records
            assert records.is_dir(), f"{path.name}: no decision records at {records}"
            assert sorted(records.glob("*.md")), f"{path.name}: {records} holds no records"
        if declared.grill_capture:
            # The frozen operator turn. Both halves or neither: the checkpoint without the
            # gate file resumes into a lane whose answer is missing, and the gate file
            # without the checkpoint is a round that still parks on the grill.
            capture = DATA / declared.grill_capture
            for half in ("checkpoint.json", gf.GRILL_GATE):
                assert (capture / half).is_file(), f"{path.name}: no {half} in {capture}"
    assert found, "no greenfield task declares a Fixture — the backlog-driven half is gone"


# ── the operator gate ─────────────────────────────────────────────────────────────────

GATE = (
    "STATUS: AWAITING_OPERATOR\n"
    "\n"
    "## Questions from the agent\n"
    "\n"
    "❓ **Q1** — what is the creation contract?\n"
)


def park(run: Run, name: str = "_author-context.md") -> Path:
    path = run.repo / "docs" / "epics" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(GATE, encoding="utf-8")
    return path


def watch_once(run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch, *, expect: int) -> None:
    """Run the watcher until the ledger has `expect` entries, then stop it.

    The real watcher lives beside a phase that blocks for minutes; here it is driven to a
    quiescent point and joined, so the test asserts on a finished thread rather than on a
    race. `expect=0` waits out a fixed slice instead — for the cases whose whole claim is
    that nothing was written.
    """
    monkeypatch.setattr(gf, "GATE_POLL_S", 0.01)
    stop, thread = gf.gates_watched(run, fixture, "author")
    thread.start()
    try:
        deadline = time.monotonic() + 10.0
        while len(gf.operator_gates_of(run)) < expect and time.monotonic() < deadline:
            time.sleep(0.01)
        # A further slice, so a wrongly-repeated entry has time to show up rather than
        # being outrun by the stop — and so an `expect=0` case is a real wait.
        time.sleep(0.1)
    finally:
        stop.set()
        thread.join(timeout=5.0)
    assert not thread.is_alive(), "the watcher outlived the phase it was watching"


def test_a_gate_still_awaiting_past_the_grace_is_parked(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one thing the watcher does at a gate: notice, and stop the round on it.

    A round with nobody at the keyboard cannot get past a gate whose lane has no
    resolver — so the value of noticing is the minute it costs instead of the hour, and
    the ledger entry that says the score covers a partial round.
    """
    monkeypatch.setattr(gf, "GATE_GRACE_S", 0.0)
    gate = park(run)
    watch_once(run, fixture, monkeypatch, expect=1)

    entry, = gf.operator_gates_of(run)
    assert entry["action"] == "parked"
    assert entry["gate"] == "docs/epics/_author-context.md"
    assert "no operator" in entry["reason"]
    # Untouched. The watcher reads gates; it has never been the thing that answers one.
    assert gate.read_text(encoding="utf-8") == GATE


def test_the_watcher_never_answers_a_gate(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It used to, for one gate class, from a sheet of replies applied positionally — and
    positionally is the whole defect: a gate's questions are generated per round, so a
    sheet written against one round's questions got stamped `ANSWERED` over another's. The
    repair that looks obvious is forbidden too: checking whether the sheet *covers* what
    was asked makes the harness judge semantics at gate time."""
    monkeypatch.setattr(gf, "GATE_GRACE_S", 0.0)
    gate = park(run)
    watch_once(run, fixture, monkeypatch, expect=1)

    assert gate.read_text(encoding="utf-8").startswith("STATUS: AWAITING_OPERATOR")
    assert not gf.gate_answered(gate)
    assert "answered" not in {e["action"] for e in gf.operator_gates_of(run)}


def test_a_gate_answered_inside_the_grace_is_not_a_stall(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Most gates on a round's path have an auto-resolver, and a resolver that grounds its
    answer writes it in seconds. Parking on first sight would score every one of those as
    a stall, and `parked` would stop meaning "the round stopped here"."""
    gate = park(run)
    watch_once(run, fixture, monkeypatch, expect=0)
    assert gf.operator_gates_of(run) == []

    gate.write_text(GATE.replace("AWAITING_OPERATOR", "ANSWERED"), encoding="utf-8")
    watch_once(run, fixture, monkeypatch, expect=0)
    assert gf.operator_gates_of(run) == []


def test_a_gate_is_parked_once(run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The round stops on a gate the first time; a watcher that keeps re-parking the same
    file turns one stop into a ledger nobody can read a count off."""
    monkeypatch.setattr(gf, "GATE_GRACE_S", 0.0)
    park(run)
    watch_once(run, fixture, monkeypatch, expect=1)
    watch_once(run, fixture, monkeypatch, expect=1)

    assert [e["action"] for e in gf.operator_gates_of(run)] == ["parked"]


def test_a_parked_gate_is_a_warning_on_the_score() -> None:
    lines = gf.warnings([], [], [{"gate": "docs/epics/_author-context.md",
                                 "action": "parked", "reason": "no operator"}])
    assert any("stayed parked" in line for line in lines)
    # A round nobody stopped and nobody reached into is the only one that warns about
    # neither: `hand` has its own warning, for the same reason.
    assert not gf.warnings([], [], [])


# ── the frozen grill capture ──────────────────────────────────────────────────────────

ANSWERED_GATE = GATE.replace("AWAITING_OPERATOR", "ANSWERED") + "\nA1 — `201 Created`.\n"


def capture(run: Run, *, waiting_on: str = "docs/epics/_author-context.md") -> Any:
    """Write a frozen capture into the data dir, as the tracked one is written."""
    directory = run.data_dir / "grill"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / gf.GRILL_GATE).write_text(ANSWERED_GATE, encoding="utf-8")
    run.write_json(directory / "checkpoint.json", {
        "run_id": "pd3eb1e81",
        "state": "refactor_backlog",
        "flow": "Author",
        "waiting_on": waiting_on,
        # Both of these name the machine the capture was taken on, and one of them names a
        # library that is not this round's. Rendering them is the point of the seeding.
        "inputs": {"repo_dir": "/elsewhere/stage/link-shortener", "library_dirs": [],
                   "backlog": "docs/backlog.md"},
        "ctx": {"repo_root": "/elsewhere/stage/link-shortener",
                "author_branch": "author/author-grill", "base_branch": "main"},
    })
    (run.repo / "docs" / "epics").mkdir(parents=True, exist_ok=True)
    run.scratch.mkdir(parents=True, exist_ok=True)
    gf.effective(run).write_text("", encoding="utf-8")
    return None


def test_the_capture_is_seeded_as_a_checkpoint_the_round_resumes_from(
    run: Run, fixture: Any
) -> None:
    """The mechanism, in one assertion: an `Await` checkpoint names the state it will
    resume *into*, so a round that starts from this one starts at `refactor_backlog` —
    past the one gate the product reserves for a human, with nothing about the loop frozen.
    """
    capture(run)
    git_init(run.repo)

    gf.seed_grill_capture(run, dataclasses.replace(fixture, grill_capture="grill"))

    seeded = json.loads(
        (gf.runs_dir(run) / f"author-{gf.AUTHOR_RUN_ID}" / "checkpoint.json")
        .read_text(encoding="utf-8"))
    assert seeded["state"] == "refactor_backlog"
    assert seeded["run_id"] == gf.AUTHOR_RUN_ID
    # A resume rebuilds the instance from the checkpoint's own inputs, never from
    # `--params` — so a path left as the capturing machine's is the path this round reads.
    assert seeded["inputs"]["repo_dir"] == str(run.repo)
    assert seeded["ctx"]["repo_root"] == str(run.repo)
    assert seeded["waiting_on"] == str(run.repo / "docs" / "epics" / gf.GRILL_GATE)
    # Carried through untouched: the capture is the round's inputs, not a subset of them.
    assert seeded["inputs"]["backlog"] == "docs/backlog.md"


def test_the_answered_gate_lands_where_the_flow_will_read_it(run: Run, fixture: Any) -> None:
    capture(run)
    git_init(run.repo)

    gf.seed_grill_capture(run, dataclasses.replace(fixture, grill_capture="grill"))

    gate = run.repo / "docs" / "epics" / gf.GRILL_GATE
    assert gate.read_text(encoding="utf-8") == ANSWERED_GATE
    assert gf.gate_answered(gate)
    # On the branch the parked run was on: `close` reads it off the ctx and fails on a
    # branch that is not there.
    head = subprocess.run(["git", "-C", str(run.repo), "branch", "--show-current"],
                          capture_output=True, text=True, check=True)
    assert head.stdout.strip() == "author/author-grill"


def test_a_declared_capture_that_is_missing_is_an_error_not_a_shrug(
    run: Run, fixture: Any
) -> None:
    """Read from the tracked data dir, never from the tree the round mutates — so a
    capture that is not there is a broken `--data-dir`, and a round that silently ran
    without it would park on the grill after paying for a genesis."""
    with pytest.raises(gf.TrialError, match="no frozen grill capture"):
        gf.seed_grill_capture(run, dataclasses.replace(fixture, grill_capture="nope"))


def test_a_task_with_no_capture_seeds_nothing(run: Run, fixture: Any) -> None:
    """Not every greenfield task's author lane has a grill gate to have frozen."""
    gf.seed_grill_capture(run, fixture)
    assert not (gf.runs_dir(run) / f"author-{gf.AUTHOR_RUN_ID}").exists()


def git_init(repo: Path) -> None:
    for argv in (["init", "-q"], ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *argv], check=True)
    (repo / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)


def test_the_scaffolding_is_committed_before_the_first_story(run: Run) -> None:
    """Untracked installer output is what a story's settle lap parks on — so it is a
    baseline commit, dated before story one, rather than an unrecorded file."""
    subprocess.run(["git", "-C", str(run.repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(run.repo), "config", "user.email", "t@example.com"],
                   check=True)
    subprocess.run(["git", "-C", str(run.repo), "config", "user.name", "t"], check=True)
    (run.repo / "Makefile").write_text("all:\n", encoding="utf-8")

    gf.commit_baseline(run)

    out = subprocess.run(["git", "-C", str(run.repo), "status", "--porcelain"],
                         capture_output=True, text=True, check=True)
    assert out.stdout == ""
    assert gf.git_commits(run.repo) == 1


def test_a_baseline_with_nothing_to_commit_is_not_an_error(run: Run) -> None:
    """Genesis may have committed as it went; a second baseline is then a no-op."""
    subprocess.run(["git", "-C", str(run.repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(run.repo), "config", "user.email", "t@example.com"],
                   check=True)
    subprocess.run(["git", "-C", str(run.repo), "config", "user.name", "t"], check=True)
    (run.repo / "Makefile").write_text("all:\n", encoding="utf-8")
    gf.commit_baseline(run)

    gf.commit_baseline(run)  # no exception

    assert gf.git_commits(run.repo) == 1


def test_a_hand_answer_is_recorded_and_says_so_loudly(run: Run) -> None:
    """A round a person unstuck is not the unattended capture its score would read as."""
    gf.record_hand_answer(run, "dirty-tree-operator-context.create-short-links.md",
                          "gitignored the agent runtime", commit="b5f6862")

    ledger = gf.operator_gates_of(run)
    assert ledger == [{"gate": "dirty-tree-operator-context.create-short-links.md",
                       "action": "hand", "note": "gitignored the agent runtime",
                       "commit": "b5f6862"}]
    assert any("BY HAND" in line for line in gf.warnings([], [], ledger))
    printed = gf.operator_gate_lines(ledger)
    assert any("ANSWERED BY HAND" in line and "b5f6862" in line for line in printed)


def test_a_hand_answer_is_not_counted_as_parked() -> None:
    """Two different findings: parked means the round went on without a decision, hand
    means it went on with one no future round will make for itself."""
    lines = gf.warnings([], [], [{"gate": "g", "action": "hand", "note": "n"}])
    assert not any("stayed parked" in line for line in lines)


# ── the agent's own exhaust ───────────────────────────────────────────────────────────


def test_the_produced_repo_ignores_the_agent_runtime(run: Run) -> None:
    """The coder lane refuses to sweep unrecorded files into a story's commit and parks on
    a human gate instead — so the CLI's session store and the QA daemon's log, which
    reappear on every story, cost a whole round rather than skewing one."""
    (run.repo / ".gitignore").write_text(".agents/runs/\n", encoding="utf-8")
    gf.ignore_agent_runtime(run)

    written = (run.repo / ".gitignore").read_text(encoding="utf-8")
    assert written.startswith(".agents/runs/\n")  # what genesis wrote is left alone
    assert ".opencode/\n" in written
    assert "**/qa/**/*.log\n" in written


def test_the_runtime_ignore_is_written_once(run: Run) -> None:
    gf.ignore_agent_runtime(run)
    once = (run.repo / ".gitignore").read_text(encoding="utf-8")
    gf.ignore_agent_runtime(run)
    assert (run.repo / ".gitignore").read_text(encoding="utf-8") == once
    # A genesis that wrote no `.gitignore` at all still gets one, rather than a crash.
    assert once.startswith("\n" + gf.IGNORE_HEADER)


def test_a_repo_root_gate_is_seen_too(run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The coder lane's dirty-tree, CI and merge gates land at the repo root, not under
    `docs/`. A glob that only knew about the author lane's was blind to them — and a gate
    nobody watches does not park with a ledger entry, it stalls the round in silence."""
    gate = run.repo / "dirty-tree-operator-context.create-short-links.md"
    gate.write_text(GATE, encoding="utf-8")
    monkeypatch.setattr(gf, "GATE_POLL_S", 0.01)
    monkeypatch.setattr(gf, "GATE_GRACE_S", 0.0)
    stop, thread = gf.gates_watched(run, fixture, "coder")
    thread.start()
    try:
        deadline = time.monotonic() + 10.0
        while not gf.operator_gates_of(run) and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join(timeout=5.0)

    entry, = gf.operator_gates_of(run)
    assert entry["gate"] == "dirty-tree-operator-context.create-short-links.md"
    assert entry["action"] == "parked"
    # Seen and parked wherever it is written: this one sits at the repo root rather than
    # under a docs directory, and a gate the watcher does not see costs the round an hour.
    assert gate.read_text(encoding="utf-8") == GATE


def test_a_coder_gate_is_parked_and_left_alone_too(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = run.repo / "ci-operator-context.0001-api.md"
    gate.write_text(GATE, encoding="utf-8")
    monkeypatch.setattr(gf, "GATE_POLL_S", 0.01)
    monkeypatch.setattr(gf, "GATE_GRACE_S", 0.0)
    stop, thread = gf.gates_watched(run, fixture, "coder")
    thread.start()
    try:
        deadline = time.monotonic() + 10.0
        while not gf.operator_gates_of(run) and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join(timeout=5.0)

    entry, = gf.operator_gates_of(run)
    assert entry["action"] == "parked"
    # Every lane, one behaviour. A coder gate asks about the state of a repo mid-round —
    # nothing written down before the round started could answer it, and the watcher was
    # never the thing that would have tried.
    assert gate.read_text(encoding="utf-8") == GATE


def test_a_context_file_that_is_not_a_gate_is_passed_over(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The globs are deliberately loose, and `gate_answered` is what makes that safe: a
    regenerated `qa-okf-context.md` carries no `AWAITING_OPERATOR` header, so it reads as
    answered rather than as a gate the harness should be touching."""
    noise = run.repo / "docs" / "specs" / "s" / "qa-okf-context.md"
    noise.parent.mkdir(parents=True)
    noise.write_text("# obligations\n\n- a thing\n", encoding="utf-8")
    # `expect=0`: the point is that nothing is ever recorded, so the watcher is given a
    # handful of polls and then stopped rather than waited on.
    watch_once(run, fixture, monkeypatch, expect=0)

    assert gf.operator_gates_of(run) == []
    assert noise.read_text(encoding="utf-8") == "# obligations\n\n- a thing\n"
