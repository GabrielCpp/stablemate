"""Read the durable QA stack out of the book's ops nodes.

The stack used to be declared in a `qa-stack.yml` at the repo root: a file with no schema,
no validator, no scaffold, and two authors — one prompt line gated behind a plan field a
greenfield story never carries, and a repair prompt reached only *after* QA had already
failed against nothing. A repo that had never authored one ran QA with no stack at all and
said so nowhere.

The declaration belongs where every other executable fact about this system already lives.
`ostler.registry` has carried an operational profile since the UI profile was written —
`runbook` (context `ops`, a required `## Steps` section, `driver`/`environment`/`surfaces`)
and `environment` (`services`, `backing`, `local-only`) — and the `step` section type's
`kind:` vocabulary (`prepare|service|seed|run|health|verify|drive`) is a superset of the
phases `stack.ensure_stack` runs, down to `run:` and `working-directory:` being the same
two key names `stack._run_step` reads. It had no reader. This is that reader.

It is deliberately *only* a reader: it returns the manifest mapping
:func:`ostler.qa.stack.ensure_stack` already takes, so the lifecycle — adoption, staleness,
boot windows, teardown policy — stays in one place and this module owns none of it.

**Why a runbook may own this and a feature Concept may not.** `ostler.qa.context` excludes
the old manifest from the ownership gate because "a stack manifest is not a product
surface", and a greenfield run that tried to make one a feature Concept bought a permanent
`missing-declared-check` warning for its trouble. An `ops`-context runbook is not a product
surface either — that is what the context is for — so it can own a bring-up recipe without
ever having to declare an observation.

**The fallback.** okf-builder's walkthrough has read a launch contract off an OKF `server`
node since it was written (`launch:`/`entry-url:`/`health-path:`/`working-directory:`/
`identity:`/`stop:`/`boot-timeout:`, on the one server marked `walkthrough: true`). That is
the same contract in a thinner shape, so a book with no runbook still yields a stack from
it, and the walk and the coder QA lane share one derivation instead of two.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ostler import model
from ostler.model import Graph, UINode
from ostler.qa import stack as stack_mod
from ostler.qa.outcome import QaOutcome

#: `step.kind` values that are a phase of the durable stack, mapped to their manifest key.
#: `run`/`verify`/`drive` are runbook steps that are *not* stack phases — they exercise the
#: system once it is up, which is the QA plan's job, not the bring-up's — and are skipped.
STEP_PHASES: dict[str, str] = {
    "prepare": "prepare",
    "service": "launch",
    "seed": "seed",
    "health": "health",
}
#: Every `kind:` the profile recognizes; the doctor rejects anything else.
STEP_KINDS: frozenset[str] = frozenset(STEP_PHASES) | {"run", "verify", "drive"}
#: The adoption policies `stack.ensure_stack` understands.
REUSE_POLICIES: frozenset[str] = frozenset({"if-fresh", "always", "never"})

#: Runbook bullet → manifest key, for the scalars that are only a spelling change.
_SCALARS: dict[str, str] = {
    "entry-url": "entry_url",
    "health-path": "health_path",
    "identity": "identity",
    "reuse": "reuse",
    "fresh": "fresh",
    "boot-timeout": "boot_timeout",
    "health-timeout": "health_timeout",
    "stop": "stop",
}


def bullet_value(meta: dict, key: str) -> str:
    """One bullet's value as a string — a repeated bullet keeps its first value.

    A backticked value is the value, and the rest of the line is commentary: these bullets
    are prose documentation as much as they are interface, and `` - identity: `"ok"` — the
    health body `` is how one is actually written. Unbackticked there is no boundary, so the
    first line is all of it. This is the same reading okf-builder's walkthrough already
    applies to the `server` contract — one book must not mean two things to two readers.
    """
    value = meta.get(key, "")
    if isinstance(value, list):
        value = value[0] if value else ""
    text = str(value).strip()
    backticked = re.match(r"`([^`]+)`", text)
    return backticked.group(1).strip() if backticked else text.partition("\n")[0].strip()


def _children(meta: dict, key: str) -> list[str]:
    """A nested bullet's children as a flat list of strings."""
    value = meta.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def steps_of(graph: Graph, runbook: UINode) -> list[UINode]:
    """The runbook's `### id` steps, in document order.

    Containment is what selects them, not the heading: a `step` node is only ever minted
    under a `## Steps` heading, and `parent` chains it to the file node that owns it. Two
    runbooks in one book therefore never borrow each other's steps.
    """
    by_id = {n.id: n for n in graph.ui_nodes}

    def owned(node: UINode) -> bool:
        seen: set[str] = set()
        cur = node.parent
        while cur and cur not in seen:
            seen.add(cur)
            if cur == runbook.id:
                return True
            parent = by_id.get(cur)
            cur = parent.parent if parent else ""
        return False

    return [n for n in graph.ui_nodes if n.type == "step" and owned(n)]


