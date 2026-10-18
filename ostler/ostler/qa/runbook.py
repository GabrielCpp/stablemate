"""Read the durable QA stack out of the book's ops nodes."""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler import checks
from ostler import graph as graph_mod
from ostler import links as links_mod
from ostler import markdown
from ostler import model
from ostler import path as path_mod
from ostler.environments import leases
from ostler.model import Graph, UINode
from ostler.qa import addresses
from ostler.qa import stack as stack_mod
from ostler.qa.outcome import QaOutcome
from ostler.registry import SCENARIO_FRAME_TOKEN, STEP_KIND_VALUES

STEP_PHASES: dict[str, str] = {
    "prepare": "prepare",
    "service": "launch",
    "seed": "seed",
    "health": "health",
}
STEP_KINDS: frozenset[str] = frozenset(STEP_KIND_VALUES)
REUSE_POLICIES: frozenset[str] = frozenset({"if-fresh", "always", "never"})

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
    """A raw bullet string, extracted the way this book's values are actually read."""
    text = text.strip()
    backticked = re.match(r"`([^`]+)`", text)
    return backticked.group(1).strip() if backticked else text.partition("\n")[0].strip()


def bullet_value(meta: dict, key: str) -> str:
    """One bullet's value as a string — a repeated bullet keeps its first value."""
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
    """The runbook's `### id` steps, in document order."""
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


def is_scenario_frame(value: str, root: Path) -> bool:
    """Whether a `working-directory:` bullet states the scenario-frame token, or the bare word when the checkout holds no directory by that name."""
    text = value.strip()
    bare = SCENARIO_FRAME_TOKEN.rstrip(":")
    return text == SCENARIO_FRAME_TOKEN or (text == bare and not (root / bare).is_dir())


def _step_command(node: UINode, root: Path, default_cwd: str) -> dict[str, str] | None:
    """One `step` node as the mapping `stack._run_step`/`book_fixtures` reads, or None when it has no command."""
    command = bullet_value(node.meta, "run")
    if not command or checks.is_check_expression(command):
        return None
    if bullet_value(node.meta, "optional").lower() in ("true", "yes"):
        command = f"{command} || true"
    exports = _env_exports(node)
    if exports:
        command = f"{exports} {command}"
    cwd = bullet_value(node.meta, "working-directory")
    step: dict[str, str] = {"run": command}
    if is_scenario_frame(cwd, root):
        step["cwd-frame"] = "scenario"
    else:
        step["working-directory"] = str((root / (cwd or default_cwd or ".")).resolve())
    timeout = bullet_value(node.meta, "timeout")
    if timeout:
        step["timeout"] = timeout
    return step


def step_command(node: UINode, root: Path, default_cwd: str) -> dict[str, str] | None:
    """Public alias of `_step_command`, for a caller outside this module (`book_fixtures`)."""
    return _step_command(node, root, default_cwd)


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _env_exports(node: UINode) -> str:
    """A step's `env:` children as a shell prefix."""
    assignments = [
        value
        for value in (bullet_text(item) for item in _children(node.meta, "env"))
        if _ASSIGNMENT.match(value)
    ]
    return "".join(f"export {item}; " for item in assignments).strip()


def _secrets_of(meta: dict) -> dict[str, str]:
    """The runbook's `secrets:` children as ``{ENV_NAME: mint recipe}``."""
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
    """The root of the system this book describes, which is not always where it was read."""
    features = path_mod.features_root(graph)
    try:
        relative = features.relative_to(graph.root).as_posix()
    except ValueError:
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
            if step and "launch" not in manifest:
                manifest["launch"] = step["run"]
                manifest["launch_cwd"] = step.get(
                    "working-directory", manifest["app_cwd"])
            gate = bullet_value(node.meta, "health")
            if gate and not checks.is_check_expression(gate):
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

    A `driver: mobile` runbook always does, because its prepare steps boot the device and
    install the app even when the app calls no backend.
    """
    if bullet_value(node.meta, "driver") == "mobile":
        return True
    if bullet_value(node.meta, "entry-url") or bullet_value(node.meta, "launch"):
        return True
    return any(bullet_value(step.meta, "kind") == "service" for step in steps_of(graph, node))


def stack_runbooks(graph: Graph) -> list[UINode]:
    """Every runbook that claims to bring a system up, in document order."""
    return [n for n in graph.ui_nodes_of_type("runbook") if is_stack_runbook(graph, n)]


@dataclass(frozen=True)
class StackSelection:
    """Which runbooks a bring-up covers — or, when none was chosen, *why* none was."""

    runbooks: tuple[UINode, ...] = ()
    reason: str = ""
    environment: str = ""
    candidates: tuple[str, ...] = field(default=())


def environment_of(node: UINode, resolver: links_mod.LinkResolver) -> str:
    """The node id *node*'s `environment:` link resolves to, or `""`."""
    value = node.meta.get("environment", "")
    if isinstance(value, list):
        value = value[0] if value else ""
    for _text, href in markdown.extract_refs(str(value)).links:
        target = resolver.resolve(node.path, href)
        if target is not None and target.resolved:
            return target.node_id
    return ""


