"""The deterministic red gate between the tests turn and the code turn.

The dev flow splits implementation into two agent turns — `implement-plan-tests.md` writes
the failing tests, `implement-plan-code.md` makes them green — and this module is the
tooling between them that makes the split *enforced* rather than requested. Two nodes:

* `arm_red_gate` runs **before** the tests turn. It records the service worktree's changed
  paths (so the gate can later diff what that turn alone touched), resolves the test command
  the gate will run, resolves the test-file signatures purity is judged by, and reads the
  plan for the planner's `Test scenarios: regression-only` escape.
* `run_red_gate` runs **after** the tests turn. It checks the turn's diff is pure (test
  files only, by signature), then runs the suite and demands a genuine failure: the tests
  must be red *because the behavior is missing* before the code turn is allowed to start.
  A green suite, an impure diff or an empty diff routes back to the tests turn.

Command resolution is the lint gate's convention-plus-override, applied to `test`: an
explicit `agents.yml` entry (`test:` or `workflow.test:`, keyed by service name or cwd
basename) wins, otherwise `make test` when the Makefile defines that target, otherwise
there is nothing to run and the red observation is `skipped` — fail-open, like `run_lint`,
because a service that has not adopted a test command is not thereby failing. Purity is
still enforced in that case: it needs only git, not a suite.
"""
from __future__ import annotations

import fnmatch
import logging
import re
import subprocess
from pathlib import Path

import yaml
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import RedGateArm, RedGateOutcome

#: The planner's plan-time escape hatch, matched case-insensitively in the layer's plan
#: file and the root plan.md. `plan-story.md` specifies this literal phrasing.
REGRESSION_ONLY_MARKER = "test scenarios: regression-only"

#: Basename patterns that identify a test file across the stacks the workflows target.
#: An `agents.yml` `test_signatures:` entry for the service replaces this list.
DEFAULT_TEST_SIGNATURES = (
    "test_*.py",
    "*_test.py",
    "*_test.go",
    "*_test.dart",
    "*.test.ts",
    "*.test.tsx",
    "*.test.js",
    "*.test.jsx",
    "*.spec.ts",
    "*.spec.tsx",
)

#: Directory segments that mark everything under them as test code, whatever the basename —
#: fixtures, helpers, golden files all legitimately live beside the tests.
TEST_DIR_SEGMENTS = {"tests", "__tests__", "test", "spec"}

#: Seconds the red run gets before the gate stands aside rather than blocking the layer.
RED_GATE_TIMEOUT = 600


def _spec_abs(spec_dir: str, repo_dir: str) -> Path | None:
    """The spec dir as an absolute path, or None when no spec dir was given."""
    if not spec_dir:
        return None
    path = Path(spec_dir)
    return path if path.is_absolute() else find_repo_root(repo_dir) / path


