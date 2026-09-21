"""Where the survey's artifacts live, and whether the planner runs at all."""
from __future__ import annotations

import logging

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.survey.blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.survey import InventoryCheck, SurveyConfig


@blueprint.node
def load_survey_config(
    logger: logging.Logger,
    rubric: str = "docs/survey/rubric.md",
    survey_dir: str = "docs/survey",
    repo_dir: str = "",
) -> SurveyConfig:
    """Resolve the survey's paths and prove the rubric exists."""
    rubric = rubric.strip() or "docs/survey/rubric.md"
    survey_dir = survey_dir.strip() or "docs/survey"

    root = survey_repo_root(repo_dir)
    backlog = paths.backlog_file(root)
    rubric_path = (root / rubric).resolve()
    if not rubric_path.is_file():
        logger.warning("rubric file not found: %s", rubric_path)
        raise WorkflowFailed(
            f"rubric file not found: {rubric_path}\n"
            f"Create {rubric} (a markdown document defining the cross-cutting concern being "
            f"surveyed: what counts as a finding, what 'clean' means, and which repo skills "
            f"the assessors should read) before running the surveyor workflow, or pass "
            f"--params '{{\"rubric\":\"<path>\"}}'.",
            failure_class="surveyor-rubric-missing",
            artifacts={"rubric": str(rubric_path)},
        )

    logger.info(
        "config loaded: rubric=%s survey_dir=%s repo_root=%s", rubric, survey_dir, root
    )
    return SurveyConfig(
        repo_root=str(root),
        rubric=rubric,
        survey_dir=survey_dir,
        rules=f"{survey_dir}/units.yml",
        inventory=f"{survey_dir}/inventory.json",
        findings_dir=f"{survey_dir}/findings",
        partition=f"{survey_dir}/partition.yaml",
        backlog=backlog,
        unit_manifest=f"{survey_dir}/unit-manifest.json",
        context=f"{survey_dir}/_survey-context.md",
    )


@blueprint.node
def check_inventory(
    logger: logging.Logger,
    inventory: str = "docs/survey/inventory.json",
    rules: str = "docs/survey/units.yml",
    repo_dir: str = "",
) -> InventoryCheck:
    """Decide whether the granularity planner needs its one bounded judgment."""
    inventory_rel = inventory.strip() or "docs/survey/inventory.json"
    rules_rel = rules.strip() or "docs/survey/units.yml"

    root = survey_repo_root(repo_dir)
    if (root / inventory_rel).is_file():
        note = f"inventory {inventory_rel} already exists — frozen; the planner never re-runs"
        logger.info(note)
    elif (root / rules_rel).is_file():
        note = f"rules {rules_rel} already exist (operator-pinned or prior run) — planner skipped"
        logger.info(note)
    else:
        note = "no inventory or rules yet — the planner decides the enumeration rules"
        logger.info(note)
        return InventoryCheck(needs_plan=True, check_note=note)
    return InventoryCheck(needs_plan=False, check_note=note)


__all__ = ["check_inventory", "load_survey_config"]