def _step_command(node: UINode, root: Path, default_cwd: str) -> dict[str, str] | None:
    """One `step` node as the mapping `stack._run_step` reads, or None when it has no command.

    Always the mapping form, never a bare string: `_run_step` gives a bare string the
    *boot* timeout (30s by default) and a mapping without one `STEP_TIMEOUT_S` (600s), so
    `- make build` and `- run: make build` mean different things. Emitting one shape means
    an author never meets that asymmetry.
    """
    command = bullet_value(node.meta, "run")
    if not command:
        return None
    if bullet_value(node.meta, "optional").lower() in ("true", "yes"):
        # Best-effort, per the profile. `ensure_stack` has no soft mode, so the intent is
        # carried in the recipe itself rather than dropped along with the step.
        command = f"{command} || true"
    exports = _env_exports(node)
    if exports:
        command = f"{exports} {command}"
    cwd = bullet_value(node.meta, "working-directory")
    step: dict[str, str] = {
        "run": command,
        "working-directory": str((root / (cwd or default_cwd or ".")).resolve()),
    }
    timeout = bullet_value(node.meta, "timeout")
    if timeout:
        step["timeout"] = timeout
    return step


def _env_exports(node: UINode) -> str:
    """A step's `env:` children as a shell prefix.

    Each child is an ordinary shell assignment — `PORT=8080`, or
    `TOKEN=$(scripts/mint.sh)` — because the step already runs through `bash -c` and
    inventing a second syntax for the same thing buys nothing. Wiring that must be fresh
    per *plan run* rather than per bring-up is `secrets:` on the runbook instead.
    """
    assignments = [item for item in _children(node.meta, "env") if "=" in item]
    return "".join(f"export {item}; " for item in assignments).strip()


def _secrets_of(meta: dict) -> dict[str, str]:
    """The runbook's `secrets:` children as ``{ENV_NAME: mint recipe}``.

    A short-lived credential goes stale between QA-plan authoring and the run that spends
    it, and the bring-up phases run once per stack rather than once per plan, so they
    cannot be the freshening point. These are minted immediately before the run instead.
    The recipe is repo-owned shell, never interpreted here; it prints the secret and
    nothing else.
    """
    secrets: dict[str, str] = {}
    for item in _children(meta, "secrets"):
        name, sep, recipe = item.partition(":")
        if not sep or not name.strip() or not recipe.strip():
            continue
        secrets[name.strip()] = recipe.strip()
    return secrets


def _from_runbook(graph: Graph, runbook: UINode) -> dict[str, Any]:
    root = graph.root
    meta = runbook.meta
    manifest: dict[str, Any] = {}
    for bullet, key in _SCALARS.items():
        value = bullet_value(meta, bullet)
        if value:
            manifest[key] = value
    app_cwd = bullet_value(meta, "working-directory") or "."
    manifest["app_cwd"] = str((root / app_cwd).resolve())
    manifest["repo_root"] = str(root.resolve())

    phases: dict[str, list[dict[str, str]]] = {"prepare": [], "seed": [], "health": []}
    for node in steps_of(graph, runbook):
        kind = bullet_value(node.meta, "kind").lower()
        phase = STEP_PHASES.get(kind)
        if phase is None:
            continue
        step = _step_command(node, root, app_cwd)
        if phase == "launch":
            # The first `service` step is the launch; a second is a `runbook-multi-service`
            # error the doctor reports, and taking the first keeps the reader deterministic
            # while the book is being repaired.
            if step and "launch" not in manifest:
                manifest["launch"] = step["run"]
            gate = bullet_value(node.meta, "health")
            if gate:
                phases["health"].append({"run": gate, "working-directory": step["working-directory"]
                                         if step else manifest["app_cwd"]})
            continue
        if step:
            phases[phase].append(step)
    for phase, steps in phases.items():
        if steps:
            manifest[phase] = steps

    secrets = _secrets_of(meta)
    if secrets:
        manifest["secrets"] = secrets
    manifest["source"] = runbook.id
    return manifest


