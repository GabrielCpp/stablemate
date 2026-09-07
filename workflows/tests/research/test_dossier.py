"""The program dossier, on a compact extract of the tracebus record.

Every number asserted here is one the real program carried and the loop never
computed: the required effect against the seed noise of its own eval, the date the
frozen metric last moved, how many times a gate was killed and revived.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest

from workhorse_workflows.research.nodes import dossier as D
from workhorse_workflows.research.nodes.history import (
    HISTORY_NAME,
    append_history,
    bootstrap_history,
    read_history,
)
from workhorse_workflows.research.schemas import Dossier, FrozenTarget, HistoryEvent

FIXTURE = Path(__file__).parent / "fixtures" / "tracebus"
LOG = logging.getLogger("test.dossier")
TODAY = "2026-09-07"


@pytest.fixture
def program(tmp_path: Path) -> tuple[Path, str]:
    """The fixture copied into a git repo so churn and history have somewhere to go."""
    repo = tmp_path / "repo"
    dst = repo / "docs" / "research" / "tracebus"
    dst.parent.mkdir(parents=True)
    import shutil

    shutil.copytree(FIXTURE, dst)
    (repo / "src" / "phasor").mkdir(parents=True)
    (repo / "src" / "phasor" / "g1.py").write_text("x = 1\n" * 40)
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["-c", "user.email=t@t", "-c", "user.name=t", "add", "."], check=True)
    subprocess.run(
        git + ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "G1 rework"],
        check=True,
    )
    return repo, "docs/research/tracebus"


def _build(repo: Path, program_dir: str, **kw) -> Dossier:
    return D.build_dossier(
        LOG, str(repo), program_dir, f"{program_dir}/PROGRESS.md", "src/phasor",
        **{"today": TODAY, **kw},
    )


# ── parsers ─────────────────────────────────────────────────────────────────


def test_frozen_target_parses_the_readme_table():
    t = D.parse_frozen_target((FIXTURE / "README.md").read_text())
    assert (t.threshold_count, t.n) == (93, 147)
    assert t.threshold_value == pytest.approx(93 / 147)
    assert t.seeds == [0, 1, 2]
    assert t.deadline.startswith("2026-10-31")
    assert (t.baseline_count, t.baseline_source) == (83, "prose")
    assert "HARD-FN" in t.dataset


def test_frozen_target_without_section_is_reported_not_raised():
    unparsed: list[str] = []
    t = D.parse_frozen_target("# nothing here\n", unparsed)
    assert t.n == 0
    assert unparsed and "Frozen target" in unparsed[0]


def test_status_tables_split_active_from_superseded():
    unparsed: list[str] = []
    active, superseded = D.parse_status_table((FIXTURE / "PROGRESS.md").read_text(), unparsed)
    assert [r.gate_id for r in active] == ["G0", "G1", "G2", "G3", "G4"]
    g1 = active[1]
    assert g1.status.startswith("REOPENED")
    assert g1.date == "2026-09-07"
    by_id = {r.gate_id: r for r in superseded}
    assert "D1" in by_id and "BANKED" in by_id["D1"].status
    assert "D3" in by_id and "KILLED" in by_id["D3"].status
    # The deliberately malformed G5 row (five cells under a six-column header).
    assert any("G5" in u or "cells" in u for u in unparsed)


def test_dated_entries_are_classified():
    events = D.parse_dated_entries((FIXTURE / "PROGRESS.md").read_text())
    kinds = [(e.date, e.event, e.gate_id) for e in events]
    assert ("2026-09-05", "pass", "G0") in kinds
    assert ("2026-09-07", "kill", "G1") in kinds
    assert ("2026-09-07", "revive", "") in kinds
    assert any(e.event == "goal" and e.date == "2026-08-06" for e in events)
    assert any(e.event == "new_direction" for e in events)
    assert all(e.source == "bootstrap" for e in events)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("G1 first attempt: KILLED (preserved record)", "kill"),
        ("Reopening", "revive"),
        ("D3 cycle 2 closure: FAIL (FAIL_MAX_REWORKS)", "apparatus_kill"),
        ("Program verdict: GOAL_BANKED", "goal"),
        ("Direction defined", "new_direction"),
        ("G0 corrective off-policy probe: PASS", "pass"),
        ("G3b VERDICT after dig: FAIL", "fail"),
        ("G2: inversion (PRE-REGISTRATION)", "gate_selected"),
        ("some remark", "note"),
    ],
)
def test_classify_entry(title: str, expected: str):
    assert D.classify_entry(title) == expected


def test_jobs_read_seed_families_and_flags():
    unparsed: list[str] = []
    jobs = {j.gate_id: j for j in D.read_jobs(FIXTURE / "jobs", unparsed)}
    assert set(jobs) == {"G1", "G0", "D3"}  # -dry skipped
    g1 = jobs["G1"]
    assert g1.families["coverage"] == [34.0, 31.0, 36.0]
    assert g1.family_mean["coverage"] == pytest.approx(33.67, abs=0.01)
    assert g1.family_sd["coverage"] == pytest.approx(2.05, abs=0.01)
    assert g1.scalars["C"] == 101.0
    assert set(g1.flags) == {"apparatus_blocked", "precondition_tension"}
    assert g1.finished_at == "2026-09-07"
    assert g1.n_completed == g1.n_planned == 408
    assert jobs["D3"].flags == ["grammar_leak_flag"]
    assert jobs["D3"].scalars["corrective_primary_resolved_total"] == 83.0
    assert unparsed == []


def test_pending_results_skip_table_rows_and_spending():
    text = "| G2 | doc | G1 | NOT STARTED (pending G1) |\nspending 440k calls\nSWE READOUT PENDING\n"
    assert D.pending_results(text) == ["SWE READOUT PENDING"]


# ── the series and resolvability ────────────────────────────────────────────


def test_metric_series_and_last_move():
    text = (FIXTURE / "PROGRESS.md").read_text()
    frozen = D.parse_frozen_target((FIXTURE / "README.md").read_text())
    rows, sup = D.parse_status_table(text)
    jobs = D.read_jobs(FIXTURE / "jobs")
    entries = D.parse_dated_entries(text)
    series = D.metric_series(frozen, rows, sup, text, jobs, entries)
    counts = {(p.date, p.source): p.count for p in series}
    assert counts[("2026-07-19", "progress:section")] == 85
    assert counts[("2026-08-26", "job:corrective_primary_resolved_total")] == 83
    assert all(p.count != 93 for p in series), "the target itself is not an observation"
    assert all(p.count != 96 for p in series), "`>= 96/147` is a target mention"
    assert D.last_move(series) == "2026-07-19"


def test_resolvability_on_the_frozen_target():
    frozen = D.parse_frozen_target((FIXTURE / "README.md").read_text())
    r = D.resolvability(frozen, observed_seed_sd=2.05)
    assert r.required_effect == pytest.approx(10 / 147)
    assert r.ratio == pytest.approx(1.66, abs=0.05)
    assert r.resolvable is False
    assert r.per_seed_required == pytest.approx(3.33, abs=0.01)
    assert r.per_seed_se == pytest.approx(3.47, abs=0.05)
    assert "NOT resolvable" in r.statement


def test_resolvability_passes_with_a_bigger_eval_or_margin():
    big = FrozenTarget(threshold_count=300, n=500, baseline_count=260, seeds=[0, 1, 2])
    assert D.resolvability(big).resolvable is True
    margin = FrozenTarget(threshold_count=105, n=147, baseline_count=83, seeds=[0, 1, 2])
    assert D.resolvability(margin).resolvable is True
    assert "not computable" in D.resolvability(FrozenTarget(threshold_count=93, n=147)).statement


# ── the node ────────────────────────────────────────────────────────────────


def test_build_dossier_fires_the_tracebus_triggers(program):
    repo, pdir = program
    d = _build(repo, pdir, lead_reviews=6)
    assert d.frozen.threshold_count == 93
    assert d.moved_last_on == "2026-07-19"
    assert d.days_since_moved == 50
    assert d.days_to_deadline == 54
    assert d.resolvability.resolvable is False
    assert d.counts["kills"] >= 1 and d.counts["revives"] >= 2
    assert d.active_gate == "G1"
    assert {"apparatus_cycles>=2", "metric_stale", "unresolvable_effect", "reviews_exhausted"} <= set(d.triggers)
    assert "ceiling_below_target" not in d.triggers  # C = 101 >= 93
    assert d.circling and d.review_due
    assert any("SWE READOUT PENDING" in p for p in d.pending)
    assert d.churn.get("G1", 0) == 40
    assert any("cells" in u for u in d.unparsed)
    assert len(d.fingerprint) == 12
    # history bootstrapped from the progress file, once
    hist = repo / pdir / HISTORY_NAME
    assert hist.exists()
    n = len(read_history(hist))
    assert n == len(D.parse_dated_entries((FIXTURE / "PROGRESS.md").read_text()))
    _build(repo, pdir)
    assert len(read_history(hist)) == n


def test_review_due_is_deduped_by_fingerprint(program):
    repo, pdir = program
    d = _build(repo, pdir, lead_reviews=6)
    assert d.review_due
    append_history(LOG, str(repo), pdir, "program_review", fingerprint=d.fingerprint, today=TODAY)
    again = _build(repo, pdir, lead_reviews=6)
    assert again.fingerprint == d.fingerprint
    assert again.review_due is False
    periodic = _build(repo, pdir, lead_reviews=6, gate_cycles=3, review_every=3)
    assert periodic.review_due is True


def test_a_review_s_own_recharter_does_not_trigger_the_next_review(program):
    """Seen on tracebus: the re-charter fixed `unresolvable_effect`, the trigger set
    shrank, the fingerprint changed, and `start` wanted a second review at once. New
    evidence needs a gate to have cycled since the review — or another day."""
    repo, pdir = program
    d = _build(repo, pdir, lead_reviews=6)
    append_history(LOG, str(repo), pdir, "program_review", fingerprint="stale" + d.fingerprint, today=TODAY)
    same_day = _build(repo, pdir, lead_reviews=6, gate_cycles=0)
    assert same_day.circling and same_day.review_due is False
    after_a_gate = _build(repo, pdir, lead_reviews=6, gate_cycles=1)
    assert after_a_gate.review_due is True
    next_day = _build(repo, pdir, lead_reviews=6, gate_cycles=0, today="2026-09-08")
    assert next_day.review_due is True


def test_fresh_program_has_no_triggers(tmp_path: Path):
    pdir = tmp_path / "p"
    pdir.mkdir()
    (pdir / "README.md").write_text(
        "# P\n\n## North star\n\n### Frozen target\n\n| Field | Value |\n|---|---|\n"
        "| Metric | acc over seeds {0,1,2} |\n| Dataset | d |\n| Threshold | `>= 120/200` |\n"
        "| Baseline | `80/200` |\n| Deadline | 2027-01-01 |\n"
    )
    (pdir / "PROGRESS.md").write_text(
        "# P\n\n| Gate | Document | Depends on | Status | Result | Date |\n|---|---|---|---|---|---|\n"
        "| G0 | G0.md | - | NOT STARTED | | |\n"
    )
    d = D.build_dossier(LOG, str(tmp_path), "p", today=TODAY)
    assert d.frozen.baseline_source == "table"
    assert d.resolvability.resolvable is True
    assert d.triggers == [] and not d.circling and not d.review_due
    assert d.active_gate == "G0"


def test_render_and_summary_carry_the_statement(program):
    repo, pdir = program
    d = _build(repo, pdir, lead_reviews=6)
    text = D.render_dossier(d)
    assert d.resolvability.statement in text
    assert "| 2026-07-19 |" in text and "coverage=[34, 31, 36]" in text
    assert "## Could not parse" in text
    summary = D.summarize(d)
    assert summary.count("\n") == 4 and "unresolvable_effect" in summary


# ── history ─────────────────────────────────────────────────────────────────


def test_history_append_and_bootstrap(tmp_path: Path):
    (tmp_path / "p").mkdir()
    ev = append_history(LOG, str(tmp_path), "p", "kill", gate_id="G1", note="x" * 600, today=TODAY)
    assert ev.event == "kill" and len(ev.note) == 500
    path = tmp_path / "p" / HISTORY_NAME
    lines = path.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["gate_id"] == "G1"
    assert bootstrap_history(path, [HistoryEvent(date=TODAY, event="pass")]) is False
    assert len(read_history(path)) == 1
    path.write_text("not json\n" + lines[0] + "\n")
    assert [e.event for e in read_history(path)] == ["kill"]
