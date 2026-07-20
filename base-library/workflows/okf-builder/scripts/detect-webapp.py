#!/usr/bin/env python3
"""okf-builder walkthrough: the docs-derived gate + launch recipe.

The FIRST node of the ``walkthrough`` flow, so it resolves its own paths (the flow
is standalone-invokable — ``workhorse run okf-builder walkthrough --params
'{"service":"groom"}'`` — and must not depend on the crawl having run). Everything it
needs is read *from the book itself* via ``ostler search`` + the doc bodies:

  * web-app?      — the service documents at least one ``screen`` surface.
  * entry URL     — the ``server`` doc's machine-readable ``entry-url:`` bullet.
  * launch recipe — the server's ``launch:`` and ``working-directory:`` bullets, plus
                    the optional ``stop:``/``boot-timeout:`` bullets a bring-up command
                    (docker compose, a make target) needs and a foreground server does not.
  * which server  — a service may document several ways to run one app; ``walkthrough:
                    true`` marks the production-like one the walk drives (see
                    ``select_server``).
  * identity      — a unique literal expected from ``health-path:`` so a process already
                    occupying the port cannot be mistaken for this service.

Nothing is taken from workflow vars: port, entry URL, health path and launch command
are all detected from the documentation. Also allocates the walk worklist (build
scratch) and the screenshots dir — which lives IN the book
(``docs/features/<service>/gui/screenshots``), since screenshots are committed
documentation evidence, referenced by ``screenshot:`` bullets and vetted by
``ostler vet``. Resets ``round`` so the walk's round-cap is its own, and emits the
fixed ``cdp_url`` the walk's shared browser listens on (must match the repo's
playwright-MCP ``--cdp-endpoint``).

Args: [docs_path] [service] [source_path]
Outputs JSON: {"is_webapp","repo_root","source_root","features_root","entry_url","launch_cmd",
               "health_path","app_cwd","app_identity","stop_cmd","boot_timeout",
               "wt_worklist_path","screenshots_dir","cdp_url","round"}
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from workhorse.scriptutil import find_docs_root
except ModuleNotFoundError:  # Allow direct validation outside the Workhorse venv.
    def find_docs_root(value: str) -> Path:
        return Path(value or os.environ.get("AGENT_REPO_DIR", ".")).resolve()

FALLBACK_PORT = "8787"
LOOPBACK = "127.0.0.1"  # the docs' loopback option — keeps the walked app local
# Fixed because the walked repo's opencode.json points its playwright MCP at the same
# endpoint (--cdp-endpoint), and that file is static config.
CDP_URL = "http://127.0.0.1:9222"


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "is_webapp": "no", "repo_root": "", "source_root": "", "features_root": "", "entry_url": "",
        "launch_cmd": "", "health_path": "/", "app_cwd": "", "app_identity": "",
        "stop_cmd": "", "boot_timeout": "", "wt_worklist_path": "",
        "screenshots_dir": "", "cdp_url": CDP_URL, "round": 0,
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _search(repo_root: str, etype: str, q: str = "") -> list[dict]:
    try:
        p = subprocess.run(
            ["ostler", "search", q, "--type", etype, "--json"],
            cwd=repo_root, capture_output=True, text=True, timeout=120,
        )
        data = json.loads(p.stdout or "[]")
        return data if isinstance(data, list) else []
    except (OSError, subprocess.SubprocessError, ValueError):
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


def select_server(paths, read_contract, logger: logging.Logger) -> dict[str, str]:
    """Pick the ONE server the walk drives, out of every server the service documents.

    A service can document several ways to run the same app — a dev server, a
    production static server, a full stack behind a gateway. They serve the same
    screens, so walking each in turn would only re-photograph them; what matters is
    driving the one whose bundle and dispatch match production. The book says which
    that is via ``walkthrough: true``; absent that, fall back to the first documented
    server and say so, since an unmarked book is making the choice by accident.
    """
    contracts = [(path, read_contract(path)) for path in paths]
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


def main(logger: logging.Logger) -> None:
    docs_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    service = sys.argv[2] if len(sys.argv) > 2 else ""
    source_path = sys.argv[3] if len(sys.argv) > 3 else ""
    root = str(find_docs_root(docs_arg))
    source_root = str((Path(root) / (source_path or service)).resolve())
    features_root = str(Path(root) / "docs" / "features" / service) if service else ""

    # A whole-tree build ("" service) has no single app to boot — skip cleanly.
    if not service:
        logger.info("no service given (whole-tree build) — no single app to walk, skipping")
        emit(is_webapp="no", repo_root=root, source_root=source_root)

    scope = f"docs/features/{service}/"

    # 1) Web-app iff the book documents at least one `screen` surface for this service.
    screens = [s for s in _search(root, "screen") if scope in s.get("path", "")]
    if not screens:
        # The whole walkthrough flow is skipped from here. Undocumented screens and a
        # service that genuinely has no GUI look identical at this gate.
        logger.info("%s documents no screen surfaces — not a web app, skipping the walk",
                    service)
        emit(is_webapp="no", repo_root=root, source_root=source_root, features_root=features_root)

    logger.info("%s documents %d screen surface(s) — this is a web app", service, len(screens))

    # 2) Prefer the explicit runtime contract on the server node. It is both documentation
    #    and the executable launch interface consumed by this walkthrough.
    contract = select_server(
        # Sorted so that an unmarked book picks the SAME server every run. Search order
        # is not a promised interface, and a walk that silently changes which app it
        # documents between runs is worse than one that documents the wrong app twice.
        sorted(
            (srv.get("path", "") for srv in _search(root, "server") if scope in srv.get("path", "")),
        ),
        lambda path: parse_launch_contract(_read(root, path), root, source_path or service),
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
        # No server contract: the guessed recipe carries no identity marker, so boot-app
        # cannot adopt a running app and will not reuse whatever holds the port.
        logger.warning("no server node with `launch:`/`entry-url:` bullets for %s — "
                       "falling back to a guessed serve command", service)
        for c in _search(root, "command", "serve"):
            if scope not in c.get("path", ""):
                continue
            text = _read(root, c["path"])
            m_name = re.search(r"usage:\s*`?(\w[\w-]*)\s+serve\b", text)
            if m_name:
                cmd_name = m_name.group(1)
            m_port = re.search(r"`--port[^`]*`[\s\S]*?default:\s*`?(\d+)`?", text)
            if m_port:
                port = m_port.group(1)
            break

        venv_bin = Path(root) / ".venv" / "bin" / cmd_name
        venv_py = Path(root) / ".venv" / "bin" / "python"
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

    # 4) Walk worklist stays build scratch; screenshots live IN the book — they are
    #    committed evidence the docs' `screenshot:` bullets reference.
    build_dir = Path(root) / ".agents" / "okf-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    wl = build_dir / f"{service}.walkthrough.json"
    if not wl.exists():
        wl.write_text(json.dumps({"items": []}, indent=2))
    shots = Path(features_root) / "gui" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)

    emit(is_webapp="yes", repo_root=root, source_root=source_root, features_root=features_root,
         entry_url=entry_url, launch_cmd=launch_cmd, health_path=health_path,
         app_cwd=app_cwd, app_identity=app_identity,
         stop_cmd=stop_cmd, boot_timeout=boot_timeout,
         wt_worklist_path=str(wl), screenshots_dir=str(shots), round=0)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("detect-webapp"))
