"""The reconcile gate measures a run's epics against the scope they held when the run started."""
from __future__ import annotations

import logging
from pathlib import Path

from _epics import epics_root
from ostler import Ostler
from workhorse_workflows.author.finalize.nodes import verify_reconcile
from workhorse_workflows.author.main.nodes import snapshot_epics

LOGGER = logging.getLogger("test.reconcile")
EPIC = "accounts"


def _graph(repo: Path) -> None:
    okf = Ostler(repo)
    assert okf.create_epic(EPIC, "Account access").ok
    assert okf.add_seed(EPIC, "credentials", status="researched", summary="Accept valid credentials").ok
    assert okf.create_story(EPIC, "sign-in", "Sign in", covers=["credentials"]).ok
    assert okf.create_story(EPIC, "sign-out", "Sign out", covers=["credentials"]).ok


def _epic_md() -> Path:
    return next(epics_root().glob("*/epic.md"))


def test_a_run_that_drops_a_story_it_started_with_fails_the_gate(repo: Path) -> None:
    _graph(repo)
    baseline = snapshot_epics(LOGGER, repo_dir=str(repo))
    text = _epic_md().read_text(encoding="utf-8")
    assert "### sign-out" in text
    _epic_md().write_text(text.replace("### sign-out", "### renamed"), encoding="utf-8")

    report = verify_reconcile(LOGGER, baseline.model_dump_json(), repo_dir=str(repo))

    assert not report.holds
    assert not report.skipped
    assert "[dropped-story]" in report.errors
    assert "story 'sign-out' was committed but is absent now" in report.errors


def test_a_run_that_drops_a_seed_it_started_with_fails_the_gate(repo: Path) -> None:
    _graph(repo)
    baseline = snapshot_epics(LOGGER, repo_dir=str(repo))
    text = _epic_md().read_text(encoding="utf-8")
    assert "### credentials" in text
    _epic_md().write_text(text.replace("### credentials", "### renamed"), encoding="utf-8")

    report = verify_reconcile(LOGGER, baseline.model_dump_json(), repo_dir=str(repo))

    assert "[dropped-seed]" in report.errors


def test_a_run_that_keeps_its_scope_holds(repo: Path) -> None:
    _graph(repo)
    baseline = snapshot_epics(LOGGER, repo_dir=str(repo))
    assert Ostler(repo).create_story(EPIC, "reset-password", "Reset password", covers=["credentials"]).ok

    report = verify_reconcile(LOGGER, baseline.model_dump_json(), repo_dir=str(repo))

    assert report.holds
    assert report.report == "reconcile vs run start: 1 epic(s) checked, 0 silent drop(s)"


def test_a_run_that_started_with_no_epics_skips(repo: Path) -> None:
    baseline = snapshot_epics(LOGGER, repo_dir=str(repo))
    assert baseline.epics == {}
    _graph(repo)

    report = verify_reconcile(LOGGER, baseline.model_dump_json(), repo_dir=str(repo))

    assert report.skipped
    assert not report.holds


def test_a_finalize_started_without_a_baseline_skips(repo: Path) -> None:
    _graph(repo)

    assert verify_reconcile(LOGGER, "", repo_dir=str(repo)).skipped
