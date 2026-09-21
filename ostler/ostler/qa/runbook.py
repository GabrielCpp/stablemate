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
`kind:` vocabulary (`prepare|service|seed|run|health|verify|drive|teardown`) is a superset of the
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

**The fallback.** okf-builder's walk has read a launch contract off an OKF `server`
node since it was written (`launch:`/`entry-url:`/`health-path:`/`working-directory:`/
`identity:`/`stop:`/`boot-timeout:`, on the book's `server` node). That is
the same contract in a thinner shape, so a book with no runbook still yields a stack from
it, and the walk and the coder QA lane share one derivation instead of two.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler import checks
from ostler import graph as graph_mod
from ostler import links as links_mod
from ostler import markdown
from ostler import model
from ostler import path as path_mod
from ostler.model import Graph, UINode
from ostler.qa import stack as stack_mod
from ostler.qa.outcome import QaOutcome

#: `step.kind` values that are a phase of the durable stack, mapped to their manifest key.
#: `run`/`verify`/`drive`/`teardown` are runbook steps that are *not* stack phases — they act
#: on the system once it is up, which is the QA plan's job or an operator's, not the
#: bring-up's — and are skipped.
STEP_PHASES: dict[str, str] = {
    "prepare": "prepare",
    "service": "launch",
    "seed": "seed",
    "health": "health",
}
#: Every `kind:` the profile recognizes; the doctor rejects anything else.
#:
#: `teardown` is here because a book that documents a whole lifecycle has to file its
#: shutdown and volume-removal targets somewhere, and every other word was worse. `kind:` is
#: required on a step, so leaving it off is not available; `run` is what the QA plan drives,
#: which a command that deletes a database is not; and `prepare` is the one an author
#: actually reaches for, which puts `docker down -v` in the phase that runs *before* the
#: launch. A runbook whose `prepare` list ended in a teardown target tore down what its own
#: earlier steps had built, and the bring-up then failed against nothing.
STEP_KINDS: frozenset[str] = frozenset(STEP_PHASES) | {"run", "verify", "drive", "teardown"}
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


def bullet_text(text: str) -> str:
    """A raw bullet string, extracted the way this book's values are actually read.

    A backticked value is the value, and the rest of the line is commentary: these bullets
    are prose documentation as much as they are interface, and `` - identity: `"ok"` — the
    health body `` is how one is actually written. Unbackticked there is no boundary, so the
    first line is all of it. This is the same reading okf-builder's walk already
    applies to the `server` contract — one book must not mean two things to two readers.

    The string-level half of :func:`bullet_value`, split out so a caller holding a raw value
    rather than a bullet dict (:mod:`ostler.values`) reads it the same way instead of copying
    the extraction.
    """
    text = text.strip()
    backticked = re.match(r"`([^`]+)`", text)
    return backticked.group(1).strip() if backticked else text.partition("\n")[0].strip()


def bullet_value(meta: dict, key: str) -> str:
    """One bullet's value as a string — a repeated bullet keeps its first value.

    See :func:`bullet_text` for the extraction itself.
    """
    value = meta.get(key, "")
    if isinstance(value, list):
        value = value[0] if value else ""
    return bullet_text(str(value))


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


#: `working-directory:` value that names a fixture step's own scenario directory rather than
#: a checkout-relative path — the same directory `Tool._cwd(qa.scenario_id)` resolves and
#: creates in the harness. Meaningful only on a fixture step, which runs inside a scenario;
#: a runbook step carrying it trips the doctor's `runbook-scenario-frame` instead, because a
#: runbook step runs at bring-up, before any scenario exists to name.
SCENARIO_FRAME_TOKEN = "scenario:"


def is_scenario_frame(value: str) -> bool:
    """Whether a `working-directory:` bullet states the scenario-frame token."""
    return value.strip() == SCENARIO_FRAME_TOKEN


def _step_command(node: UINode, root: Path, default_cwd: str) -> dict[str, str] | None:
    """One `step` node as the mapping `stack._run_step`/`book_fixtures` reads, or None when it
    has no command.

    Always the mapping form, never a bare string: `_run_step` gives a bare string the
    *boot* timeout (30s by default) and a mapping without one `STEP_TIMEOUT_S` (600s), so
    `- make build` and `- run: make build` mean different things. Emitting one shape means
    an author never meets that asymmetry.

    A `working-directory: scenario:` bullet is carried as the `"cwd-frame": "scenario"` marker
    instead of a resolved path — the scenario directory does not exist at manifest-build time,
    so there is nothing here to resolve it against; the harness (`Qa._run_book_step`) resolves
    the marker at run time. Every other value, stated or absent, keeps exactly today's
    checkout-relative meaning under the `"working-directory"` key.
    """
    command = bullet_value(node.meta, "run")
    if not command or checks.is_check_expression(command):
        # A check expression (`http_status(200, path="/healthz")`) is not a command —
        # `ensure_stack`/`book_fixtures` shell this verbatim, and handing it a check call
        # buys nothing but a bash syntax error two stages later. Treated the same as an
        # absent `run:`: the doctor's `check-expression-as-command` is the loud finding an
        # author sees before bring-up ever runs; this is only the backstop that keeps a
        # book that skipped the doctor from reaching bash with the wrong grammar.
        return None
    if bullet_value(node.meta, "optional").lower() in ("true", "yes"):
        # Best-effort, per the profile. `ensure_stack` has no soft mode, so the intent is
        # carried in the recipe itself rather than dropped along with the step.
        command = f"{command} || true"
    exports = _env_exports(node)
    if exports:
        command = f"{exports} {command}"
    cwd = bullet_value(node.meta, "working-directory")
    step: dict[str, str] = {"run": command}
    if is_scenario_frame(cwd):
        step["cwd-frame"] = "scenario"
    else:
        step["working-directory"] = str((root / (cwd or default_cwd or ".")).resolve())
    timeout = bullet_value(node.meta, "timeout")
    if timeout:
        step["timeout"] = timeout
    return step


def step_command(node: UINode, root: Path, default_cwd: str) -> dict[str, str] | None:
    """Public alias of `_step_command`, for a caller outside this module (`book_fixtures`).

    A fixture's own `## Steps` are the same section type a runbook's are, so building the
    manifest form of one is the same walk — this is the seam that lets `book_fixtures`
    reuse it without reaching past the leading underscore.
    """
    return _step_command(node, root, default_cwd)


#: A shell assignment: a name, `=`, then whatever the shell will take.
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _env_exports(node: UINode) -> str:
    """A step's `env:` children as a shell prefix.

    Each child is an ordinary shell assignment — `PORT=8080`, or
    `TOKEN=$(scripts/mint.sh)` — because the step already runs through `bash -c` and
    inventing a second syntax for the same thing buys nothing. Wiring that must be fresh
    per *plan run* rather than per bring-up is `secrets:` on the runbook instead.

    The child is read through `bullet_text` like every other value, so the assignment may
    be written bare or backticked. A child that is not an assignment is prose — a note
    saying where the wiring already comes from, which is a thing the book is meant to be
    able to say — and it is not exported. Merely containing an `=` is not enough: a
    sentence that *mentions* `HOST=db` would otherwise become the command, and the step
    runs it through a shell.
    """
    assignments = [
        value
        for value in (bullet_text(item) for item in _children(node.meta, "env"))
        if _ASSIGNMENT.match(value)
    ]
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
        idx = markdown.label_colon_index(item)
        if idx == -1:
            continue
        name, recipe = item[:idx], item[idx + 1:]
        if not name.strip() or not recipe.strip():
            continue
        secrets[name.strip()] = recipe.strip()
    return secrets


def system_root(graph: Graph) -> Path:
    """The root of the system this book describes, which is not always where it was read.

    Every path in a runbook — `working-directory: .`, a step's own `working-directory:`,
    a `code:` citation — is written relative to the root of the *subject*, so that one book
    joins to its code whether it sits at a repo's top level or nested inside a host tree.
    `graph.root` is where the book was loaded from. For a book at its own `docs/features`
    those are the same directory and always have been; for a book read from elsewhere they
    are not, and resolving against the checkout launches the stack from a directory that
    has none of the subject's files in it. `path.book_prefix_in` carries the derivation.
    """
    features = path_mod.features_root(graph)
    try:
        relative = features.relative_to(graph.root).as_posix()
    except ValueError:  # a features root outside the checkout names its own system
        return features.parent.parent
    prefix = path_mod.book_prefix_in(graph.root, relative)
    return graph.root / prefix if prefix else graph.root


def _from_runbook(graph: Graph, runbook: UINode) -> dict[str, Any]:
    root = system_root(graph)
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
                manifest["launch_cwd"] = step.get(
                    "working-directory", manifest["app_cwd"])
            gate = bullet_value(node.meta, "health")
            if gate and not checks.is_check_expression(gate):
                # Same backstop as `_step_command`'s: a check expression here is a book
                # defect the doctor already reports (`check-expression-as-command`), not a
                # gate this reader should hand to bash.
                phases["health"].append({
                    "run": gate,
                    "working-directory": step.get("working-directory", manifest["app_cwd"])
                    if step else manifest["app_cwd"],
                })
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
    """The thinner `server` contract, as the same manifest."""
    root = system_root(graph)
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


@dataclass(frozen=True)
class StackSelection:
    """Which runbooks a bring-up covers — or, when none was chosen, *why* none was.

    The reason is the point. `load_stack` answers this question with `{}`, which reads as
    "the book declares no stack" no matter which of three things happened: the book really
    declares none, the caller named a runbook that is not there, or the book declares
    several bound to different environments and the caller named none. The last is a
    **refusal** — the right answer, since guessing would bring the wrong stack up — and
    reporting a refusal as an absence sends the reader to write a runbook that already
    exists. Opposite findings want opposite fixes, so they get different values.
    """

    #: Every runbook this bring-up covers, in document order. Empty iff `reason` is set.
    runbooks: tuple[UINode, ...] = ()
    #: `""` when runbooks were chosen; otherwise one of `no-runbook`, `no-such-name`,
    #: `ambiguous`.
    reason: str = ""
    #: The environment node id the chosen runbooks share, when more than one was chosen.
    environment: str = ""
    #: The stack runbooks that were on the table, for a reason the caller must report.
    candidates: tuple[str, ...] = field(default=())


def environment_of(node: UINode, resolver: links_mod.LinkResolver) -> str:
    """The node id *node*'s `environment:` link resolves to, or `""`.

    Resolved rather than compared as text: globex's two runbooks both bind to `local.md`
    and spell it `local.md` and `../../api-service/ops/local.md`, because they sit in
    different service directories. Those are the same environment, and a string compare
    says they are two.
    """
    value = node.meta.get("environment", "")
    if isinstance(value, list):
        value = value[0] if value else ""
    for _text, href in markdown.extract_refs(str(value)).links:
        target = resolver.resolve(node.path, href)
        if target is not None and target.resolved:
            return target.node_id
    return ""


def _environment_is_local_only(graph: Graph, environment_id: str) -> bool:
    """Whether the `environment` node *environment_id* declares itself `local-only: true`.

    Same truthy spelling `doctor.py`'s `runbook-local-only` check already reads this bullet
    with, so the two readers of one declaration agree on what it means.
    """
    node = graph.find_ui_node(environment_id)
    if node is None:
        return False
    return bullet_value(node.meta, "local-only") in ("true", "yes")


def _selection_for(stacks: list[UINode], resolver: links_mod.LinkResolver,
                   environment: str) -> StackSelection:
    """Every stack runbook bound to *environment*, as a resolved selection.

    The environment is the unit, so a selection names all of its runbooks, never the one
    that happened to decide it.
    """
    selected = tuple(node for node in stacks if environment_of(node, resolver) == environment)
    return StackSelection(runbooks=selected, environment=environment)


def select_stack(graph: Graph, name: str = "", *, near: Path | None = None) -> StackSelection:
    """Which runbooks bring this book's system up, or why the question has no answer.

    With `name`, the runbook whose slug/id matches it — named explicitly, so a procedure
    runbook is the caller's business. `near` is ignored whenever `name` is given: an
    explicit name is the caller saying which system, and asking it to also infer one from
    a path would just be a second, contradictory way of answering the same question.

    Without, **the environment is the unit, not the runbook.** A book describing one
    service has one stack runbook and the two units coincide; a book describing a web
    surface and the API it calls has two, and a journey through the web surface needs both
    serving. What makes them one system is that they bind to the same `environment:` node —
    which is a thing the author wrote down, not an inference — so every stack runbook
    sharing one environment comes up together. Stack runbooks bound to *different*
    environments are genuinely several systems, and picking one of those is the caller's
    to do by name — or, when `near` names the spec under audit, by *derivation*: the
    surface `near` sits in says which of that book's environments is the one to bring up,
    and every stack runbook anywhere in the book bound to that environment comes up with
    it, including ones in other surfaces. That is the point — a web surface and the API it
    calls are one system — so the narrowing only picks the environment; the selection
    itself stays book-wide.

    Whatever candidates survive that narrowing are filtered once more by `local-only`,
    and only then does the refusal fire: a QA bring-up must never boot a non-local system
    by accident, so when exactly one candidate is declared `local-only: true`, that
    declaration is the book's own answer to which one QA is for. Two or zero declaring it
    settle nothing, so the refusal stands. It runs right after `near` because it is a
    safety filter over whatever ambiguity remains, not a selector — `near` knows which
    surface is under audit and this does not, so a book-wide `local-only` environment must
    never outrank it.

    When more than one candidate survives the `local-only` filter — two honestly local
    environments, say two docker-compose profiles — the engine takes the first by node id,
    which is the environment page's repo-relative path. The book is not asked to break that
    tie: every survivor is a local environment this book says QA may boot, so the choice
    between them is about which one the tooling happens to start, not about the system being
    described, and a marker bullet asking the author to answer it was a question about the
    tooling wearing a book page's clothes. Ordering by a path the repo already fixes is what
    makes the same book resolve to the same environment on every machine.
    """
    runbooks = graph.ui_nodes_of_type("runbook")
    if name:
        for node in runbooks:
            if name in (node.id, node.path.stem, node.title):
                return StackSelection(runbooks=(node,))
        return StackSelection(reason="no-such-name")
    stacks = stack_runbooks(graph)
    if not stacks:
        return StackSelection(reason="no-runbook")
    if len(stacks) == 1:
        return StackSelection(runbooks=(stacks[0],))
    resolver = links_mod.LinkResolver(graph)
    environments = {environment_of(node, resolver) for node in stacks}
    if len(environments) == 1 and "" not in environments:
        return StackSelection(runbooks=tuple(stacks), environment=environments.pop())
    ambiguous = StackSelection(reason="ambiguous",
                               candidates=tuple(node.id for node in stacks))
    candidates = environments
    if near is not None:
        features_root = path_mod.features_root(graph)
        near_path = near if near.is_absolute() else graph.root / near
        surface = graph_mod.surface_of(near_path, features_root)
        narrowed = [node for node in stacks
                    if surface and graph_mod.surface_of(node.path, features_root) == surface]
        if narrowed:
            candidates = {environment_of(node, resolver) for node in narrowed}
    local_only = {env for env in candidates
                  if env and _environment_is_local_only(graph, env)}
    if local_only:
        candidates = local_only
    if len(candidates) == 1 and "" not in candidates:
        return _selection_for(stacks, resolver, next(iter(candidates)))
    named = sorted(env for env in candidates if env)
    if named:
        return _selection_for(stacks, resolver, named[0])
    return ambiguous


def select_runbook(graph: Graph, name: str = "") -> UINode | None:
    """The single runbook this repo's QA stack comes from, or None.

    The one-manifest reading of :func:`select_stack`, kept for callers that take one stack
    or nothing. A multi-service environment resolves to None here — correctly, since there
    is no single runbook — and such a caller should be reading `select_stack` instead.
    """
    chosen = select_stack(graph, name).runbooks
    return chosen[0] if len(chosen) == 1 else None


def select_server(graph: Graph) -> UINode | None:
    """The `server` node whose launch contract this book's QA falls back to, or None.

    A sole server is it. Where a book declares several, the first by id: they are servers of
    one book, so the fallback contract is read off whichever the engine reaches first rather
    than off whichever one an author remembered to mark.

    A `server` node stating no `launch:` is not a candidate. It documents a service's
    contract without saying how the service starts, so there is nothing for a bring-up to
    fall back *to* — and a book with only such a node still owes `runbook-missing`, which
    gates on this function returning None.
    """
    servers = sorted((n for n in graph.ui_nodes_of_type("server")
                      if bullet_value(n.meta, "launch")), key=lambda n: n.id)
    return servers[0] if servers else None


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


def load_stack(root: Path | None = None, *, name: str = "", near: Path | None = None,
               graph: Graph | None = None,
               logger: logging.Logger | None = None) -> dict[str, Any]:
    """The manifest `ensure_stack` takes, read from the book's ops nodes.

    Returns ``{}`` when the book declares neither a runbook nor a `server` node —
    the only honest "nothing to bring up" left, and one the doctor reports as
    `runbook-missing` rather than leaving it to be discovered by a QA run that passes
    against nothing. Also returns ``{}`` on a refusal — several stack runbooks and no
    name given, or several bound to one environment — rather than falling back to the
    server contract, which would bring up the wrong system and call it a pass. A
    caller that needs to tell those cases apart, or that wants every manifest a
    multi-runbook environment covers, reads `select_stack` or `load_stacks` instead.

    Every `working-directory` comes back absolute. The manifest is authored repo-relative
    because that is what an author means; nothing downstream resolves it, so an unresolved
    `.` would launch the stack from whatever cwd the engine happens to hold.
    """
    log = logger or logging.getLogger(__name__)
    graph = graph if graph is not None else model.load(root or Path.cwd())
    selection = select_stack(graph, name, near=near)
    if len(selection.runbooks) == 1:
        log.info("stack declared by runbook %s", selection.runbooks[0].id)
        return _from_runbook(graph, selection.runbooks[0])
    if len(selection.runbooks) > 1:
        log.warning("%d stack runbooks share environment %s; load_stack returns one "
                    "manifest, use load_stacks", len(selection.runbooks),
                    selection.environment)
        return {}
    if selection.reason == "no-such-name":
        log.warning("no runbook named %r in the book", name)
        return {}
    if selection.reason == "ambiguous":
        log.warning("%d stack runbooks across several environments and none named: %s",
                    len(selection.candidates), ", ".join(selection.candidates))
        return {}
    server = select_server(graph)
    if server is not None:
        log.info("no runbook; falling back to the server contract on %s", server.id)
        return _from_server(graph, server)
    log.info("the book declares no runbook and no `server` node — nothing to bring up")
    return {}


def load_stacks(graph: Graph, *, name: str = "", near: Path | None = None,
                logger: logging.Logger | None = None,
                ) -> tuple[list[dict[str, Any]], StackSelection]:
    """Every manifest this book's bring-up covers, with the selection that produced it.

    One manifest per runbook rather than one merged manifest: each stack runbook carries
    its own `entry-url`, `health-path` and `boot-timeout`, and folding two services into
    one manifest would have to invent a single health check no author wrote — and then
    report the wrong service when it failed.

    The fallback to the `server` contract stays where it was, reached only when the
    book declares no stack runbook at all. A book that declares several and named none has
    not fallen back to anything; it has been refused.
    """
    log = logger or logging.getLogger(__name__)
    selection = select_stack(graph, name, near=near)
    if selection.runbooks:
        for node in selection.runbooks:
            log.info("stack declared by runbook %s", node.id)
        return [_from_runbook(graph, node) for node in selection.runbooks], selection
    if selection.reason == "no-such-name":
        log.warning("no runbook named %r in the book", name)
        return [], selection
    if selection.reason == "ambiguous":
        log.warning("%d stack runbooks across several environments and none named: %s",
                    len(selection.candidates), ", ".join(selection.candidates))
        return [], selection
    server = select_server(graph)
    if server is not None:
        log.info("no runbook; falling back to the server contract on %s", server.id)
        return [_from_server(graph, server)], selection
    log.info("the book declares no runbook and no `server` node — nothing to bring up")
    return [], selection


def _aimed(root: Path, features_root: str) -> Graph | None:
    """The graph for the book `features_root` names, or None to let the caller default.

    `qa context` resolves which book a run is about and records it in the packet; every
    later stage reads that packet. Passing the aim down is what stops a stage from
    answering a question about whichever book happens to sit under its cwd.
    """
    if not features_root:
        return None
    return model.load(root, root_overrides={"features": features_root})


def _aim_label(root: Path, features_root: str) -> str:
    return path_mod.resolve_features_root(features_root, root)


def _graph_for(root: Path, features_root: str) -> Graph:
    aimed = _aimed(root, features_root)
    return aimed if aimed is not None else model.load(root)


def _refusal(root: Path, features_root: str, selection: StackSelection,
             verb: str) -> QaOutcome | None:
    """The outcome for a selection that chose nothing, or None when it chose something.

    Three answers, three statuses. `none` is an honest verdict only about a book we
    actually read, so it says which one — aimed at the wrong book it used to be
    indistinguishable from a book that declares nothing, and the run continued against no
    stack at all. `ambiguous` and `unknown-runbook` are refusals rather than absences, and
    both are `ok=False`: the caller asked for a stack and is not getting one.
    """
    where = _aim_label(root, features_root)
    data: dict[str, Any] = {"manifest": {}, "featuresRoot": features_root,
                            "runbooks": list(selection.candidates)}
    if selection.reason == "no-such-name":
        return QaOutcome(ok=False, status="unknown-runbook", data=data,
                         message=f"the book under {where} declares no runbook by that name")
    if selection.reason == "ambiguous":
        return QaOutcome(
            ok=False, status="ambiguous", data=data,
            message=("the book under {} declares {} stack runbooks across several "
                     "environments and none was named — pass --runbook: {}".format(
                         where, len(selection.candidates), ", ".join(selection.candidates))))
    return QaOutcome(
        ok=True, status="none", data=data,
        message=("the book under {} declares no runbook and no `server` node — "
                 "nothing to {}".format(where, verb)))


def bring_up_stacks(manifests: list[dict[str, Any]], *, repo_root: str,
                    logger: logging.Logger | None = None) -> list[dict[str, Any]]:
    """Bring every manifest up in document order, stopping at the first that fails.

    A multi-service environment comes up one runbook at a time, in document order, and
    stops at the first that will not go healthy — the later services in a stack are the
    ones that call the earlier, so continuing past a failure only produces a second,
    derived failure to read. The caller inspects the last element of the returned list to
    see whether the whole bring-up succeeded: its `ready` is `"yes"` only when every
    manifest passed came up; otherwise it is the failing result.
    """
    log = logger or logging.getLogger(__name__)
    results: list[dict[str, Any]] = []
    for manifest in manifests:
        result = stack_mod.ensure_stack(
            manifest, repo_root=manifest.get("repo_root", repo_root), logger=log)
        results.append({**result, "manifest": manifest, "source": manifest.get("source", "")})
        if result.get("ready") != "yes":
            break
    return results


def cmd_stack_up(root: Path, *, name: str = "", features_root: str = "",
                 logger: logging.Logger | None = None) -> QaOutcome:
    """`ostler qa stack up` — bring the book's declared stack to ready, or say why not.

    The manifests it derived travel out in `data` beside the verdict: a repairer told only
    that `prepare[1]` failed re-derives from the book what the reader already knew, and a
    book whose recipe is subtly not the one the author meant is otherwise invisible.

    A multi-service environment comes up one runbook at a time, in document order, and
    stops at the first that will not go healthy — the later services in a stack are the
    ones that call the earlier, so continuing past a failure only produces a second,
    derived failure to read. See :func:`bring_up_stacks`, which owns the loop.
    """
    log = logger or logging.getLogger(__name__)
    manifests, selection = load_stacks(_graph_for(root, features_root), name=name, logger=log)
    refused = _refusal(root, features_root, selection, "bring up")
    if refused is not None and not manifests:
        return refused
    results = bring_up_stacks(manifests, repo_root=str(root), logger=log)
    last = results[-1]
    manifest = last["manifest"]
    if last.get("ready") != "yes":
        return QaOutcome(
            ok=False,
            message="stack bring-up failed for '{}' at step '{}'{}".format(
                manifest.get("source", "?"), last.get("failed_step", "unknown"),
                f": {last['error'].strip()}" if last.get("error") else ""),
            data={**last, "stacks": results, "source": manifest.get("source", "")})
    how = "adopted" if last.get("adopted") == "yes" else "brought up"
    where = ", ".join(r.get("entry_url") or "(no entry url)" for r in results)
    plural = "" if len(results) == 1 else f" ({len(results)} services)"
    return QaOutcome(
        ok=True, message=f"stack {how} and healthy at {where}{plural}",
        data={**last, "stacks": results, "environment": selection.environment})


def cmd_stack_down(root: Path, *, name: str = "", features_root: str = "",
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
    manifests, selection = load_stacks(_graph_for(root, features_root), name=name, logger=log)
    refused = _refusal(root, features_root, selection, "tear down")
    if refused is not None and not manifests:
        return refused
    # Reverse of bring-up order: the service that was started last is the one holding
    # connections to the ones under it.
    results = [stack_mod.teardown_stack({}, manifest, logger=log)
               for manifest in reversed(manifests)]
    torn = {r.get("torn_down", "no") for r in results}
    verdict = "no" if "no" in torn else ("skipped" if torn == {"skipped"} else "yes")
    return QaOutcome(
        ok=verdict != "no",
        message={"yes": "stack torn down",
                 "skipped": "no `stop:` recipe — leaving the stack serving"}.get(
                     verdict, "teardown failed"),
        data={**results[-1], "stacks": results},
    )


__all__ = [
    "REUSE_POLICIES",
    "STEP_KINDS",
    "STEP_PHASES",
    "bring_up_stacks",
    "bullet_value",
    "cmd_stack_down",
    "cmd_stack_up",
    "is_stack_runbook",
    "StackSelection",
    "environment_of",
    "load_stack",
    "load_stacks",
    "select_runbook",
    "select_stack",
    "system_root",
    "select_server",
    "stack_runbooks",
    "steps_of",
]
