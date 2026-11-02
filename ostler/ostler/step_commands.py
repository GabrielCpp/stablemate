"""`ostler doctor`'s checks on a flow step's `run:`, `health:` and `working-directory:` bullets."""

from __future__ import annotations

import re

from ostler import checks, markdown, refs as refs_mod, registry
from ostler.finding import Finding
from ostler.model import Graph, UINode
from ostler.qa import fixture_browser, runbook as runbook_mod, stack as stack_mod

_STEP_COMMAND_KEYS: tuple[str, ...] = ("run", "health")

_BACKGROUNDED = re.compile(r"(?<![&|])&\s*$")

_THIS_MACHINE = re.compile(r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b|\[::1\]")

_ID_KEY = re.compile(r"(?:^|_)(?:id|uuid|guid)$|(?<=[a-z])(?:Id|Uuid|Guid)$", re.IGNORECASE)

_ID_LITERAL = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    r"|\b[0-9a-fA-F]{32}\b"
    r"|\bUNHEX\(\s*'[0-9a-fA-F]+'"
    r"|\bCAST\(\s*'[^']*'\s+AS\s+BINARY\b",
    re.IGNORECASE)

_INSERT = re.compile(r"\bINSERT\b[^()]*\(([^()]*)\)\s*VALUES\s*\(", re.IGNORECASE)

_FIXED_VALUE = re.compile(r"^(?:-?\d+|'[^'$@]*'|\"[^\"$@]*\")$")


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


def _directory_held(graph: Graph, value: str) -> bool:
    try:
        return runbook_mod.resolve_directory(graph.root, value).is_dir()
    except runbook_mod.WorkingDirectoryError:
        return True


def check_fixture_step_directory(graph: Graph, step: UINode, rel: str, f: list[Finding]) -> None:
    """A fixture step's `working-directory:` path names a directory the checkout holds."""
    value = runbook_mod.bullet_value(step.meta, "working-directory")
    if not value or runbook_mod.is_scenario_frame(value, graph.root) or _directory_held(graph, value):
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


def check_fixture_launch_screen(graph: Graph, node: UINode, steps: list[UINode], rel: str, f: list[Finding]) -> None:
    """A fixture's `launch-screen:` names a screen, and only a `lifetime: scenario` fixture with no browser step may state one."""
    value = runbook_mod.bullet_value(node.meta, "launch-screen")
    if not value:
        return
    ref = refs_mod.bullet_ref(node.id, "launch-screen")
    links = markdown.extract_refs(value).links
    target = graph.find_ui_node(graph.resolve_doc_ref(links[0][1], origin=node.path)) if links else None
    if target is not None and target.type != "screen":
        f.append(Finding(
            "error", "unresolved-relation",
            f"{node.id}: `launch-screen: {value}` resolves to a {target.type or 'untyped'} node, not a "
            f"screen, so no claim can start from the screen this fixture leaves the app on",
            path=rel, line=node.line, ref=ref,
            suggestion="- launch-screen: [<screen>](<screen>.md)"))
    if runbook_mod.bullet_value(node.meta, "lifetime") != "scenario":
        f.append(Finding(
            "error", "fixture-launch-screen-lifetime",
            f"{node.id}: `launch-screen:` states the screen a cold launch opens on after this fixture "
            f"ran, and the next scenario clears the device, so a session a lap built would be gone "
            f"by then. Declare `lifetime: scenario` so each scenario signs the device in again",
            path=rel, line=node.line, ref=ref,
            suggestion="- lifetime: scenario"))
    if any(fixture_browser.is_browser_step(step) for step in steps):
        f.append(Finding(
            "error", "fixture-launch-screen-browser",
            f"{node.id}: `launch-screen:` names a screen of an app on a device, and this fixture has a "
            f"browser step (`open:` or `arrange:`), which signs a browser in and leaves the device "
            f"untouched. Sign the device in with `run:` steps, as the fixture reference shows",
            path=rel, line=node.line, ref=ref))


def check_fixture_probe_remote(step: UINode, rel: str, f: list[Finding]) -> None:
    """A `probe` step asks about a service outside the machine, because a service on the machine is the runbook's to start."""
    run = runbook_mod.bullet_value(step.meta, "run")
    if runbook_mod.bullet_value(step.meta, "kind") != "probe" or not _THIS_MACHINE.search(run):
        return
    f.append(Finding(
        "error", "fixture-probe-local",
        f"{step.id}: `run:` probes a service on this machine. A probe gaps its claims when an outside "
        f"service only a person can supply is absent, such as a payment provider with no key. A "
        f"service on this machine is one the runbook starts, and whatever answers there now may be "
        f"someone else's. Start it in the runbook on a free port, as another book's runbook may "
        f"already do, point the app at it, and drop this probe",
        path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, "kind")))


def _split_values(text: str, start: int) -> list[str]:
    """The comma-separated values of the parenthesis opening at `start`, nested calls kept whole."""
    depth, item, out = 0, "", []
    for ch in text[start:]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        if ch == "," and depth == 0:
            out.append(item.strip())
            item = ""
            continue
        item += ch
    out.append(item.strip())
    return out


def fixed_ids(text: str) -> list[str]:
    """Every literal an arrangement writes where a product-assigned or generated id belongs."""
    found = [m.group(0) for m in _ID_LITERAL.finditer(text)]
    for insert in _INSERT.finditer(text):
        columns = [c.strip().strip("`\"'") for c in insert.group(1).split(",")]
        values = _split_values(text, insert.end())
        for column, value in zip(columns, values, strict=False):
            if _ID_KEY.search(column) and _FIXED_VALUE.match(value) and value not in found:
                found.append(value)
    return found


def check_fixture_fixed_id(step: UINode, rel: str, f: list[Finding]) -> None:
    """A fixture step lets the product assign every id or generates one as it runs, never fixes one."""
    for key in ("run", "body"):
        value = runbook_mod.bullet_value(step.meta, key)
        literals = fixed_ids(value) if value else []
        if not literals:
            continue
        f.append(Finding(
            "error", "fixture-fixed-id",
            f"{step.id}: `{key}:` writes the fixed id {', '.join(f'`{v}`' for v in literals)}. "
            f"Fixtures compose on one copy of the stack, and two that fix the same id rewrite "
            f"each other's rows, so a scenario passes or fails by build order. Let the product "
            f"assign the id, or generate one in the step as it runs (`uuidgen`, "
            f"`$(date +%s%N)`), and provide it with `from:`/`read:`",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, key),
            suggestion="- run: id=$(uuidgen) && <create the record with $id> && printf '{\"id\":\"%s\"}' \"$id\""))


def check_fixture_asserted_id(node: UINode, rel: str, f: list[Finding]) -> None:
    """An id a fixture provides is generated as it builds or read back from the step that created the record, never a literal."""
    for entry in node.entries.get("provides", []):
        head = entry.headline.partition("—")[0].split()
        asserted = entry.property_text("is")
        if not head or not _ID_KEY.search(head[0]) or not asserted or "$" in asserted:
            continue
        f.append(Finding(
            "error", "fixture-fixed-id",
            f"{node.id}: `provides: {head[0]}` is asserted with the literal `is: {asserted.strip()}`, "
            f"so every build of the fixture fixes the same id. Fixtures compose on one copy of "
            f"the stack, and two that fix the same id rewrite each other's rows. Generate the id "
            f"as the fixture builds (`is: $(uuidgen)`), or point the fact at the step that created "
            f"the record with `from:`/`read:`",
            path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "provides"),
            suggestion=f"  - {head[0]} — <what it is>\n    - is: $(uuidgen)"))
