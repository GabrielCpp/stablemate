"""The committed user-journey suites: which ones this story touched, and how they ran.

Ports two scripts that only make sense together — `detect-regression-platform.py` picks the
platform, `run-regression-suite.py` runs it — so they share one module and one schema
subject.

Both are deliberately generous, and in opposite ways from the QA gates around them:

* The detector **fails open**. An unreadable `plan-context.json` yields `none`, which skips
  the whole regression step. It is a router, not a verdict, and a story with no UI must not
  be blocked by a file it never had reason to write.
* The runner treats **"nothing to run" as `passed`**. No `Makefile`, no `e2e-journeys`
  target, an empty `maestro_flows/` — a repo with no regression suite has not failed one.
  Only a real non-zero suite exit is `failed`; only an unreachable stack or emulator is
  `blocked`, which routes to the shared setup-repair loop rather than burning the
  regression-fix budget on something the fix agent cannot act on.

Two script-shaped things change. The runner printed its verdict twice — once as
`regression_run`, once trimmed to status/notes as `qa_result` — so the `blocked → setup_fix`
loop would see it; a node returns one model, and that mirror is now
`RegressionRun.as_qa_result()`, called at the flow's transition site. And the detector
carried its own `find_repo_root` and its own `_load_json`; both are the engine's now, the
latter because its `except (FileNotFoundError, json.JSONDecodeError, OSError) → {}` is
exactly `scriptutil.load_json`'s, differing only in which channel the diagnostic goes to.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workhorse.scriptutil import find_repo_root, load_json
from workhorse_workflows.coder.nodes._blueprint import blueprint
from workhorse_workflows.coder.schemas.qa import (
    FailureAttribution,
    RegressionPlatform,
    RegressionRun,
)
from workhorse_workflows.kit import resolve_workspace

#: Per-service `type` → regression platform (the `services` array, the current source).
UI_TYPE_PLATFORM = {"react-router": "web", "svelte": "web", "flutter": "mobile"}
#: Legacy flat `touched_layers` → platform. Narrower than the map above on purpose: it is
#: the pre-`services` vocabulary, and svelte post-dates it.
UI_LAYER_PLATFORM = {"react-router": "web", "flutter": "mobile"}

WEB_TYPES = {"react-router", "svelte"}
MOBILE_TYPES = {"flutter"}

# Generous outer wall-clock bound; `make e2e-journeys` already enforces its own inner
# `timeout 1200` — this only needs to outlive that plus process overhead.
WEB_TIMEOUT = 1500
MOBILE_TIMEOUT = 1500

# Playwright "list" reporter failure line:
#   "  1) [journeys] › e2e/journeys/foo.spec.ts:12:3 › name"
FAIL_LINE_RE = re.compile(r"^\s*\d+\)\s+\S.*?›\s+(\S+):\d+:\d+\s+›\s+(.+?)\s*=*\s*$", re.MULTILINE)
UNREACHABLE_RE = re.compile(r"not reachable on :")
NO_TARGET_RE = re.compile(r"no rule to make target", re.IGNORECASE)
NO_DEVICE_RE = re.compile(r"no devices found|unable to connect|device offline", re.IGNORECASE)
NO_FLOWS_RE = re.compile(r"do not contain any Flow files", re.IGNORECASE)

#: Worst-first, so `min` over this order picks the status that must win a merge.
STATUS_ORDER = {"blocked": 0, "failed": 1, "passed": 2}


def _service_cwds(
    plan_ctx: dict, repos: dict, types: set[str], logger: logging.Logger
) -> list[tuple[Path, str]]:
    """`(cwd, label)` for every matching service whose repo resolves in the workspace."""
    results: list[tuple[Path, str]] = []
    for svc in plan_ctx.get("services") or []:
        if svc.get("type") not in types:
            continue
        repo_path = repos.get(svc["repo"], {}).get("path")
        if not repo_path:
            logger.warning("repo '%s' not found in workspace — skipping service", svc["repo"])
            continue
        results.append((Path(repo_path) / svc["path"], f"{svc['repo']}::{svc.get('path', '.')}"))
    return results


def _sanitize_label(label: str) -> str:
    """Turn a `repo::path` label into a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", label).strip("-")


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int | None, str]:
    """Run a suite command, returning `(returncode, combined output)`.

    A `None` returncode means the command never produced one — it timed out, or the tool is
    not installed. Both are `blocked` to the caller, and both keep whatever output arrived.
    """
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False
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
    except FileNotFoundError as exc:
        return None, f"command not found: {exc}"


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


