"""`load_survey_config` and `check_inventory` — the two nodes that decide where the
survey's artifacts live and whether the granularity planner runs at all.

These are the ported `surveyor/scripts/{load-config,check-inventory}.py`, and the parity
claim is on their *decisions*: which path convention each key gets, that a missing rubric
halts the run, and the precedence of frozen-inventory over pinned-rules over plan.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.surveyor.nodes import check_inventory, load_survey_config

Write = Callable[[Path, str], Path]


def test_the_config_derives_every_path_from_survey_dir(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / "docs/survey/rubric.md", "# concern\n")

    cfg = load_survey_config(logger)

    assert cfg.repo_root == str(repo)
    # Repo-relative, every one of them: the scripts put relative strings in `cfg` and
    # the nodes downstream join them against the repo root themselves.
    assert cfg.rubric == "docs/survey/rubric.md"
    assert cfg.survey_dir == "docs/survey"
    assert cfg.rules == "docs/survey/units.yml"
    assert cfg.inventory == "docs/survey/inventory.json"
    assert cfg.findings_dir == "docs/survey/findings"
    assert cfg.partition == "docs/survey/partition.yaml"
    assert cfg.unit_manifest == "docs/survey/unit-manifest.json"
    assert cfg.context == "docs/survey/_survey-context.md"
    assert cfg.backlog == "docs/backlog.md"


def test_survey_dir_moves_the_whole_convention_with_it(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """The parity surveyor runs under `docs/survey/legacy-vs-new` the same way."""
    write(repo / "docs/survey/legacy-vs-new/rubric.md", "# concern\n")

    cfg = load_survey_config(
        logger,
        rubric="docs/survey/legacy-vs-new/rubric.md",
        survey_dir="docs/survey/legacy-vs-new",
        backlog="docs/backlog.md",
    )

    assert cfg.inventory == "docs/survey/legacy-vs-new/inventory.json"
    assert cfg.findings_dir == "docs/survey/legacy-vs-new/findings"


def test_blank_parameters_fall_back_to_the_defaults(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """`--params '{"rubric": ""}'` and an unset var reach the node the same way, which
    is why the script stripped each argument before defaulting it."""
    write(repo / "docs/survey/rubric.md", "# concern\n")

    cfg = load_survey_config(logger, rubric="  ", survey_dir="", backlog=" ")

    assert cfg.rubric == "docs/survey/rubric.md"
    assert cfg.survey_dir == "docs/survey"
    assert cfg.backlog == "docs/backlog.md"


def test_a_missing_rubric_halts_the_run(repo: Path, logger: logging.Logger) -> None:
    """The rubric is the surveyor's only project-facing input: without it the planner
    and the assessors would hallucinate the concern being surveyed."""
    with pytest.raises(WorkflowFailed) as caught:
        load_survey_config(logger)

    message = str(caught.value)
    assert "rubric file not found" in message
    assert str(repo / "docs/survey/rubric.md") in message
    assert "--params" in message  # the fix travels with the halt


def test_an_existing_inventory_freezes_the_enumeration(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """A resume must consume the *same* list — a re-planned one would silently break
    the coverage claim, so the inventory outranks even a rules file sitting beside it."""
    write(repo / "docs/survey/inventory.json", '{"units": []}\n')
    write(repo / "docs/survey/units.yml", "rules: []\n")

    check = check_inventory(logger)

    assert check.needs_plan is False
    assert "frozen" in check.check_note


def test_pinned_rules_skip_the_planner(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """For the day the planner misjudges a repo: an operator writes the rules by hand."""
    write(repo / "docs/survey/units.yml", "rules: []\n")

    check = check_inventory(logger)

    assert check.needs_plan is False
    assert "planner skipped" in check.check_note


def test_with_neither_the_planner_gets_its_one_judgment(
    repo: Path, logger: logging.Logger
) -> None:
    check = check_inventory(logger)

    assert check.needs_plan is True
    assert "no inventory or rules yet" in check.check_note
