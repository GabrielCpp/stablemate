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
import hashlib
import importlib.util
import json
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

BENCHMARKS = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does."""
    saved = sys.path[:]
    sys.path.insert(0, str(BENCHMARKS / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


_spec = importlib.util.spec_from_file_location("_greenfield", BENCHMARKS / "tasks" / "_greenfield.py")
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
        task=loader.load_path(BENCHMARKS / "tasks" / "link_shortener.py"),
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
    rubric = (BENCHMARKS / "rubric.md").read_text(encoding="utf-8")
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
    rubric = (BENCHMARKS / "rubric.md").read_text(encoding="utf-8")

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
    for path in loader.task_paths(BENCHMARKS):
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
        backlog = BENCHMARKS / declared.backlog
        assert backlog.is_file(), f"{path.name}: no backlog at {backlog}"
        assert gf.parse_backlog(backlog), f"{path.name}: backlog has no `- [id] …` bullets"
        if declared.decisions:
            # The sheet versions with the seed and `check_public.py` scans it, both of which
            # need it to be a real tracked file under `benchmarks/` — and a task that names
            # one it does not have parks every round on a gate it thinks it has answered.
            sheet = BENCHMARKS / declared.decisions
            assert sheet.is_file(), f"{path.name}: no decision sheet at {sheet}"
    assert found, "no greenfield task declares a Fixture — the backlog-driven half is gone"


# ── the operator gate ─────────────────────────────────────────────────────────────────

SHEET = "# decisions\n\n## Creation contract\n\n`POST /links` answers `201 Created`.\n"

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


def sheeted(run: Run, fixture: Any, text: str = SHEET) -> Any:
    (run.data_dir / "docs" / "decisions.md").write_text(text, encoding="utf-8")
    return dataclasses.replace(fixture, decisions="docs/decisions.md")


def watch_once(run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch, *, expect: int) -> None:
    """Run the watcher until the ledger has `expect` entries, then stop it.

    The real watcher lives beside a phase that blocks for minutes; here it is driven to a
    quiescent point and joined, so the test asserts on a finished thread rather than on a
    race.
    """
    monkeypatch.setattr(gf, "GATE_POLL_S", 0.01)
    stop, thread = gf.gates_watched(run, fixture, "author")
    thread.start()
    try:
        deadline = time.monotonic() + 10.0
        while len(gf.operator_gates_of(run)) < expect and time.monotonic() < deadline:
            time.sleep(0.01)
        # A further poll's worth of grace, so a wrongly-repeated injection has time to show
        # up rather than being outrun by the stop.
        time.sleep(0.1)
    finally:
        stop.set()
        thread.join(timeout=5.0)
    assert not thread.is_alive(), "the watcher outlived the phase it was watching"


def test_the_watcher_answers_a_parked_gate_from_the_tracked_sheet(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The grill gate is human by construction, so an unattended round dies on it. The
    sheet is the operator, frozen — and the questions stay in the file beneath it, because
    what was answered is only readable beside what was asked."""
    gate = park(run)
    watch_once(run, sheeted(run, fixture), monkeypatch, expect=1)

    written = gate.read_text(encoding="utf-8")
    # The header, not an appended block: only the first `STATUS:` line is ever read.
    assert written.startswith("STATUS: ANSWERED\n")
    assert "AWAITING_OPERATOR" not in written
    assert "`POST /links` answers `201 Created`." in written
    assert "❓ **Q1** — what is the creation contract?" in written
    # workhorse's own reader is what the driver polls; it has to agree the gate is done.
    assert gf.gate_answered(gate)


def test_the_injection_is_recorded_with_the_sheet_it_applied(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An injected answer is an input to the round. An input nobody can see is the defect
    this whole seam exists to fix, so the path and the sha go in the ledger."""
    park(run)
    watch_once(run, sheeted(run, fixture), monkeypatch, expect=1)

    entry, = gf.operator_gates_of(run)
    assert entry["action"] == "answered"
    assert entry["gate"] == "docs/epics/_author-context.md"
    assert entry["sheet"] == "docs/decisions.md"
    assert entry["sha256"] == hashlib.sha256(SHEET.encode("utf-8")).hexdigest()


def test_a_gate_that_asks_again_stays_parked(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One injection per gate path, ever. A second park at the same file is the flow
    saying the sheet did not settle it — and the harness must not read the new question and
    decide for itself whether the sheet covers it. That judgement is the thing a benchmark
    cannot be making at gate time."""
    gate = park(run)
    fixture = sheeted(run, fixture)
    watch_once(run, fixture, monkeypatch, expect=1)
    gate.write_text(GATE.replace("Q1", "Q2"), encoding="utf-8")
    watch_once(run, fixture, monkeypatch, expect=2)

    # Left exactly as the flow re-asked it: parked, and the round waits.
    assert gate.read_text(encoding="utf-8").startswith("STATUS: AWAITING_OPERATOR")
    assert [e["action"] for e in gf.operator_gates_of(run)] == ["answered", "parked"]


def test_a_task_with_no_sheet_parks_and_says_so(
    run: Run, fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = park(run)
    watch_once(run, fixture, monkeypatch, expect=1)

    assert gate.read_text(encoding="utf-8") == GATE
    entry, = gf.operator_gates_of(run)
    assert entry["action"] == "parked"
    assert "no decision sheet" in entry["reason"]


def test_a_declared_sheet_that_is_missing_is_an_error_not_a_shrug(
    run: Run, fixture: Any
) -> None:
    """Read from the tracked data dir, never from the tree the round mutates — so a sheet
    that is not there is a broken `--data-dir`, and a round that silently ran without it
    would be the unrepeatable one all over again."""
    with pytest.raises(gf.TrialError, match="no decision sheet"):
        gf.decision_sheet(run, dataclasses.replace(fixture, decisions="docs/nope.md"))


def test_a_parked_gate_is_a_warning_on_the_score() -> None:
    lines = gf.warnings([], [], [{"gate": "docs/epics/_author-context.md",
                                 "action": "parked", "reason": "no decision sheet"}])
    assert any("stayed parked" in line for line in lines)
    assert not gf.warnings([], [], [{"gate": "g", "action": "answered",
                                     "sheet": "s", "sha256": "0" * 64}])
