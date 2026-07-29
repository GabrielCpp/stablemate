"""Tests for the benchmark harness.

These cover the properties that make the score trustworthy, and nothing else — a
benchmark whose own scoring is wrong is worse than no benchmark, but its table
formatting is not load-bearing.

The properties:

* a node that slept on a usage cap is NEVER flagged as a hang, while one that did the
  same wall-clock in ACTIVE work is;
* a judge's behavioral claim is capped unless it cites paths that actually exist;
* the structural trace never invents a behavioral claim of its own.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("bench", Path(__file__).parents[1] / "bench.py")
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
    spec_path = tmp_path / "bench.yml"
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
    monkeypatch.setattr(bench, "WORKFLOWS", spec.target)  # no source → no staleness noise
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


def judge(spec: "bench.Spec", bullet: dict, response: str) -> dict:
    rubric = (Path(__file__).parents[1] / "rubric.md").read_text(encoding="utf-8")
    return bench.judge_one(spec, bullet, rubric, FakeBackend(response))


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
    backend = FakeBackend(json.dumps({"level": 0, "evidence": [], "reason": "x"}))
    rubric = (Path(__file__).parents[1] / "rubric.md").read_text(encoding="utf-8")

    bench.judge_one(spec, bullet, rubric, backend)
    prompt = backend.prompts[0]
    assert "{{" not in prompt
    assert "todo-create" in prompt and "api-create" in prompt and "QA passed" in prompt


def test_render_leaves_json_braces_alone(spec: "bench.Spec"):
    """The rubric shows the judge a JSON shape; single braces must survive rendering."""
    out = bench.render('{"level": 2} and {{bullet_id}}', bullet_id="todo-create")
    assert out == '{"level": 2} and todo-create'