@dataclass(frozen=True)
class EnvironmentAddresses:
    """An environment page's named addresses, and whether each run gets its own copy of them."""

    environment: UINode
    per_run: bool
    entries: dict[str, str]

    def shared_book(self) -> dict[str, str]:
        """The book a shared environment's page gives: each name's stated URL."""
        return {name: value.rstrip("/") for name, value in self.entries.items()}


def environment_addresses(node: UINode) -> EnvironmentAddresses:
    """The `addresses:` and `sharing:` bullets of the `environment` node *node*."""
    entries: dict[str, str] = {}
    for item in _children(node.meta, "addresses"):
        idx = markdown.label_colon_index(item)
        if idx == -1:
            continue
        name = item[:idx].strip().strip("`")
        if name:
            entries[name] = bullet_text(item[idx + 1:])
    per_run = bullet_value(node.meta, "sharing").lower() == "per-run"
    return EnvironmentAddresses(environment=node, per_run=per_run, entries=entries)


def _environment_is_local_only(graph: Graph, environment_id: str) -> bool:
    """Whether the `environment` node *environment_id* declares itself `local-only: true`."""
    node = graph.find_ui_node(environment_id)
    if node is None:
        return False
    return bullet_value(node.meta, "local-only") in ("true", "yes")


def _environment_is_per_run(graph: Graph, environment_id: str) -> bool:
    """Whether the `environment` node *environment_id* gives each run its own copy."""
    node = graph.find_ui_node(environment_id)
    return node is not None and environment_addresses(node).per_run


def _selection_for(stacks: list[UINode], resolver: links_mod.LinkResolver,
                   environment: str) -> StackSelection:
    """Every stack runbook bound to *environment*, as a resolved selection."""
    selected = tuple(node for node in stacks if environment_of(node, resolver) == environment)
    return StackSelection(runbooks=selected, environment=environment)


def select_stack(graph: Graph, name: str = "", *, near: Path | None = None,
                 leased: bool = False) -> StackSelection:
    """Which runbooks bring this book's system up, or why the question has no answer.

    A bring-up that holds a lease asks for a copy of its own, so among environments still
    in the running it prefers the ones copied per run, and one that holds none prefers
    the shared ones a run without a lease can bring up.
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
        narrowed = _on_surface_of(graph, stacks, near)
        if narrowed:
            candidates = {environment_of(node, resolver) for node in narrowed}
    copies = {env for env in candidates
              if env and _environment_is_per_run(graph, env) == leased}
    if copies:
        candidates = copies
    local_only = {env for env in candidates
                  if env and _environment_is_local_only(graph, env)}
    if local_only:
        candidates = local_only
    if len(candidates) > 1 and near is not None:
        serving = {environment_of(node, resolver) for node in _serving_target(graph, stacks, near)}
        if serving & candidates:
            candidates = serving & candidates
    if len(candidates) == 1 and "" not in candidates:
        return _selection_for(stacks, resolver, next(iter(candidates)))
    named = sorted(env for env in candidates if env)
    if named:
        return _selection_for(stacks, resolver, named[0])
    return ambiguous


def select_runbook(graph: Graph, name: str = "") -> UINode | None:
    """The single runbook this repo's QA stack comes from, or None."""
    chosen = select_stack(graph, name).runbooks
    return chosen[0] if len(chosen) == 1 else None


def select_server(graph: Graph) -> UINode | None:
    """The `server` node whose launch contract this book's QA falls back to, or None."""
    servers = sorted((n for n in graph.ui_nodes_of_type("server")
                      if bullet_value(n.meta, "launch")), key=lambda n: n.id)
    return servers[0] if servers else None


def _surface_near(graph: Graph, near: Path) -> str:
    """The surface *near* belongs to, or "" when it sits on none."""
    return graph_mod.surface_of(near if near.is_absolute() else graph.root / near,
                                path_mod.features_root(graph))


def _on_surface_of(graph: Graph, nodes: list[UINode], near: Path) -> list[UINode]:
    """The *nodes* on the surface *near* belongs to, or none when *near* sits on no surface."""
    surface = _surface_near(graph, near)
    features_root = path_mod.features_root(graph)
    return [node for node in nodes
            if surface and graph_mod.surface_of(node.path, features_root) == surface]


