#!/usr/bin/env python3
"""Deterministically run the committed user-journey regression suite.

No LLM judgment: a clean exit is `passed`, a real suite failure is `failed`,
and "the real stack isn't reachable" is `blocked` (routes to the existing
setup-fix loop instead of burning the regression-fix budget on something the
fix agent cannot act on).

When a service has no regression suite committed (no ``maestro_flows/`` for
mobile, no ``Makefile`` or no ``e2e-journeys`` target for web), the service is
**skipped** (``passed``) — not ``blocked``. A missing suite is not a setup
issue; it means the project simply has no regression flows to run.

Reads ``<spec_dir>/plan-context.json`` itself (same convention as
``detect-regression-platform.py``) to find the react-router/flutter service(s)
and their repo, rather than depending on a list-shaped CLI arg.

Args:
    argv[1]  spec_dir  — story's spec directory (repo-relative)
    argv[2]  qa_dir    — absolute path to <spec_dir>/qa/, for the raw run log
    argv[3]  platform  — "web" | "mobile" | "both" (from detect_regression)

Web: runs `make e2e-journeys` in the react-router service dir. That target
already health-checks the real stack (web/API/auth-emulator ports) and exits
1 with a "not reachable on :" line per missing piece before running anything
— this script reads that signal rather than duplicating the health check.

Mobile: runs `maestro test <service>/maestro_flows/` in the flutter service dir.

Output (stdout, JSON): {"regression_run": {"status": "passed"|"failed"|
"blocked", "failing_tests": [...], "log_path": "...", "notes": "..."},
"qa_result": {"status": ..., "notes": ...}}

``qa_result`` mirrors ``regression_run``'s status/notes verbatim so the existing
blocked → guard_setup → setup_fix loop (which reads `qa_result.notes`, same as
every other QA-phase blocked path) keeps working unchanged on the blocked case.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root, load_json, resolve_workspace

logger = logging.getLogger(__name__)

WEB_TYPES = {"react-router", "svelte"}
MOBILE_TYPES = {"flutter"}

# Generous outer wall-clock bound; `make e2e-journeys` already enforces its own
# inner `timeout 1200` — this only needs to outlive that plus process overhead.
WEB_TIMEOUT = 1500
MOBILE_TIMEOUT = 1500

# Playwright "list" reporter failure line: "  1) [journeys] › e2e/journeys/foo.spec.ts:12:3 › name"
FAIL_LINE_RE = re.compile(
    r"^\s*\d+\)\s+\S.*?›\s+(\S+):\d+:\d+\s+›\s+(.+?)\s*=*\s*$", re.MULTILINE
)
UNREACHABLE_RE = re.compile(r"not reachable on :")
NO_TARGET_RE = re.compile(r"no rule to make target", re.IGNORECASE)
STATUS_ORDER = {"blocked": 0, "failed": 1, "passed": 2}


def _find_services(plan_ctx: dict, types: set[str]) -> list[dict]:
    return [svc for svc in plan_ctx.get("services") or [] if svc.get("type") in types]


def _service_cwds(
    plan_ctx: dict, repos: dict, types: set[str]
) -> list[tuple[Path, str]]:
    """Return (cwd, label) for every matching service whose repo resolves."""
    services = _find_services(plan_ctx, types)
    results = []
    for svc in services:
        repo_info = repos.get(svc["repo"], {})
        repo_path = repo_info.get("path")
        if not repo_path:
            logger.warning(
                "repo '%s' not found in workspace — skipping service", svc["repo"]
            )
            continue
        label = f"{svc['repo']}::{svc.get('path', '.')}"
        results.append((Path(repo_path) / svc["path"], label))
    return results


def _sanitize_label(label: str) -> str:
    """Turn a repo::path label into a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", label).strip("-")


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int | None, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout
            if isinstance(exc.stdout, str)
            else (exc.stdout or b"").decode("utf-8", "replace")
        )
        stderr = (
            exc.stderr
            if isinstance(exc.stderr, str)
            else (exc.stderr or b"").decode("utf-8", "replace")
        )
        return None, stdout + stderr
    except FileNotFoundError as exc:
        return None, f"command not found: {exc}"


def _tail(output: str, n: int = 30) -> str:
    return "\n".join(output.strip().splitlines()[-n:])


def _write_log(qa_dir: str, name: str, output: str) -> str:
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


def _run_web_one(cwd: Path, label: str, qa_dir: str) -> dict:
    """Run the web regression suite for a single service."""
    log_name = f"regression-run-web-{_sanitize_label(label)}.log"

    if not (cwd / "Makefile").exists():
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": "",
            "notes": f"no regression suite at {label} (no Makefile) — skipped",
        }

    returncode, output = _run(["make", "e2e-journeys"], cwd, WEB_TIMEOUT)
    log_path = _write_log(qa_dir, log_name, output)

    if returncode is None:
        return {
            "status": "blocked",
            "failing_tests": [],
            "log_path": log_path,
            "notes": f"`make e2e-journeys` did not complete within {WEB_TIMEOUT}s — the stack may be hung.",
        }
    if NO_TARGET_RE.search(output):
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": log_path,
            "notes": f"no e2e-journeys make target at {label} — skipped",
        }
    if UNREACHABLE_RE.search(output):
        missing = [
            ln.strip() for ln in output.splitlines() if "not reachable on :" in ln
        ]
        return {
            "status": "blocked",
            "failing_tests": [],
            "log_path": log_path,
            "notes": "real stack not reachable: " + "; ".join(missing),
        }
    if returncode == 0:
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": log_path,
            "notes": f"make e2e-journeys exited 0 ({label})",
        }

    failing = [f"{path}: {name}" for path, name in FAIL_LINE_RE.findall(output)]
    notes = f"make e2e-journeys exited {returncode} ({label})"
    notes += (
        f"; {len(failing)} failing test(s): " + "; ".join(failing[:10])
        if failing
        else f"; could not parse individual failures — tail:\n{_tail(output)}"
    )
    return {
        "status": "failed",
        "failing_tests": failing,
        "log_path": log_path,
        "notes": notes,
    }


