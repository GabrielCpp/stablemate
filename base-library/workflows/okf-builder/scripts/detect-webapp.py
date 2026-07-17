#!/usr/bin/env python3
"""okf-builder walkthrough: the docs-derived gate + launch recipe.

The FIRST node of the ``walkthrough`` flow, so it resolves its own paths (the flow
is standalone-invokable — ``workhorse run okf-builder walkthrough --params
'{"service":"groom"}'`` — and must not depend on the crawl having run). Everything it
needs is read *from the book itself* via ``ostler search`` + the doc bodies:

  * web-app?      — the service documents at least one ``screen`` surface.
  * entry URL     — the ``server`` doc's machine-readable ``entry-url:`` bullet.
  * launch recipe — the server's ``launch:`` and ``working-directory:`` bullets.
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
               "health_path","app_cwd","app_identity","wt_worklist_path","screenshots_dir",
               "cdp_url","round"}
"""
from __future__ import annotations

import json
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
        "wt_worklist_path": "",
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
    match = re.search(rf"(?m)^-\s*{re.escape(key)}:\s*(?:`([^`]+)`|(.+?))\s*$", text)
    if not match:
        return ""
    return (match.group(1) or match.group(2) or "").strip()


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
    }


def main() -> None:
    docs_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    service = sys.argv[2] if len(sys.argv) > 2 else ""
    source_path = sys.argv[3] if len(sys.argv) > 3 else ""
    root = str(find_docs_root(docs_arg))
    source_root = str((Path(root) / (source_path or service)).resolve())
    features_root = str(Path(root) / "docs" / "features" / service) if service else ""

    # A whole-tree build ("" service) has no single app to boot — skip cleanly.
    if not service:
        emit(is_webapp="no", repo_root=root, source_root=source_root)

    scope = f"docs/features/{service}/"

    # 1) Web-app iff the book documents at least one `screen` surface for this service.
    screens = [s for s in _search(root, "screen") if scope in s.get("path", "")]
    if not screens:
        emit(is_webapp="no", repo_root=root, source_root=source_root, features_root=features_root)

    # 2) Prefer the explicit runtime contract on the server node. It is both documentation
    #    and the executable launch interface consumed by this walkthrough.
    contract: dict[str, str] = {}
    for srv in _search(root, "server"):
        if scope not in srv.get("path", ""):
            continue
        contract = parse_launch_contract(_read(root, srv["path"]), root, source_path or service)
        if contract:
            break

    # Compatibility fallback for older books that only document a Python-style `serve`
    # command. New/updated books should always use the explicit server contract above.
    port, cmd_name = FALLBACK_PORT, service
    if contract:
        launch_cmd = contract["launch_cmd"]
        entry_url = contract["entry_url"]
        health_path = contract["health_path"]
        app_cwd = contract["app_cwd"]
        app_identity = contract["app_identity"]
    else:
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
         wt_worklist_path=str(wl), screenshots_dir=str(shots), round=0)


if __name__ == "__main__":
    main()