def _serving_target(graph: Graph, stacks: list[UINode], near: Path) -> list[UINode]:
    """The *stacks* on *near*'s surface whose `entry-url:` is the address that surface's checks are compiled against."""
    from ostler import reach

    surface = _surface_near(graph, near)
    target = reach.entry_origin(graph_mod.build(graph), surface) if surface else None
    if not target:
        return []
    return [node for node in _on_surface_of(graph, stacks, near)
            if reach.url_origin(bullet_value(node.meta, "entry-url")) == target]


def has_served_surface(graph: Graph, near: Path | None = None) -> bool:
    """Whether anything in this book has to be *running* before QA can reach it.

    With *near*, the question is asked of the one surface that path belongs to: a
    command-line book serves nothing even when a book beside it serves a screen.
    """
    served = [*graph.ui_nodes_of_type("screen"), *graph.ui_nodes_of_type("server")]
    if near is not None and _surface_near(graph, near):
        return bool(_on_surface_of(graph, served, near))
    return bool(served)


def load_stack(root: Path | None = None, *, name: str = "", near: Path | None = None,
               graph: Graph | None = None,
               logger: logging.Logger | None = None) -> dict[str, Any]:
    """The manifest `ensure_stack` takes, read from the book's ops nodes."""
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
                leased: bool = False, logger: logging.Logger | None = None,
                ) -> tuple[list[dict[str, Any]], StackSelection]:
    """Every manifest this book's bring-up covers, with the selection that produced it."""
    log = logger or logging.getLogger(__name__)
    selection = select_stack(graph, name, near=near, leased=leased)
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
    """The graph for the book `features_root` names, or None to let the caller default."""
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
    """The outcome for a selection that chose nothing, or None when it chose something."""
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


@dataclass(frozen=True)
class StackLease:
    """The copy one bring-up holds: the name it runs under, and the book its addresses are read from."""

    name: str = ""
    book: Path | None = None
    addresses: EnvironmentAddresses | None = None

    @property
    def env(self) -> dict[str, str]:
        """What every recipe of this bring-up finds in its environment."""
        env = {addresses.LEASE_ENV: self.name} if self.name else {}
        if self.book is not None:
            env[addresses.BOOK_ENV] = str(self.book)
        return env

    @property
    def per_run(self) -> bool:
        return self.addresses is not None and self.addresses.per_run

    def problems(self) -> list[str]:
        """Why the book this bring-up left cannot serve the environment, one sentence each."""
        if self.book is None or self.addresses is None:
            return []
        try:
            book = addresses.read_book(self.book)
        except addresses.AddressError as exc:
            return [str(exc)]
        return addresses.book_problems(book, self.addresses.entries)

    @contextlib.contextmanager
    def holding(self) -> Iterator[None]:
        """Hold the lease in this process's environment, with a shared stack's book written from its page."""
        with addresses.leased(self.env):
            if self.book is not None and self.addresses is not None and not self.per_run:
                addresses.write_book(self.book, self.addresses.shared_book())
            yield

    def data(self) -> dict[str, Any]:
        """The lease as an outcome reports it."""
        book: dict[str, str] = {}
        if self.book is not None:
            try:
                book = addresses.read_book(self.book)
            except addresses.AddressError:
                book = {}
        return {"lease": self.name, "address_book": str(self.book or ""), "addresses": book}


def _addressed_environment(graph: Graph, selection: StackSelection) -> EnvironmentAddresses | None:
    """The addresses of the environment every selected runbook binds, or None when it names none."""
    environment = selection.environment
    if not environment and selection.runbooks:
        resolver = links_mod.LinkResolver(graph)
        bound = {environment_of(node, resolver) for node in selection.runbooks}
        environment = bound.pop() if len(bound) == 1 else ""
    node = graph.find_ui_node(environment) if environment else None
    if node is None:
        return None
    found = environment_addresses(node)
    return found if found.per_run or found.entries else None


def stack_lease(graph: Graph, selection: StackSelection, lease: str) -> StackLease | QaOutcome:
    """The lease a bring-up or a teardown runs under, or the refusal that stops it."""
    if lease and (problem := addresses.lease_problem(lease)):
        return QaOutcome(ok=False, status="bad-lease", data={"lease": lease},
                         message=f"`{lease}` cannot name a copy: {problem}")
    found = _addressed_environment(graph, selection)
    if found is None:
        return StackLease(name=lease)
    if found.per_run and not lease:
        return QaOutcome(
            ok=False, status="lease-required", data={"environment": found.environment.id},
            message=(f"the environment {found.environment.id} gives each run its own copy, so "
                     f"the copy needs a name: pass --lease NAME or set {addresses.LEASE_ENV}"))
    page = graph.root / found.environment.path
    book = addresses.book_path(page, lease if found.per_run else "")
    return StackLease(name=lease, book=book, addresses=found)


