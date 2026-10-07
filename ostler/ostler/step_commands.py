"""`ostler doctor`'s checks on a flow step's `run:`, `health:` and `working-directory:` bullets."""

from __future__ import annotations

import re

from ostler import checks, refs as refs_mod, registry
from ostler.finding import Finding
from ostler.model import Graph, UINode
from ostler.qa import runbook as runbook_mod, stack as stack_mod

_STEP_COMMAND_KEYS: tuple[str, ...] = ("run", "health")

_BACKGROUNDED = re.compile(r"(?<![&|])&\s*$")


def check_step_command_bullets(step: UINode, rel: str, f: list[Finding]) -> None:
    """A `run:`/`health:` bullet is shelled, never parsed — a check expression there is wrong."""
    for key in _STEP_COMMAND_KEYS:
        value = runbook_mod.bullet_value(step.meta, key)
        if not value or not checks.is_check_expression(value):
            continue
        f.append(Finding(
            "error", "check-expression-as-command",
            f"{step.id}: `{key}:` ({value}) is a check expression, not a shell command — "
            f"`{key}:` is shelled at bring-up time, so this would fail with a bash syntax "
            f"error instead of running; write a shell command that exits non-zero on "
            f"failure (e.g. `curl -fsS <url>`), or move this check onto the `verify:` of "
            f"the claim it actually observes",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, key),
            suggestion=f"- {key}: curl -fsS <url>"))


def check_step_command_syntax(step: UINode, rel: str, f: list[Finding]) -> None:
    """A `run:`/`health:` bullet is handed to the shell verbatim, so it must parse as shell."""
    for key in _STEP_COMMAND_KEYS:
        value = runbook_mod.bullet_value(step.meta, key)
        if not value or checks.is_check_expression(value):
            continue
        refused = stack_mod.shell_syntax_error(value)
        if not refused:
            continue
        f.append(Finding(
            "error", "unparsable-command",
            f"{step.id}: `{key}:` ({value}) is not a shell command the shell can parse ({refused}). "
            f"`{key}:` is run with `bash -c` exactly as written, so it holds one command and no prose. "
            f"Describe what the command proves in the step's body, and write here a command "
            f"that exits non-zero on failure",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, key),
            suggestion=f"- {key}: curl -fsS <url>"))


def check_step_command_checkout_path(graph: Graph, step: UINode, rel: str, f: list[Finding]) -> None:
    """A `run:`/`health:` bullet names no path by this checkout's absolute location, which no other checkout shares."""
    root = str(graph.root.resolve())
    for key in _STEP_COMMAND_KEYS:
        value = runbook_mod.bullet_value(step.meta, key)
        if not value or root not in value:
            continue
        f.append(Finding(
            "error", "checkout-absolute-path",
            f"{step.id}: `{key}:` names {root}, where this checkout happens to sit, so the step runs on "
            f"no other machine. Write the path from the folder the step runs in, and name that folder "
            f"with `working-directory:`, read from the checkout root",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, key),
            suggestion="- working-directory: <folder from the checkout root>"))


def check_fixture_step_directory(graph: Graph, step: UINode, rel: str, f: list[Finding]) -> None:
    """A fixture step's `working-directory:` path names a directory the checkout holds."""
    value = runbook_mod.bullet_value(step.meta, "working-directory")
    if not value or runbook_mod.is_scenario_frame(value, graph.root) or (graph.root / value).is_dir():
        return
    f.append(Finding(
        "error", "fixture-step-directory",
        f"{step.id}: `working-directory: {value}` names no directory in the checkout, so the step "
        f"cannot run there. A path is read from the checkout root; for the scenario's own "
        f"directory, write the token `{registry.SCENARIO_FRAME_TOKEN}` with its colon",
        path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, "working-directory"),
        suggestion=f"- working-directory: {registry.SCENARIO_FRAME_TOKEN}"))


def check_step_not_scenario_frame(graph: Graph, step: UINode, rel: str, f: list[Finding]) -> None:
    """A runbook step's `working-directory: scenario:` names a frame that does not exist yet."""
    value = runbook_mod.bullet_value(step.meta, "working-directory")
    if not runbook_mod.is_scenario_frame(value, graph.root):
        return
    f.append(Finding(
        "error", "runbook-scenario-frame",
        f"{step.id}: `working-directory: {registry.SCENARIO_FRAME_TOKEN}` names a "
        f"scenario's own directory, but this step runs at bring-up, before any scenario "
        f"exists to name — state a path, or drop the bullet to run at the checkout root",
        path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, "working-directory"),
        suggestion="- working-directory: <path>"))


def check_fixture_step_serves(node: UINode, step: UINode, rel: str, f: list[Finding]) -> None:
    """A fixture step holds a process open only as a `serve` step of a `lifetime: scenario` fixture."""
    kind = runbook_mod.bullet_value(step.meta, "kind")
    run = runbook_mod.bullet_value(step.meta, "run")
    if kind != "serve" and _BACKGROUNDED.search(run):
        f.append(Finding(
            "error", "fixture-step-backgrounded",
            f"{step.id}: `run:` ends in `&`, so the harness waits on a process that never exits "
            f"and the scenario times out. A process the scenario talks to is a `kind: serve` "
            f"step, which the harness starts and stops when the scenario ends",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, "kind"),
            suggestion="- kind: serve"))
    if kind == "serve" and runbook_mod.bullet_value(node.meta, "lifetime") != "scenario":
        f.append(Finding(
            "error", "fixture-serve-lifetime",
            f"{step.id}: a `serve` step's process ends with the scenario that started it, so "
            f"another scenario reusing this fixture would find no server. Declare "
            f"`lifetime: scenario` so each scenario starts its own",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, "kind"),
            suggestion="- lifetime: scenario"))
