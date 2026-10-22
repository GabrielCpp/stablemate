"""The scenarios the last scored QA run did not pass, read off its run log."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ostler.qa.run_log import read_records

from workhorse_workflows.coder.shared import qa_support
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import FailedScenarios
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.kit.qa.schemas import QaPlanRun


def failed_scenario_ids(result: QaPlanRun) -> tuple[str, ...]:
    """The scenarios a failed run did not pass, sorted; empty for every other status."""
    if result.status != "failed":
        return ()
    scenarios = result.ostler.get("scenarios")
    if not isinstance(scenarios, dict):
        return ()
    return tuple(
        sorted(
            str(name)
            for name, outcome in scenarios.items()
            if isinstance(outcome, dict) and outcome.get("status") != "passed"
        )
    )


def failed_scenarios_arg(spec_dir: str, ids: Sequence[str]) -> list[dict[str, Any]]:
    """Each failed scenario with the assertions it failed, as the owner prompt lists them."""
    if not spec_dir or not ids:
        return []
    failed = qa_support.failed_assertions(qa_support.scored_run_log(Path(spec_dir)))
    return [{"id": sid, "failed_assertions": failed.get(sid, [])} for sid in ids]


def _last_session(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The records written since the newest `session_start`."""
    start = 0
    for index, record in enumerate(records):
        if record.get("kind") == "session_start":
            start = index
    return records[start:]


@blueprint.node
def last_failed_scenarios(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = ""
) -> FailedScenarios:
    """The scenarios whose asserts did not all pass in the last scored QA run of this spec dir."""
    spec = Path(spec_dir)
    if not spec.is_absolute():
        spec = find_repo_root(repo_dir) / spec
    log = qa_support.scored_run_log(spec)
    if not log.is_file():
        return FailedScenarios()
    records, _problems = read_records(log)
    ids = sorted(
        {
            str(record.get("scenario", "")).strip()
            for record in _last_session(records)
            if record.get("kind") == "assert"
            and str(record.get("result", "")).strip().upper() != "PASS"
            and str(record.get("scenario", "")).strip()
        }
    )
    logger.info("the last scored QA run left %d scenario(s) not passed", len(ids))
    return FailedScenarios(ids=ids)


__all__ = ["failed_scenario_ids", "failed_scenarios_arg", "last_failed_scenarios"]
