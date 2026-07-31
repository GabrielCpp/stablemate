"""The walk's setting: is there an app to drive, and what does the book say boots it.

Ported from `base-library/workflows/okf-builder/scripts/{detect-webapp,seed-walkthrough}.py`.
Three divergences:

* **`ostler search` is called as a library.** `_search` shelled out to
  `ostler search <q> --type <t> --json` and parsed stdout; here it is
  `Ostler(root).search(q, etype=…)`, which is the same call one layer down. Its `except`
  arm is unchanged in effect: a search that cannot answer yields no rows, which reads as
  "no screens documented" and skips the walk rather than crashing it.
* **The `ModuleNotFoundError` fallback around `find_docs_root` is gone.** It existed so the
  script could be validated outside the workhorse venv; a node module imported by the
  workflow package has no such mode, and the base library's rule is that a declared
  dependency has no fallback.
* **`round` is no longer an output.** The script emitted `round=0` to reset the walk's own
  round-cap, because a YAML `var` is global to the run. Here the walk's round is a state
  parameter of the sub-flow, which starts at 0 by construction.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from ostler import Ostler, graph as graph_mod
from workhorse_workflows.okf_builder import paths
from workhorse_workflows.okf_builder.nodes import _stubs
from workhorse_workflows.okf_builder.nodes._blueprint import blueprint
from workhorse_workflows.okf_builder.schemas import WalkSeed, WebApp

FALLBACK_PORT = "8787"
LOOPBACK = "127.0.0.1"  # the docs' loopback option — keeps the walked app local
# Fixed because the walked repo's opencode.json points its playwright MCP at the same
# endpoint (--cdp-endpoint), and that file is static config.
CDP_URL = "http://127.0.0.1:9222"

#: The bullet that proves a screen was visually registered against a running app. Its absence
#: is what makes a screen unconfirmed — `screenshot:` alone is a picture, not a registration.
#:
#: It is counted **anywhere on the screen**, not only on the screen's file node. A vet report
#: describes one *state*, and a state is produced by an interaction, so walks attach the
#: bullet to the `mount-load-*` interaction that renders it. Looking only at the file node
#: scores every such screen unconfirmed and re-walks work that is already done.
VET_BULLET = "vet"


def _search(repo_root: str, etype: str, q: str = "") -> list[dict]:
    try:
        return Ostler(repo_root).search(q, etype=etype)
    except (OSError, ValueError, RuntimeError, KeyError):
        return []


def _read(repo_root: str, rel: str) -> str:
    try:
        return (Path(repo_root) / rel).read_text()
    except OSError:
        return ""


def _bullet(text: str, key: str) -> str:
    """The value of a machine-facing ``- key: value`` bullet.

    These bullets are prose documentation as much as they are interface, so a backticked
    value is the value even when explanation follows it on the same line (and even when
    that explanation wraps onto the next). Only an unbackticked bullet takes the whole
    line — there is no other way to tell value from commentary.
    """
    match = re.search(rf"(?m)^-\s*{re.escape(key)}:\s*(.+?)\s*$", text)
    if not match:
        return ""
    value = match.group(1)
    backticked = re.match(r"`([^`]+)`", value)
    return backticked.group(1) if backticked else value.strip()


def parse_launch_contract(text: str, repo_root: str, source_root: str) -> dict[str, str]:
    """Read the machine-facing runtime contract from one OKF server node."""
    launch_cmd = _bullet(text, "launch")
    entry_url = _bullet(text, "entry-url")
    if not launch_cmd or not entry_url:
        return {}

    working_directory = _bullet(text, "working-directory")
    app_cwd = Path(working_directory)
    if not app_cwd.is_absolute():
        app_cwd = Path(repo_root) / (working_directory or source_root)

    return {
        "launch_cmd": launch_cmd,
        "entry_url": entry_url.rstrip("/"),
        "health_path": _bullet(text, "health-path") or "/",
        "app_cwd": str(app_cwd.resolve()),
        "app_identity": _bullet(text, "identity"),
        # A bring-up command (docker compose, a make target) returns once the stack is
        # serving instead of staying in the foreground, and outlives the run — so it
        # needs its own stop recipe, and a ceiling measured in builds rather than in
        # process spawns. Both optional: a plain foreground server documents neither.
        "stop_cmd": _bullet(text, "stop"),
        "boot_timeout": _bullet(text, "boot-timeout"),
        # Which server the walk drives, when a service documents more than one way to
        # run the same app (a dev server, a production static server, a full stack).
        # The book's author marks the most PRODUCTION-LIKE one — matching prod's bundle
        # and request dispatch — because that is the app whose behaviour the screens
        # should document. Without it selection would fall back to search order.
        "walkthrough": _bullet(text, "walkthrough"),
    }


def _is_marked(value: str) -> bool:
    """Whether a `walkthrough:` bullet opts its server in. Prose is not a marker."""
    return value.strip().lower() in {"true", "yes", "primary"}


def select_server(
    server_paths: Iterable[str],
    read_contract: Callable[[str], dict[str, str]],
    logger: logging.Logger,
) -> dict[str, str]:
    """Pick the ONE server the walk drives, out of every server the service documents.

    A service can document several ways to run the same app — a dev server, a
    production static server, a full stack behind a gateway. They serve the same
    screens, so walking each in turn would only re-photograph them; what matters is
    driving the one whose bundle and dispatch match production. The book says which
    that is via ``walkthrough: true``; absent that, fall back to the first documented
    server and say so, since an unmarked book is making the choice by accident.
    """
    contracts = [(path, read_contract(path)) for path in server_paths]
    contracts = [(path, contract) for path, contract in contracts if contract]
    if not contracts:
        return {}

    marked = [(path, c) for path, c in contracts if _is_marked(c.get("walkthrough", ""))]
    if len(marked) > 1:
        # Ambiguous on purpose-looking input: pick deterministically but be loud, since
        # the book asserts two different apps are both the production-like one.
        logger.warning("%d servers are marked `walkthrough:` — %s; walking %s. Mark exactly "
                       "one, the most production-like.",
                       len(marked), ", ".join(path for path, _ in marked), marked[0][0])
    if marked:
        logger.info("walking the server marked `walkthrough:` — %s", marked[0][0])
        return marked[0][1]

    if len(contracts) > 1:
        logger.warning("%d servers document a launch contract (%s) but none is marked "
                       "`walkthrough: true` — falling back to %s. Add the bullet to the "
                       "most production-like one so this is not decided by file order.",
                       len(contracts), ", ".join(path for path, _ in contracts), contracts[0][0])
    return contracts[0][1]


@blueprint.node(stub=_stubs.webapp)
def detect_webapp(
    logger: logging.Logger,
    docs_path: str = "",
    service: str = "",
    source_path: str = "",
    repo_dir: str = "",
) -> WebApp:
    """The docs-derived gate + launch recipe.

    The FIRST node of the walk, so it resolves its own paths: the sub-flow is
    standalone-invokable and must not depend on the crawl having run. Everything it needs
    is read *from the book itself* via `ostler search` + the doc bodies:

    * web-app?      — the service documents at least one `screen` surface.
    * entry URL     — the `server` doc's machine-readable `entry-url:` bullet.
    * launch recipe — the server's `launch:` and `working-directory:` bullets, plus the
                      optional `stop:`/`boot-timeout:` bullets a bring-up command (docker
                      compose, a make target) needs and a foreground server does not.
    * which server  — a service may document several ways to run one app; `walkthrough:
                      true` marks the production-like one the walk drives (see
                      `select_server`).
    * identity      — a unique literal expected from `health-path:` so a process already
                      occupying the port cannot be mistaken for this service.

    Nothing is taken from the run's parameters: port, entry URL, health path and launch
    command are all detected from the documentation. Also allocates the walk worklist
    (build scratch) and the screenshots dir — which lives IN the book
    (`docs/features/<service>/gui/screenshots`), since screenshots are committed
    documentation evidence, referenced by `screenshot:` bullets and vetted by `ostler vet`.
    Emits the fixed `cdp_url` the walk's shared browser listens on (must match the repo's
    playwright-MCP `--cdp-endpoint`).
    """
    root = paths.docs_root(docs_path, repo_dir)
    source_root = str((root / (source_path or service)).resolve())
    features_root = str(paths.features_root(root, service)) if service else ""

    # A whole-tree build ("" service) has no single app to boot — skip cleanly.
    if not service:
        logger.info("no service given (whole-tree build) — no single app to walk, skipping")
        return WebApp(repo_root=str(root), source_root=source_root, cdp_url=CDP_URL)

    scope = f"docs/features/{service}/"

    # 1) Web-app iff the book documents at least one `screen` surface for this service.
    screens = [s for s in _search(str(root), "screen") if scope in s.get("path", "")]
    if not screens:
        # The whole walk is skipped from here. Undocumented screens and a service that
        # genuinely has no GUI look identical at this gate.
        logger.info("%s documents no screen surfaces — not a web app, skipping the walk",
                    service)
        return WebApp(repo_root=str(root), source_root=source_root,
                      features_root=features_root, cdp_url=CDP_URL)

    logger.info("%s documents %d screen surface(s) — this is a web app", service, len(screens))

    # 2) Prefer the explicit runtime contract on the server node. It is both documentation
    #    and the executable launch interface consumed by this walk.
    contract = select_server(
        # Sorted so that an unmarked book picks the SAME server every run. Search order
        # is not a promised interface, and a walk that silently changes which app it
        # documents between runs is worse than one that documents the wrong app twice.
        sorted(
            srv.get("path", "") for srv in _search(str(root), "server")
            if scope in srv.get("path", "")
        ),
        lambda path: parse_launch_contract(_read(str(root), path), str(root),
                                           source_path or service),
        logger,
    )

    # Compatibility fallback for older books that only document a Python-style `serve`
    # command. New/updated books should always use the explicit server contract above.
    port, cmd_name = FALLBACK_PORT, service
    if contract:
        logger.info("using the documented server contract: launch=%r entry-url=%s",
                    contract["launch_cmd"], contract["entry_url"])
        launch_cmd = contract["launch_cmd"]
        entry_url = contract["entry_url"]
        health_path = contract["health_path"]
        app_cwd = contract["app_cwd"]
        app_identity = contract["app_identity"]
        stop_cmd = contract["stop_cmd"]
        boot_timeout = contract["boot_timeout"]
    else:
        # No server contract: the guessed recipe carries no identity marker, so boot_app
        # cannot adopt a running app and will not reuse whatever holds the port.
        logger.warning("no server node with `launch:`/`entry-url:` bullets for %s — "
                       "falling back to a guessed serve command", service)
        for c in _search(str(root), "command", "serve"):
            if scope not in c.get("path", ""):
                continue
            text = _read(str(root), c["path"])
            m_name = re.search(r"usage:\s*`?(\w[\w-]*)\s+serve\b", text)
            if m_name:
                cmd_name = m_name.group(1)
            m_port = re.search(r"`--port[^`]*`[\s\S]*?default:\s*`?(\d+)`?", text)
            if m_port:
                port = m_port.group(1)
            break

        venv_bin = root / ".venv" / "bin" / cmd_name
        venv_py = root / ".venv" / "bin" / "python"
        flags = f"serve --host {LOOPBACK} --port {port}"
        if venv_bin.exists():
            launch_cmd = f"{venv_bin} {flags}"
        elif venv_py.exists():
            launch_cmd = f"{venv_py} -m {cmd_name} {flags}"
        else:
            launch_cmd = f"{cmd_name} {flags}"
        entry_url = f"http://{LOOPBACK}:{port}"
        health_path = "/"
        app_cwd = source_root
        app_identity = ""
        stop_cmd = ""
        boot_timeout = ""

    # 3) Walk worklist stays build scratch; screenshots live IN the book — they are
    #    committed evidence the docs' `screenshot:` bullets reference.
    paths.build_dir(root).mkdir(parents=True, exist_ok=True)
    wl = paths.walk_worklist_path(root, service)
    if not wl.exists():
        wl.write_text(json.dumps({"items": []}, indent=2))
    shots = paths.screenshots_dir(features_root)
    shots.mkdir(parents=True, exist_ok=True)

    return WebApp(
        is_webapp=True,
        repo_root=str(root),
        source_root=source_root,
        features_root=features_root,
        entry_url=entry_url,
        launch_cmd=launch_cmd,
        health_path=health_path,
        app_cwd=app_cwd,
        app_identity=app_identity,
        stop_cmd=stop_cmd,
        boot_timeout=boot_timeout,
        wt_worklist_path=str(wl),
        screenshots_dir=str(shots),
        cdp_url=CDP_URL,
    )


def _screen_of(node_id: str, by_id: dict) -> str | None:
    """The screen a node lives on: its file-level node, when that file is a screen doc."""
    file_id = node_id.split("#", 1)[0]
    node = by_id.get(file_id)
    return file_id if node is not None and node.get("type") == "screen" else None


def _book(repo_root: str, service: str, logger: logging.Logger) -> dict | None:
    """The service's graph, in-process. A graph that will not load seeds nothing, loudly.

    Only the *graph* is fallible here: an interpreter that cannot import ostler never
    reaches this node, because the workflow declares ``dist: ostler`` in ``requires:``
    and workhorse refuses to start the run.
    """
    try:
        return graph_mod.build(Ostler(repo_root).graph, surface=service or None)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        logger.warning("could not load the OKF graph — the walk cannot be seeded: %s", exc)
        return None


@blueprint.node
def seed_walkthrough(
    logger: logging.Logger,
    wt_worklist_path: str = "",
    service: str = "",
    repo_root: str = ".",
) -> WalkSeed:
    """Seed the walk worklist with the *unconfirmed* delta.

    The walk's product is visual evidence: a screenshot per screen state and, via `ostler
    vet`, a registered crop per documented component. So the walk's delta is not the code
    delta — a screen is behind because it carries no evidence, not because its source
    moved. Design §10.3 calls this the **unconfirmed** set and computes it by set arithmetic
    against the book, needing no git anchor.

    Two item kinds are seeded, and the order matters:

    * `journey` — one per `flow` doc that still traverses an unconfirmed screen. Journeys go
      first because they arrive with state the earlier steps established, which is the only
      way some screens render at all.
    * `screen` — one per unconfirmed screen, as the sweep that catches what no journey
      covers. The walk turn resolves its path with `ostler reach` rather than navigating to
      `route:`, so a screen is reached the way a user would or is reported as a book defect.

    Re-seeding is therefore idempotent against evidence: a screen that already carries a
    `vet:` bullet is not re-walked, and a journey whose screens are all confirmed stays
    `done`. The previous behaviour — reopening *every* done journey on every run — made each
    run redo the same paths regardless of what was already registered, so the gap never
    closed.
    """
    wl_path = Path(wt_worklist_path)
    data = json.loads(wl_path.read_text()) if wl_path.exists() else {"items": []}
    items = data.get("items", [])
    by_key = {(i.get("kind"), i.get("target")): i for i in items}

    book = _book(repo_root or ".", service, logger)
    if book is None:
        return WalkSeed(
            done_count=sum(1 for i in items if i.get("status") == "done"),
            pending_count=sum(1 for i in items if i.get("status") == "pending"),
        )

    by_id = {n["id"]: n for n in book["nodes"]}
    screens = [n for n in book["nodes"] if n["type"] == "screen" and n["kind"] == "file"]
    registered = {
        screen for n in book["nodes"] if VET_BULLET in n.get("bullets", {})
        if (screen := _screen_of(n["id"], by_id)) is not None
    }
    unconfirmed = {n["id"] for n in screens} - registered

    added = 0

    def _seed(kind: str, target: str, context: str) -> None:
        nonlocal added
        existing = by_key.get((kind, target))
        if existing is None:
            items.append({"kind": kind, "target": target, "context": context,
                          "status": "pending"})
            by_key[(kind, target)] = items[-1]
            added += 1
        elif existing.get("status") == "done":
            # Done, but the evidence it should have produced is absent — the earlier run did
            # not finish the job, so reopen it. A confirmed target never reaches this branch.
            existing["status"] = "pending"
            existing["context"] = context
            added += 1

    for flow in (n for n in book["nodes"] if n["type"] == "flow"):
        touched = {s for s in (_screen_of(e["to"], by_id) for e in flow["edges"]) if s}
        if not touched & unconfirmed:
            continue  # every screen this journey covers is already registered
        _seed("journey", f"flow:{Path(flow['path']).stem}", flow["title"])

    for screen in sorted(unconfirmed):
        _seed("screen", screen, by_id[screen]["title"])

    data["items"] = items
    wl_path.write_text(json.dumps(data, indent=2))
    done = sum(1 for i in items if i.get("status") == "done")
    pend = sum(1 for i in items if i.get("status") == "pending")
    if not pend:
        logger.info("nothing to walk: all %d screen(s) under %s carry `%s:` evidence",
                    len(screens), service or "(whole book)", VET_BULLET)
    logger.info("seeded walk worklist %s: %d item(s) added, %d/%d screen(s) unconfirmed, "
                "%d done / %d pending", wl_path, added, len(unconfirmed), len(screens),
                done, pend)
    return WalkSeed(done_count=done, pending_count=pend, added=added,
                    unconfirmed_count=len(unconfirmed), screen_count=len(screens))


__all__ = [
    "CDP_URL",
    "VET_BULLET",
    "detect_webapp",
    "parse_launch_contract",
    "seed_walkthrough",
    "select_server",
]
