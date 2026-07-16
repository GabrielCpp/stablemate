"""The programmatic ``Ostler`` facade — same core the CLI dispatches to, reached
as a Python object instead of a subprocess. Mirrors ``test_query_select`` but
drives everything through the facade, and pins the load-once / invalidate-on-
mutation contract."""

from __future__ import annotations

from pathlib import Path

from ostler import Ostler


def test_reads_match_the_underlying_core(repo: Path):
    okf = Ostler(repo)
    assert {r["name"] for r in okf.list("epic")} == {"epic-a", "epic-b"}
    assert {r["slug"] for r in okf.list("story")} == {"01-foo", "01-bar"}
    assert {r["id"] for r in okf.list("seed", epic="epic-a")} == {"seed-a1", "seed-a2"}
    assert okf.next_epic()["name"] == "epic-a"
    assert okf.next_story("epic-a")["slug"] == "01-foo"


def test_query_and_search(repo: Path):
    okf = Ostler(repo)
    assert {x["id"] for x in okf.query("gaps-in-story", "01-foo")} == {"gap-x"}
    assert any(h["slug"] == "01-foo" for h in okf.search("thing works", etype="story"))


def test_path_resolution(repo: Path):
    okf = Ostler(repo)
    assert "01-foo" in okf.spec_path("01-foo")
    assert "01-foo" in okf.story_path("epic-a", "01-foo")
    assert okf.branch("01-foo") == "story/01-foo"
    assert okf.branch("epic-a", epic=True) == "feat/epic-a"


def test_doctor_returns_a_dict(repo: Path):
    report = Ostler(repo).doctor()
    assert isinstance(report, dict)
    assert "epics" in report


def test_graph_is_loaded_once_then_reused(repo: Path):
    okf = Ostler(repo)
    assert okf.graph is okf.graph  # cached snapshot, not reloaded per access
    first = okf.graph
    assert okf.reload().graph is not first  # reload() forces a fresh read


def test_mutation_invalidates_the_snapshot(repo: Path):
    okf = Ostler(repo)
    snapshot = okf.graph
    res = okf.set_status("01-foo", "QA passed")
    assert res.ok
    # the mutation dropped the cache, so the next read reflects disk, not the
    # pre-mutation snapshot: 01-foo is done, so epic-a has no runnable story left.
    assert okf.graph is not snapshot
    assert okf.next_story("epic-a") is None


def test_create_story_is_visible_to_the_next_read(repo: Path):
    okf = Ostler(repo)
    res = okf.create_story("epic-a", "02-baz", "Baz")
    assert res.ok
    assert "02-baz" in {r["slug"] for r in okf.list("story")}


def test_backlog_and_todo_round_trip(repo: Path):
    okf = Ostler(repo)
    assert okf.backlog() == []
    okf.backlog_add("BUG-1", "fix the thing")
    assert okf.backlog() == [{"id": "BUG-1", "text": "fix the thing"}]

    okf.todo_add("epic-a")
    assert "epic-a" in okf.todo()


# -- QA / artifact / edit subsystem facades ---------------------------------
def test_artifact_vet_reports_missing_artifact(repo: Path):
    out = Ostler(repo).artifact_vet("plan-context", "spec")
    assert out["kind"] == "plan-context"
    assert out["status"] == "error"
    assert "scaffold" in out["error"]


def test_qa_validate_missing_plan_is_invalid(repo: Path):
    outcome = Ostler(repo).qa_validate("nope.yml", spec="spec")
    assert outcome.ok is False
    assert outcome.status == "invalid"


def test_qa_context_validate_flags_a_bad_packet(repo: Path):
    spec = repo / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text("{}", encoding="utf-8")
    problems = Ostler(repo).qa_context_validate(spec=spec)
    assert problems  # a `{}` packet is not a valid context


def test_settle_review_errors_without_a_verdict(repo: Path):
    plan = Ostler(repo).settle_review("01-foo")
    assert plan.error  # no review-resolution.json on disk → an errored plan, nothing applied