def _run_web_one(cwd: Path, label: str, qa_dir: str, logger: logging.Logger) -> RegressionRun:
    """One web service's `make e2e-journeys`.

    The target health-checks the real stack itself and exits 1 with a `not reachable on :`
    line per missing piece before running anything, so this reads that signal rather than
    duplicating the health check.
    """
    log_name = f"regression-run-web-{_sanitize_label(label)}.log"

    if not (cwd / "Makefile").exists():
        return RegressionRun(notes=f"no regression suite at {label} (no Makefile) — skipped")

    returncode, output = _run(["make", "e2e-journeys"], cwd, WEB_TIMEOUT)
    log_path = _write_log(qa_dir, log_name, output, logger)

    if returncode is None:
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes=(
                f"`make e2e-journeys` did not complete within {WEB_TIMEOUT}s — "
                f"the stack may be hung."
            ),
        )
    if NO_TARGET_RE.search(output):
        return RegressionRun(
            log_path=log_path, notes=f"no e2e-journeys make target at {label} — skipped"
        )
    if UNREACHABLE_RE.search(output):
        missing = [ln.strip() for ln in output.splitlines() if "not reachable on :" in ln]
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes="real stack not reachable: " + "; ".join(missing),
        )
    if returncode == 0:
        return RegressionRun(log_path=log_path, notes=f"make e2e-journeys exited 0 ({label})")

    failing = [f"{path}: {name}" for path, name in FAIL_LINE_RE.findall(output)]
    notes = f"make e2e-journeys exited {returncode} ({label})"
    notes += (
        f"; {len(failing)} failing test(s): " + "; ".join(failing[:10])
        if failing
        else f"; could not parse individual failures — tail:\n{_tail(output)}"
    )
    return RegressionRun(
        status="failed", failing_tests=failing, log_path=log_path, notes=notes
    )


def _run_mobile_one(cwd: Path, label: str, qa_dir: str, logger: logging.Logger) -> RegressionRun:
    """One mobile service's `maestro test <service>/maestro_flows/`."""
    log_name = f"regression-run-mobile-{_sanitize_label(label)}.log"

    flows_dir = cwd / "maestro_flows"
    # A committed-but-empty maestro_flows/ (no *.yaml/*.yml flow files anywhere under it) is
    # the same "nothing to run" case as a missing directory: `maestro test` on an empty dir
    # exits non-zero with "do not contain any Flow files", which none of the blocked/skip
    # patterns below recognize — without this check that gets misclassified as a real
    # regression failure and routes to fix_regression for a suite that doesn't exist.
    has_flows = flows_dir.is_dir() and (
        any(flows_dir.rglob("*.yaml")) or any(flows_dir.rglob("*.yml"))
    )
    if not has_flows:
        return RegressionRun(notes=f"no regression suite at {label}/maestro_flows/ — skipped")

    returncode, output = _run(["maestro", "test", str(flows_dir)], cwd, MOBILE_TIMEOUT)
    log_path = _write_log(qa_dir, log_name, output, logger)

    if returncode is None:
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes=(
                f"`maestro test` did not complete within {MOBILE_TIMEOUT}s — "
                f"the emulator/stack may be hung."
            ),
        )
    if NO_DEVICE_RE.search(output):
        return RegressionRun(
            status="blocked",
            log_path=log_path,
            notes="emulator/device not reachable for maestro test — see log",
        )
    if NO_FLOWS_RE.search(output):
        return RegressionRun(
            log_path=log_path, notes=f"no flow files at {label}/maestro_flows/ — skipped"
        )
    if returncode == 0:
        return RegressionRun(log_path=log_path, notes=f"maestro test exited 0 ({label})")

    failing = [
        ln.strip() for ln in output.splitlines() if "✗" in ln or re.search(r"\bFAILED\b", ln)
    ]
    notes = f"maestro test exited {returncode} ({label})"
    notes += (
        f"; {len(failing)} failing flow(s): " + "; ".join(failing[:10])
        if failing
        else f"; could not parse individual failures — tail:\n{_tail(output)}"
    )
    return RegressionRun(
        status="failed", failing_tests=failing, log_path=log_path, notes=notes
    )


def _merge_results(results: list[RegressionRun]) -> RegressionRun:
    """Merge N per-service results. Worst status wins; every note is kept."""
    if not results:
        return RegressionRun(notes="no services to run")
    if len(results) == 1:
        return results[0]
    return RegressionRun(
        status=min((r.status for r in results), key=lambda s: STATUS_ORDER[s]),
        failing_tests=[t for r in results for t in r.failing_tests],
        log_path="; ".join(p for r in results if (p := r.log_path)),
        notes=" | ".join(r.notes for r in results),
    )