def _from_server(graph: Graph, server: UINode) -> dict[str, Any]:
    """The thinner walkthrough contract, as the same manifest."""
    root = graph.root
    meta = server.meta
    working = bullet_value(meta, "working-directory") or "."
    manifest: dict[str, Any] = {
        "launch": bullet_value(meta, "launch"),
        "entry_url": bullet_value(meta, "entry-url").rstrip("/"),
        "health_path": bullet_value(meta, "health-path") or "/",
        "app_cwd": str((root / working).resolve()),
        "repo_root": str(root.resolve()),
        "source": server.id,
    }
    for bullet, key in (("identity", "identity"), ("stop", "stop"),
                        ("boot-timeout", "boot_timeout")):
        value = bullet_value(meta, bullet)
        if value:
            manifest[key] = value
    return manifest


def is_stack_runbook(graph: Graph, node: UINode) -> bool:
    """Whether this runbook brings a system up, as opposed to merely running a procedure.

    `runbook` is the ops vocabulary's general shape: "preview the plan", "rotate the keys"
    and "restore last night's dump" are runbooks too, and none of them has a stack to bring
    up. A runbook is *this repo's stack* only when it says so — a `kind: service` step, or
    the launch scalars that imply one. Anything else is a procedure, which QA never boots
    and the doctor never asks to be bootable.
    """
    if bullet_value(node.meta, "entry-url") or bullet_value(node.meta, "launch"):
        return True
    return any(bullet_value(step.meta, "kind") == "service" for step in steps_of(graph, node))


def stack_runbooks(graph: Graph) -> list[UINode]:
    """Every runbook that claims to bring a system up, in document order."""
    return [n for n in graph.ui_nodes_of_type("runbook") if is_stack_runbook(graph, n)]


def select_runbook(graph: Graph, name: str = "") -> UINode | None:
    """The runbook this repo's QA stack comes from, or None.

    With `name`, the runbook whose slug/id matches it — named explicitly, so a procedure
    runbook is the caller's business. Without, the sole *stack* runbook: a book carrying
    several and naming none is ambiguous, and guessing would silently bring the wrong
    stack up.
    """
    runbooks = graph.ui_nodes_of_type("runbook")
    if not runbooks:
        return None
    if name:
        for node in runbooks:
            if name in (node.id, node.path.stem, node.title):
                return node
        return None
    stacks = stack_runbooks(graph)
    return stacks[0] if len(stacks) == 1 else None


def select_server(graph: Graph) -> UINode | None:
    """The one `server` node marked `walkthrough: true`, or None.

    Marking more than one is an authoring error the doctor reports; here it resolves to
    "no contract" rather than an arbitrary pick, because a walk against the wrong service
    is worse than a walk that says it has nowhere to go.
    """
    marked = [n for n in graph.ui_nodes_of_type("server")
              if bullet_value(n.meta, "walkthrough").lower() in ("true", "yes")]
    return marked[0] if len(marked) == 1 else None


def has_served_surface(graph: Graph) -> bool:
    """Whether anything in this book has to be *running* before QA can reach it.

    A missing stack is only a defect against a book that describes something served. A
    CLI's book (`cli` nodes), a library's, or an infrastructure program's describes
    behaviour a lane invokes directly, and telling those repos to declare a stack would
    be telling them to declare a stack for nothing. A `screen` or a `server` is the
    tell: neither can be driven without a process answering first. The doctor's
    `runbook-missing` gates on this, and so does anything downstream deciding whether an
    empty manifest is a topology or a gap.
    """
    return bool(graph.ui_nodes_of_type("screen") or graph.ui_nodes_of_type("server"))