def _worktree_changes(cwd: Path) -> list[str] | None:
    """Changed paths (tracked and untracked) in cwd's repo, or None when git cannot say.

    Paths come back relative to the repo root, which is fine: the baseline and the
    post-turn snapshot are taken the same way, so the subtraction compares like with like.
    A rename is charged to its new path.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    changes: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changes.append(path.strip().strip('"'))
    return changes


def _agents_yml_map(key: str, repo_dir: str) -> dict:
    """A `{service-or-dir: value}` map from the orchestrating repo's agents.yml.

    Looked up under `<key>:` or `workflow.<key>:`, the same two spellings `run_lint`'s
    override accepts for `lint`.
    """
    cfg_path = find_repo_root(repo_dir) / "agents.yml"
    if not cfg_path.exists():
        return {}
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    mapping = cfg.get(key) or (cfg.get("workflow") or {}).get(key) or {}
    return mapping if isinstance(mapping, dict) else {}


def _has_make_target(cwd: Path, target: str) -> bool:
    """Whether this service's Makefile defines `target`."""
    if not (cwd / "Makefile").exists() and not (cwd / "makefile").exists():
        return False
    try:
        probe = subprocess.run(
            ["make", "-n", target], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _test_command(service: str, cwd: Path, repo_dir: str) -> str:
    """The service's test command: agents.yml override, else `make test`, else nothing."""
    override = _agents_yml_map("test", repo_dir)
    command = str(override.get(service) or override.get(cwd.name) or "").strip()
    if command:
        return command
    return "make test" if _has_make_target(cwd, "test") else ""


def _test_signatures(service: str, cwd: Path, repo_dir: str) -> list[str]:
    """The basename patterns purity is judged by; an agents.yml override replaces defaults."""
    override = _agents_yml_map("test_signatures", repo_dir)
    patterns = override.get(service) or override.get(cwd.name)
    if isinstance(patterns, list) and patterns:
        return [str(p) for p in patterns]
    return list(DEFAULT_TEST_SIGNATURES)


def _is_test_path(path: str, signatures: list[str]) -> bool:
    """Whether a changed path counts as test code under the given signatures."""
    parts = Path(path).parts
    if any(part in TEST_DIR_SEGMENTS for part in parts[:-1]):
        return True
    name = parts[-1] if parts else path
    return any(fnmatch.fnmatch(name, pattern) for pattern in signatures)


def _plans_declare_regression_only(spec_abs: Path | None, plan_file: str) -> bool:
    """Whether the layer's plan or the root plan declares the regression-only escape."""
    if spec_abs is None:
        return False
    for name in dict.fromkeys((plan_file, "plan.md")):
        if not name:
            continue
        try:
            text = (spec_abs / name).read_text(encoding="utf-8")
        except OSError:
            continue
        if REGRESSION_ONLY_MARKER in text.lower():
            return True
    return False


def _sanitize_label(label: str) -> str:
    """Turn a service name into a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", label).strip("-")


def _write_log(spec_abs: Path | None, name: str, output: str, logger: logging.Logger) -> str:
    """Persist the red run's raw output; an unwritable log costs the path, not the run."""
    if spec_abs is None:
        return ""
    try:
        spec_abs.mkdir(parents=True, exist_ok=True)
        log_path = spec_abs / name
        log_path.write_text(output, encoding="utf-8")
        return str(log_path)
    except OSError as exc:
        logger.warning("could not write red-gate log %s: %s", name, exc)
        return ""


@blueprint.node
def arm_red_gate(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    spec_dir: str = "",
    plan_file: str = "",
    repo_dir: str = "",
) -> RedGateArm:
    """Record what the red gate will hold the tests turn to, before that turn runs.

    The baseline has to be taken *now*: whatever is already dirty in the worktree — a
    previous layer's diff, a fixture the harness planted — is not the tests turn's doing,
    and the gate must not charge it to that turn. The command and signatures are resolved
    once here so the tests prompt is told the exact command the gate will run.
    """
    spec_abs = _spec_abs(spec_dir, repo_dir)
    if _plans_declare_regression_only(spec_abs, plan_file):
        logger.info("plan declares '%s' — classic single-turn path", REGRESSION_ONLY_MARKER)
        return RedGateArm(mode="regression_only")

    if not cwd:
        return RedGateArm()
    service_dir = Path(cwd).expanduser()
    if not service_dir.is_dir():
        logger.warning("cwd does not exist: %s — gate will be skipped", service_dir)
        return RedGateArm()

    baseline = _worktree_changes(service_dir) or []
    command = _test_command(service, service_dir, repo_dir)
    if not command:
        logger.info(
            "no test override and no `make test` target in %s — red run will be skipped",
            service_dir,
        )
    return RedGateArm(
        baseline=baseline,
        test_command=command,
        signatures=_test_signatures(service, service_dir, repo_dir),
    )


@blueprint.node
def run_red_gate(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    spec_dir: str = "",
    baseline: list[str] | None = None,
    test_command: str = "",
    signatures: list[str] | None = None,
    repo_dir: str = "",
) -> RedGateOutcome:
    """Judge the tests turn: a pure, genuinely red diff proceeds; anything else loops back.

    Purity first, and unconditionally — it needs only git. Then the suite: a non-zero exit
    is the red observation the code turn is entitled to trust; exit 0 means the new tests
    exercise nothing that is missing, which is the exact failure mode the split exists to
    catch. No test command resolved, or a command that never returns, is `skipped` — the
    gate stands aside rather than falsely failing a service that has not adopted it, the
    same fail-open contract as the lint gate.
    """
    if not cwd:
        return RedGateOutcome(status="skipped", reason="no cwd given")
    service_dir = Path(cwd).expanduser()
    if not service_dir.is_dir():
        return RedGateOutcome(status="skipped", reason=f"cwd does not exist: {service_dir}")

    current = _worktree_changes(service_dir)
    if current is None:
        logger.warning("git could not report the worktree at %s", service_dir)
        return RedGateOutcome(
            status="skipped",
            command=test_command,
            reason=f"git could not report the worktree at {service_dir}",
        )

    known = set(baseline or [])
    changed = [path for path in current if path not in known]
    patterns = list(signatures or DEFAULT_TEST_SIGNATURES)
    non_test = [path for path in changed if not _is_test_path(path, patterns)]
    if non_test:
        logger.warning("tests turn touched non-test files: %s", ", ".join(non_test[:10]))
        return RedGateOutcome(
            status="impure",
            command=test_command,
            changed_files=changed,
            non_test_files=non_test,
            reason="the tests turn changed non-test files: " + ", ".join(non_test[:10]),
        )

    if not test_command:
        return RedGateOutcome(
            status="skipped",
            changed_files=changed,
            reason=f"no test command resolved for {service_dir} — red run skipped",
        )
    if not changed:
        return RedGateOutcome(
            status="no_tests",
            command=test_command,
            reason="the tests turn changed no files — there is nothing to observe red",
        )

    try:
        result = subprocess.run(
            test_command,
            cwd=service_dir,
            shell=True,
            capture_output=True,
            text=True,
            timeout=RED_GATE_TIMEOUT,
        )
        returncode, output = result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(
            "utf-8", "replace"
        )
        logger.warning("test command '%s' timed out after %ss", test_command, RED_GATE_TIMEOUT)
        return RedGateOutcome(
            status="skipped",
            command=test_command,
            changed_files=changed,
            reason=f"test command timed out after {RED_GATE_TIMEOUT}s",
            log_path=_write_log(
                _spec_abs(spec_dir, repo_dir),
                f"red-gate-{_sanitize_label(service or service_dir.name)}.log",
                stdout,
                logger,
            ),
        )
    except OSError as exc:
        logger.warning("test command '%s' could not be launched: %s", test_command, exc)
        return RedGateOutcome(
            status="skipped",
            command=test_command,
            changed_files=changed,
            reason=f"test command could not be launched: {exc}",
        )

    log_path = _write_log(
        _spec_abs(spec_dir, repo_dir),
        f"red-gate-{_sanitize_label(service or service_dir.name)}.log",
        output,
        logger,
    )
    if returncode == 0:
        logger.warning("suite green after the tests turn — the new tests exercise nothing missing")
        return RedGateOutcome(
            status="all_green",
            command=test_command,
            changed_files=changed,
            log_path=log_path,
            reason="the suite passed — the new tests fail on nothing",
        )

    logger.info("red observed for %s (exit %s)", service_dir, returncode)
    return RedGateOutcome(
        status="red",
        command=test_command,
        changed_files=changed,
        log_path=log_path,
        reason=f"suite exited {returncode} with the new tests in place",
    )


__all__ = ["arm_red_gate", "run_red_gate"]