def _run_platform(
    kind: str, repos: dict, plan_ctx: dict, qa_dir: str, logger: logging.Logger
) -> RegressionRun:
    """Run every resolved service of one platform.

    "The plan says web, and no web repo is in the workspace" is `blocked`, not a skip: the
    suite exists and could not be reached, which is a setup problem the repair loop can act
    on. That is the one asymmetry with the missing-suite cases above.
    """
    types, run_one = (
        (WEB_TYPES, _run_web_one) if kind == "web" else (MOBILE_TYPES, _run_mobile_one)
    )
    cwds = _service_cwds(plan_ctx, repos, types, logger)
    if not cwds:
        return RegressionRun(
            status="blocked",
            notes=f"platform={kind} but no matching service repo resolved in workspace",
        )
    return _merge_results([run_one(cwd, label, qa_dir, logger) for cwd, label in cwds])


def _same_test_path(left: str, right: str) -> bool:
    """Whether two test paths name the same file, either being repo- or service-relative."""
    left = left.removeprefix("./")
    right = right.removeprefix("./")
    return left == right or left.endswith(f"/{right}") or right.endswith(f"/{left}")


def _attribute_failures(result: RegressionRun, context: dict) -> RegressionRun:
    """Attach the OKF `verify:` owner of each failing test — diagnosis, never a downgrade."""
    if result.status != "failed" or not result.failing_tests:
        return result
    index = context.get("verificationIndex", [])
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
def detect_regression_platform(
    logger: logging.Logger, spec_dir: str = ""
) -> RegressionPlatform:
    """Did the approved plan touch a UI layer, and on which platform(s)?

    Reads the planner's `plan-context.json`. Its `services` array is the per-repo source of
    truth, so the platform comes from each entry's `type` and the touched `path`s are
    surfaced for the gate to scope its journeys; a legacy file carrying only the flat
    `touched_layers` list still resolves through the older map, without paths.
    """
    root = find_repo_root()
    plan_ctx = (
        load_json(root / spec_dir / "plan-context.json", "plan-context.json", logger)
        if spec_dir
        else {}
    )

    services = plan_ctx.get("services") or []
    if services:
        logger.info("deriving regression platform from %d service(s) in plan-context", len(services))
        ui_layers = [svc.get("type") for svc in services if svc.get("type") in UI_TYPE_PLATFORM]
        ui_paths = [
            f"{svc.get('repo', '')}::{svc.get('path', '.')}"
            for svc in services
            if svc.get("type") in UI_TYPE_PLATFORM
        ]
        platforms = sorted({UI_TYPE_PLATFORM[layer] for layer in ui_layers})
    else:
        logger.info("no services in plan-context — falling back to legacy touched_layers")
        touched = plan_ctx.get("touched_layers") or []
        ui_layers = [layer for layer in touched if layer in UI_LAYER_PLATFORM]
        ui_paths = []
        platforms = sorted({UI_LAYER_PLATFORM[layer] for layer in ui_layers})

    if not platforms:
        platform = "none"
    elif len(platforms) == 1:
        platform = platforms[0]
    else:
        platform = "both"

    logger.info("resolved regression platform=%s", platform)
    return RegressionPlatform(platform=platform, layers=ui_layers, paths=ui_paths)


@blueprint.node
def run_regression_suite(
    logger: logging.Logger,
    spec_dir: str = "",
    qa_dir: str = "",
    platform: str = "none",
) -> RegressionRun:
    """Run the committed user-journey suites for `platform` and report their own verdict.

    No LLM judgment anywhere: a clean exit is `passed`, a real suite failure is `failed`,
    and "the real stack isn't reachable" is `blocked`. Finds its services by reading the
    plan-context itself, the same convention as `detect_regression_platform`, rather than
    depending on a list-shaped argument.
    """
    root = find_repo_root()
    spec_path = root / spec_dir
    plan_ctx = (
        load_json(spec_path / "plan-context.json", "plan-context.json", logger) if spec_dir else {}
    )
    repos = resolve_workspace("CODER_WORKSPACE")

    if platform == "web":
        result = _run_platform("web", repos, plan_ctx, qa_dir, logger)
    elif platform == "mobile":
        result = _run_platform("mobile", repos, plan_ctx, qa_dir, logger)
    elif platform == "both":
        result = _merge_results(
            [
                _run_platform("web", repos, plan_ctx, qa_dir, logger),
                _run_platform("mobile", repos, plan_ctx, qa_dir, logger),
            ]
        )
    else:
        result = RegressionRun(notes=f"platform={platform!r} — nothing to run")

    context = (
        load_json(spec_path / "qa-okf-context.json", "qa-okf-context.json", logger)
        if spec_dir
        else {}
    )
    result = _attribute_failures(result, context)
    logger.info("regression run status=%s (%d failing)", result.status, len(result.failing_tests))
    return result


__all__ = ["detect_regression_platform", "run_regression_suite"]
