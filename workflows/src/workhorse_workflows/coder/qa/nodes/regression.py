"""The committed user-journey suites: which ones this story touched, and how they ran."""
from __future__ import annotations

import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Literal, NamedTuple

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.dev import gate_command
from workhorse_workflows.coder.shared.schemas.qa import (
    FailureAttribution,
    RegressionRun,
    RegressionSuite,
    RegressionSuites,
)
from workhorse_workflows.kit import find_repo_root, load_json, resolve_workspace

REGRESSION_GATE = "regression"

SUITE_TIMEOUT = 1500

FAIL_LINE_RE = re.compile(r"^\s*\d+\)\s+\S.*?›\s+(\S+):\d+:\d+\s+›\s+(.+?)\s*=*\s*$", re.MULTILINE)
UNREACHABLE_RE = re.compile(
    r"not reachable on :|connection refused|no devices found|unable to connect|device offline",
    re.IGNORECASE,
)
NOTHING_TO_RUN_RE = re.compile(
    r"do not contain any Flow files|no tests? (files? )?found|no tests to run", re.IGNORECASE
)

STATUS_ORDER = {"error": 0, "blocked": 1, "failed": 2, "passed": 3, "skipped": 4}


def _sanitize_label(label: str) -> str:
    """Turn a `repo::path` label into a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", label).strip("-")


class _Outcome(NamedTuple):
    """What running one suite command produced."""

    returncode: int | None
    output: str
    started: bool = True


def _run(command: str, cwd: Path, timeout: int) -> _Outcome:
    """Run a declared suite command, returning what came of it."""
    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return _Outcome(result.returncode, (result.stdout or "") + (result.stderr or ""))
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode("utf-8", "replace")
            if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode("utf-8", "replace")
            if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
        return _Outcome(None, stdout + stderr)
    except (FileNotFoundError, ValueError) as exc:
        return _Outcome(None, f"could not run {command!r}: {exc}", started=False)


def _tail(output: str, n: int = 30) -> str:
    return "\n".join(output.strip().splitlines()[-n:])


def _write_log(qa_dir: str, name: str, output: str, logger: logging.Logger) -> str:
    """Persist the raw suite output; an unwritable log costs the path, not the run."""
    if not qa_dir:
        return ""
    try:
        qa_path = Path(qa_dir)
        qa_path.mkdir(parents=True, exist_ok=True)
        log_path = qa_path / name
        log_path.write_text(output, encoding="utf-8")
        return str(log_path)
    except OSError as exc:
        logger.warning("could not write regression log %s: %s", name, exc)
        return ""


def _run_one(suite: RegressionSuite, qa_dir: str, logger: logging.Logger) -> RegressionRun:
    """One service's declared journey command, in the five states the model carries."""
    label = suite.label
    cwd = Path(suite.cwd)
    if not suite.command:
        return RegressionRun(notes=f"no regression command declared for {label} — skipped")
    if not cwd.is_dir():
        return RegressionRun(
            status="error",
            notes=f"{label}: service directory {suite.cwd} does not exist, so `{suite.command}` "
            "could not be run",
        )

    returncode, output, started = _run(suite.command, cwd, SUITE_TIMEOUT)
    log_path = _write_log(
        qa_dir, f"regression-run-{_sanitize_label(label)}.log", output, logger
    )

    if not started:
        return RegressionRun(
            status="error",
            log_path=log_path,
            notes=f"`{suite.command}` could not be started ({label}) — see the output",
        )
    if returncode is None:
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes=(
                f"`{suite.command}` did not complete within {SUITE_TIMEOUT}s ({label}) — "
                "the stack under test may be hung"
            ),
        )
    if returncode == 0:
        return RegressionRun(
            status="passed", log_path=log_path, notes=f"`{suite.command}` exited 0 ({label})"
        )
    if NOTHING_TO_RUN_RE.search(output):
        return RegressionRun(
            log_path=log_path, notes=f"nothing to run for {label} — skipped"
        )
    if UNREACHABLE_RE.search(output):
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes=f"{label}: the stack under test was not reachable — see log",
        )

    failing = [f"{path}: {name}" for path, name in FAIL_LINE_RE.findall(output)]
    notes = f"`{suite.command}` exited {returncode} ({label})"
    notes += (
        f"; {len(failing)} failing test(s): " + "; ".join(failing[:10])
        if failing
        else f"; could not parse individual failures — tail:\n{_tail(output)}"
    )
    return RegressionRun(status="failed", failing_tests=failing, log_path=log_path, notes=notes)