def bring_up_stacks(manifests: list[dict[str, Any]], *, repo_root: str,
                    logger: logging.Logger | None = None) -> list[dict[str, Any]]:
    """Bring every manifest up in document order, stopping at the first that fails."""
    log = logger or logging.getLogger(__name__)
    results: list[dict[str, Any]] = []
    for manifest in manifests:
        result = stack_mod.ensure_stack(
            manifest, repo_root=manifest.get("repo_root", repo_root), logger=log)
        results.append({**result, "manifest": manifest, "source": manifest.get("source", "")})
        if result.get("ready") != "yes":
            break
    return results


def _from_stack_file(root: Path, features_root: str, lease: str, near: Path | None,
                     act: Callable[..., QaOutcome | None]) -> QaOutcome | None:
    """A copy from the books' `stack.yml`, or None where a lease-less call keeps a runbook's stack."""
    if not lease and stack_runbooks(_graph_for(root, features_root)):
        return None
    return act(root, lease=lease, near=near)


def cmd_stack_up(root: Path, *, name: str = "", features_root: str = "", lease: str = "",
                 near: Path | None = None,
                 logger: logging.Logger | None = None) -> QaOutcome:
    """`ostler qa stack up` — bring the book's declared stack to ready, or say why not."""
    copied = None if name else _from_stack_file(root, features_root, lease, near, leases.up)
    if copied is not None:
        return copied
    log = logger or logging.getLogger(__name__)
    graph = _graph_for(root, features_root)
    manifests, selection = load_stacks(graph, name=name, near=near, leased=bool(lease),
                                       logger=log)
    refused = _refusal(root, features_root, selection, "bring up")
    if refused is not None and not manifests:
        return refused
    held = stack_lease(graph, selection, lease)
    if isinstance(held, QaOutcome):
        return held
    if held.per_run and held.book is not None:
        held.book.unlink(missing_ok=True)
    with held.holding():
        results = bring_up_stacks(manifests, repo_root=str(root), logger=log)
        problems = held.problems() if results[-1].get("ready") == "yes" else []
    last = results[-1]
    manifest = last["manifest"]
    if last.get("ready") != "yes":
        return QaOutcome(
            ok=False,
            message="stack bring-up failed for '{}' at step '{}'{}".format(
                manifest.get("source", "?"), last.get("failed_step", "unknown"),
                f": {last['error'].strip()}" if last.get("error") else ""),
            data={**last, "stacks": results, "source": manifest.get("source", ""),
                  **held.data()})
    if problems:
        return QaOutcome(
            ok=False, status="address-book",
            message="the stack came up, but the address book it left at {} {}".format(
                held.book, "; ".join(problems)),
            data={**last, "stacks": results, "environment": selection.environment,
                  **held.data()})
    how = "adopted" if last.get("adopted") == "yes" else "brought up"
    where = ", ".join(r.get("entry_url") or "(no entry url)" for r in results)
    plural = "" if len(results) == 1 else f" ({len(results)} services)"
    return QaOutcome(
        ok=True, message=f"stack {how} and healthy at {where}{plural}",
        data={**last, "stacks": results, "environment": selection.environment,
              **held.data()})


def cmd_stack_down(root: Path, *, name: str = "", features_root: str = "", lease: str = "",
                   near: Path | None = None,
                   logger: logging.Logger | None = None) -> QaOutcome:
    """`ostler qa stack down` — run the declared teardown, or leave an expensive stack up."""
    copied = None if name else _from_stack_file(root, features_root, lease, near, leases.down)
    if copied is not None:
        return copied
    log = logger or logging.getLogger(__name__)
    graph = _graph_for(root, features_root)
    manifests, selection = load_stacks(graph, name=name, near=near, leased=bool(lease),
                                       logger=log)
    refused = _refusal(root, features_root, selection, "tear down")
    if refused is not None and not manifests:
        return refused
    held = stack_lease(graph, selection, lease)
    if isinstance(held, QaOutcome):
        return held
    with held.holding():
        results = [stack_mod.teardown_stack({}, manifest, logger=log)
                   for manifest in reversed(manifests)]
    torn = {r.get("torn_down", "no") for r in results}
    verdict = "no" if "no" in torn else ("skipped" if torn == {"skipped"} else "yes")
    if verdict == "yes" and held.per_run and held.book is not None:
        held.book.unlink(missing_ok=True)
    return QaOutcome(
        ok=verdict != "no",
        message={"yes": "stack torn down",
                 "skipped": "no `stop:` recipe — leaving the stack serving"}.get(
                     verdict, "teardown failed"),
        data={**results[-1], "stacks": results, "lease": held.name},
    )


__all__ = [
    "REUSE_POLICIES",
    "STEP_KINDS",
    "STEP_PHASES",
    "bring_up_stacks",
    "bullet_value",
    "cmd_stack_down",
    "cmd_stack_up",
    "EnvironmentAddresses",
    "StackLease",
    "environment_addresses",
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
    "stack_lease",
    "steps_of",
]