def load_stack(root: Path | None = None, *, name: str = "",
               graph: Graph | None = None,
               logger: logging.Logger | None = None) -> dict[str, Any]:
    """The manifest `ensure_stack` takes, read from the book's ops nodes.

    Returns ``{}`` when the book declares neither a runbook nor a walkthrough server —
    the only honest "nothing to bring up" left, and one the doctor reports as
    `runbook-missing` rather than leaving it to be discovered by a QA run that passes
    against nothing.

    Every `working-directory` comes back absolute. The manifest is authored repo-relative
    because that is what an author means; nothing downstream resolves it, so an unresolved
    `.` would launch the stack from whatever cwd the engine happens to hold.
    """
    log = logger or logging.getLogger(__name__)
    graph = graph if graph is not None else model.load(root or Path.cwd())
    runbook = select_runbook(graph, name)
    if runbook is not None:
        log.info("stack declared by runbook %s", runbook.id)
        return _from_runbook(graph, runbook)
    if name:
        log.warning("no runbook named %r in the book", name)
        return {}
    server = select_server(graph)
    if server is not None and bullet_value(server.meta, "launch"):
        log.info("no runbook; falling back to the walkthrough contract on %s", server.id)
        return _from_server(graph, server)
    log.info("the book declares no runbook and no walkthrough server — nothing to bring up")
    return {}


def cmd_stack_up(root: Path, *, name: str = "",
                 logger: logging.Logger | None = None) -> QaOutcome:
    """`ostler qa stack up` — bring the book's declared stack to ready, or say why not.

    The manifest it derived travels out in `data` beside the verdict: a repairer told only
    that `prepare[1]` failed re-derives from the book what the reader already knew, and a
    book whose recipe is subtly not the one the author meant is otherwise invisible.
    """
    log = logger or logging.getLogger(__name__)
    manifest = load_stack(root, name=name, logger=log)
    if not manifest:
        return QaOutcome(
            ok=True, status="none",
            message=("the book declares no runbook and no walkthrough server — nothing to "
                     "bring up"),
            data={"manifest": {}},
        )
    result = stack_mod.ensure_stack(manifest, repo_root=str(root), logger=log)
    ready = result.get("ready") == "yes"
    how = "adopted" if result.get("adopted") == "yes" else "brought up"
    where = result.get("entry_url") or "(no entry url)"
    message = (f"stack {how} and healthy at {where}" if ready else
               "stack bring-up failed at step '{}'{}".format(
                   result.get("failed_step", "unknown"),
                   f": {result['error'].strip()}" if result.get("error") else ""))
    return QaOutcome(ok=ready, message=message,
                     data={**result, "manifest": manifest, "source": manifest.get("source", "")})


def cmd_stack_down(root: Path, *, name: str = "",
                   logger: logging.Logger | None = None) -> QaOutcome:
    """`ostler qa stack down` — run the declared teardown, or leave an expensive stack up.

    `down`, not `stop`: `ostler qa stop` already means "kill this session's daemons", and a
    verb that means two lifecycles in one namespace is a verb somebody eventually spends on
    the wrong one.

    No process handles cross a process boundary, so this command passes none — but
    :func:`ostler.qa.stack.teardown_stack` still reaps a foreground server a prior
    bring-up *recorded* in the stablemate cache for this app directory, and falls back
    to the book's `stop:` recipe only after that. A runbook that declares no `stop:`
    and left no record reports `skipped` — which is the policy, not a failure: a shared
    emulator is cheaper left serving than rebuilt.
    """
    log = logger or logging.getLogger(__name__)
    manifest = load_stack(root, name=name, logger=log)
    if not manifest:
        return QaOutcome(ok=True, status="none",
                         message="the book declares no runbook — nothing to tear down")
    result = stack_mod.teardown_stack({}, manifest, logger=log)
    torn = result.get("torn_down", "no")
    return QaOutcome(
        ok=torn != "no",
        message={"yes": "stack torn down",
                 "skipped": "no `stop:` recipe — leaving the stack serving"}.get(
                     torn, "teardown failed"),
        data=result,
    )


__all__ = [
    "REUSE_POLICIES",
    "STEP_KINDS",
    "STEP_PHASES",
    "bullet_value",
    "cmd_stack_down",
    "cmd_stack_up",
    "is_stack_runbook",
    "load_stack",
    "select_runbook",
    "select_server",
    "stack_runbooks",
    "steps_of",
]
