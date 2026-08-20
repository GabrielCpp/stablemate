"""The committed user-journey suites: which ones this story touched, and how they ran.

Two nodes that only make sense together — `detect_regression_suites` resolves which suites
the plan put at risk, `run_regression_suite` runs them — so they share one module and one
schema subject.

Both are deliberately generous, and in opposite ways from the QA gates around them:

* The detector **fails open**. An unreadable `plan-context.json` resolves no suites, which
  skips the whole regression step. It is a router, not a verdict, and a story whose services
  run no journeys must not be blocked by a file it never had reason to write.
* The runner treats **"nothing to run" as `passed`**. A service that declares no
  `regression:` command has no regression suite, and a repo with no suite has not failed
  one. Only a real non-zero exit is `failed`; only an unreachable stack, device or emulator
  is `blocked`, which routes to the shared setup-repair loop rather than burning the
  regression-fix budget on something the fix agent cannot act on.

**What runs comes out of the repo, not out of this file** (invariant 1). Each service's
`regression:` key in `agents.yml` is resolved through the same `gate_command` ladder as
`lint` and `test`, so a stack this package has never heard of gets its journeys run the day
it writes the command down. What used to be here instead was a map from four service *type*
names to two hard-coded commands — a repo running its journeys any third way could not say
so, and a service whose type was not on the list was silently exempt from a suite it really
had. The one migration cost is the reverse: a repo that relied on the implicit
`make e2e-journeys` target has no regression step until it declares `regression:` (or renames
that target to `make regression`, which the convention fallback still finds). Losing a gate
loudly at the point of declaration beats running the wrong one forever.

The runner prints one verdict. The `blocked → setup_fix` loop reads the trimmed status/notes
mirror through `RegressionRun.as_qa_result()`, called at the flow's transition site.
"""
from __future__ import annotations

import logging
import re
import shlex
import subprocess
from pathlib import Path

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.dev import gate_command
from workhorse_workflows.coder.shared.schemas.qa import (
    FailureAttribution,
    RegressionRun,
    RegressionSuite,
    RegressionSuites,
)
from workhorse_workflows.kit import find_repo_root, load_json, resolve_workspace

#: The `agents.yml` key a service declares its journey suite under.
REGRESSION_GATE = "regression"

#: Generous outer wall-clock bound. A journey suite that enforces its own inner timeout only
#: needs this to outlive it plus process overhead; one that does not is hung by now anyway.
SUITE_TIMEOUT = 1500

#: A failure line shaped `<path>:<line>:<col> › <name>`, which several journey runners print
#: and which is worth reading when it is there. Diagnosis only — an unparsed failure falls
#: back to the log tail, so a runner that prints some other shape still reports `failed`.
FAIL_LINE_RE = re.compile(r"^\s*\d+\)\s+\S.*?›\s+(\S+):\d+:\d+\s+›\s+(.+?)\s*=*\s*$", re.MULTILINE)
#: "The thing under test isn't there" — a setup problem, not a regression. These read the
#: shapes suites print when a service, device or emulator is missing; none names a tool.
UNREACHABLE_RE = re.compile(
    r"not reachable on :|connection refused|no devices found|unable to connect|device offline",
    re.IGNORECASE,
)
#: "There is nothing here to run" — a skip, and never a failure.
NOTHING_TO_RUN_RE = re.compile(
    r"do not contain any Flow files|no tests? (files? )?found|no tests to run", re.IGNORECASE
)

#: Worst-first, so `min` over this order picks the status that must win a merge.
STATUS_ORDER = {"blocked": 0, "failed": 1, "passed": 2}


def _sanitize_label(label: str) -> str:
    """Turn a `repo::path` label into a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", label).strip("-")


def _run(command: str, cwd: Path, timeout: int) -> tuple[int | None, str]:
    """Run a declared suite command, returning `(returncode, combined output)`.

    A `None` returncode means the command never produced one — it timed out, or the tool it
    names is not installed. Both are `blocked` to the caller, and both keep the output.
    """
    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(
            "utf-8", "replace"
        )
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(
            "utf-8", "replace"
        )
        return None, stdout + stderr
    except (FileNotFoundError, ValueError) as exc:
        return None, f"could not run {command!r}: {exc}"


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
    """One service's declared journey command, classified into passed/failed/blocked."""
    label = suite.label
    cwd = Path(suite.cwd)
    if not suite.command:
        return RegressionRun(notes=f"no regression command declared for {label} — skipped")
    if not cwd.is_dir():
        return RegressionRun(
            status="blocked", notes=f"{label}: service directory {suite.cwd} does not exist"
        )

    returncode, output = _run(suite.command, cwd, SUITE_TIMEOUT)
    log_path = _write_log(
        qa_dir, f"regression-run-{_sanitize_label(label)}.log", output, logger
    )

    if returncode is None:
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes=(
                f"`{suite.command}` did not complete within {SUITE_TIMEOUT}s or could not "
                f"start ({label}) — the stack may be hung, or the tool absent"
            ),
        )
    if returncode == 0:
        return RegressionRun(log_path=log_path, notes=f"`{suite.command}` exited 0 ({label})")
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
    """Merge N per-service results. Worst status wins; every note is kept."""
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
    """The whole-book verify table, from its sidecar file.

    It used to be a member of `qa-okf-context.json`, where it was the bulk of a packet a
    planning agent reads in full while only this node ever read that member. Ostler writes
    it beside the packet now; a run whose context predates the split still carries it
    inline, so fall back there rather than losing attribution on a resumed story.
    """
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
    """Which committed journey suites did the approved plan put at risk?

    Reads the planner's `plan-context.json`, whose `services` array is the per-repo source of
    truth, and asks each touched service what it declares under `regression:`. A service that
    declares nothing contributes nothing, and a plan that touched no declaring service leaves
    the list empty — which is how a backend-only story skips the step without anyone having
    to enumerate which stacks have journeys.
    """
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
    """Run the declared journey suites and report their own verdict.

    No LLM judgment anywhere: a clean exit is `passed`, a real suite failure is `failed`, and
    "the stack under test isn't reachable" is `blocked`.
    """
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