def _merge_results(results: list[RegressionRun]) -> RegressionRun:
    """Merge N per-service results."""
    if not results:
        return RegressionRun(notes="no suites to run")
    if len(results) == 1:
        return results[0]
    return RegressionRun(
        status=min((r.status for r in results), key=lambda s: STATUS_ORDER[s]),
        failing_tests=[t for r in results for t in r.failing_tests],
        log_path="; ".join(p for r in results if (p := r.log_path)),
        notes=" | ".join(r.notes for r in results),
    )


def _same_test_path(left: str, right: str) -> bool:
    """Whether two test paths name the same file, either being repo- or service-relative."""
    left = left.removeprefix("./")
    right = right.removeprefix("./")
    return left == right or left.endswith(f"/{right}") or right.endswith(f"/{left}")


def _verification_index(spec_path: Path, spec_dir: str, logger: logging.Logger) -> list:
    """The whole-book verify table, from its sidecar file."""
    if not spec_dir:
        return []
    sidecar = load_json(
        spec_path / "qa-okf-verification-index.json", "qa-okf-verification-index.json", logger
    )
    if isinstance(sidecar, list):
        return sidecar
    context = load_json(spec_path / "qa-okf-context.json", "qa-okf-context.json", logger)
    index = context.get("verificationIndex", [])
    return index if isinstance(index, list) else []


def _attribute_failures(result: RegressionRun, index: list) -> RegressionRun:
    """Attach the OKF `tests:` owner of each failing test — diagnosis, never a downgrade."""
    if result.status != "failed" or not result.failing_tests:
        return result
    attribution = []
    for failure in result.failing_tests:
        test_path = failure.split(": ", 1)[0]
        owners = [
            item
            for item in index
            if isinstance(item, dict)
            and item.get("path")
            and _same_test_path(test_path, str(item["path"]))
        ]
        classification: Literal["impacted", "outside-impact", "unattributed"]
        if any(item.get("impacted") is True for item in owners):
            classification = "impacted"
        elif owners:
            classification = "outside-impact"
        else:
            classification = "unattributed"
        attribution.append(
            FailureAttribution(
                test=failure,
                path=test_path,
                classification=classification,
                nodes=sorted({str(item.get("node", "")) for item in owners}),
            )
        )
    return result.model_copy(update={"failure_attribution": attribution})


@blueprint.node
def detect_regression_suites(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", workspace_file: str = ""
) -> RegressionSuites:
    """Which committed journey suites did the approved plan put at risk?"""
    root = find_repo_root(repo_dir)
    plan_ctx = (
        load_json(root / spec_dir / "plan-context.json", "plan-context.json", logger)
        if spec_dir
        else {}
    )
    repos = resolve_workspace(workspace_file, repo_dir)

    suites: list[RegressionSuite] = []
    for svc in plan_ctx.get("services") or []:
        repo_name = svc.get("repo", "")
        path = svc.get("path", ".")
        label = f"{repo_name}::{path}"
        repo_path = repos.get(repo_name, {}).get("path")
        if not repo_path:
            logger.warning("repo '%s' not found in workspace — skipping service", repo_name)
            continue
        cwd = Path(repo_path) / path
        command = gate_command(
            REGRESSION_GATE, label, str(svc.get("type", "")), cwd, str(repo_path)
        )
        if not command:
            continue
        suites.append(RegressionSuite(label=label, cwd=str(cwd), command=command))

    logger.info("resolved %d declared regression suite(s)", len(suites))
    return RegressionSuites(suites=suites)


@blueprint.node
def run_regression_suite(
    logger: logging.Logger,
    spec_dir: str = "",
    qa_dir: str = "",
    suites: list | None = None,
    repo_dir: str = "",
) -> RegressionRun:
    """Run the declared journey suites and report their own verdict."""
    resolved = [RegressionSuite.model_validate(s) for s in (suites or [])]
    if not resolved:
        result = RegressionRun(notes="no service declares a regression suite — nothing to run")
    else:
        result = _merge_results([_run_one(suite, qa_dir, logger) for suite in resolved])

    spec_path = find_repo_root(repo_dir) / spec_dir
    result = _attribute_failures(result, _verification_index(spec_path, spec_dir, logger))
    logger.info("regression run status=%s (%d failing)", result.status, len(result.failing_tests))
    return result


__all__ = ["detect_regression_suites", "run_regression_suite"]