def _run_mobile_one(cwd: Path, label: str, qa_dir: str) -> dict:
    """Run the mobile regression suite for a single service."""
    log_name = f"regression-run-mobile-{_sanitize_label(label)}.log"

    flows_dir = cwd / "maestro_flows"
    # A committed-but-empty maestro_flows/ (no *.yaml/*.yml flow files anywhere under it)
    # is the same "nothing to run" case as a missing directory: `maestro test` on an
    # empty dir exits non-zero with "do not contain any Flow files", which none of the
    # blocked/skip regexes below recognize — without this check that gets misclassified
    # as a real regression failure and routes to fix_regression for a suite that doesn't
    # exist.
    has_flows = flows_dir.is_dir() and (
        any(flows_dir.rglob("*.yaml")) or any(flows_dir.rglob("*.yml"))
    )
    if not has_flows:
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": "",
            "notes": f"no regression suite at {label}/maestro_flows/ — skipped",
        }

    returncode, output = _run(["maestro", "test", str(flows_dir)], cwd, MOBILE_TIMEOUT)
    log_path = _write_log(qa_dir, log_name, output)

    if returncode is None:
        return {
            "status": "blocked",
            "failing_tests": [],
            "log_path": log_path,
            "notes": f"`maestro test` did not complete within {MOBILE_TIMEOUT}s — the emulator/stack may be hung.",
        }
    if re.search(
        r"no devices found|unable to connect|device offline", output, re.IGNORECASE
    ):
        return {
            "status": "blocked",
            "failing_tests": [],
            "log_path": log_path,
            "notes": "emulator/device not reachable for maestro test — see log",
        }
    if re.search(r"do not contain any Flow files", output, re.IGNORECASE):
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": log_path,
            "notes": f"no flow files at {label}/maestro_flows/ — skipped",
        }
    if returncode == 0:
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": log_path,
            "notes": f"maestro test exited 0 ({label})",
        }

    failing = [
        ln.strip()
        for ln in output.splitlines()
        if "✗" in ln or re.search(r"\bFAILED\b", ln)
    ]
    notes = f"maestro test exited {returncode} ({label})"
    notes += (
        f"; {len(failing)} failing flow(s): " + "; ".join(failing[:10])
        if failing
        else f"; could not parse individual failures — tail:\n{_tail(output)}"
    )
    return {
        "status": "failed",
        "failing_tests": failing,
        "log_path": log_path,
        "notes": notes,
    }


def _merge_results(results: list[dict]) -> dict:
    """Merge N per-service results. Worst status wins."""
    if not results:
        return {
            "status": "passed",
            "failing_tests": [],
            "log_path": "",
            "notes": "no services to run",
        }
    if len(results) == 1:
        return results[0]
    status = min((r["status"] for r in results), key=lambda s: STATUS_ORDER[s])
    return {
        "status": status,
        "failing_tests": [t for r in results for t in r["failing_tests"]],
        "log_path": "; ".join(p for r in results if (p := r["log_path"])),
        "notes": " | ".join(r["notes"] for r in results),
    }


def _run_web(repos: dict, plan_ctx: dict, qa_dir: str) -> dict:
    cwds = _service_cwds(plan_ctx, repos, WEB_TYPES)
    if not cwds:
        return {
            "status": "blocked",
            "failing_tests": [],
            "log_path": "",
            "notes": "platform=web but no matching service repo resolved in workspace",
        }
    return _merge_results([_run_web_one(cwd, label, qa_dir) for cwd, label in cwds])


def _run_mobile(repos: dict, plan_ctx: dict, qa_dir: str) -> dict:
    cwds = _service_cwds(plan_ctx, repos, MOBILE_TYPES)
    if not cwds:
        return {
            "status": "blocked",
            "failing_tests": [],
            "log_path": "",
            "notes": "platform=mobile but no matching service repo resolved in workspace",
        }
    return _merge_results([_run_mobile_one(cwd, label, qa_dir) for cwd, label in cwds])


def _merge(web: dict, mobile: dict) -> dict:
    return _merge_results([web, mobile])


def main(logger: logging.Logger) -> None:
    spec_dir = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    qa_dir = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ""
    platform = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "none"

    root = find_repo_root()
    plan_ctx = (
        load_json(root / spec_dir / "plan-context.json", "plan-context.json", logger)
        if spec_dir
        else {}
    )
    repos = resolve_workspace("CODER_WORKSPACE")

    if platform == "web":
        result = _run_web(repos, plan_ctx, qa_dir)
    elif platform == "mobile":
        result = _run_mobile(repos, plan_ctx, qa_dir)
    elif platform == "both":
        result = _merge(
            _run_web(repos, plan_ctx, qa_dir), _run_mobile(repos, plan_ctx, qa_dir)
        )
    else:
        result = {
            "status": "passed",
            "failing_tests": [],
            "log_path": "",
            "notes": f"platform={platform!r} — nothing to run",
        }

    print(
        json.dumps(
            {
                "regression_run": result,
                "qa_result": {"status": result["status"], "notes": result["notes"]},
            }
        )
    )


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )
    main(logging.getLogger("run-regression-suite"))
