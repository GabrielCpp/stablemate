#!/usr/bin/env python3
"""Read-only status board over the file model (no service, no DB) — ostler-backed.

The author/coder workflows keep all durable state in git-tracked OKF markdown: the epic queue
(``docs/epics/index.md``), each epic's story dependency-DAG folded into its ``epic.md``
(``## Stories``), each story's ``story.md`` ``- **Status**:`` line, and the open backlog. This is
a pure projection of those files into a human board — the "Jira for agents" view, file-native: it
starts no daemon, exposes no API, and writes nothing. It reads the graph through ``ostler``
(``todo list`` / ``list --type story`` / ``backlog list``).

Status columns are derived from each story's status (what the coder updates): ``QA passed`` ⇒
done; anything else non-empty ⇒ in progress; missing/``Not started`` ⇒ not started. An epic listed
in the queue with no stories yet is shown as *not authored*.

Stdlib-only except for shelling out to the globally-installed ``ostler`` CLI. Honours
``AGENT_REPO_DIR`` like the workflow scripts, so it can be invoked from anywhere (e.g. a
``make agent-status`` target).

Usage:
    board.py [--epics-dir docs/epics] [--backlog docs/backlog.md] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def ostler_json(root: Path, args: list[str], opener: str):
    ostler = shutil.which("ostler")
    if not ostler:
        return None
    try:
        proc = subprocess.run([ostler, *args], cwd=str(root), capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (proc.stdout or "").strip()
    start = raw.find(opener)
    if start == -1:
        return [] if opener == "[" else None
    try:
        return json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None


def classify(status: str) -> str:
    s = (status or "").lower()
    if not s or s.startswith("not started"):
        return "not_started"
    if s.startswith("qa passed"):
        return "done"
    return "in_progress"


def collect(root: Path, epics_dir_rel: str, backlog_rel: str) -> dict:
    queue = ostler_json(root, ["todo", "list", "--json"], "[") or []
    queue = [str(x) for x in queue]

    by_epic: dict[str, list[dict]] = {}
    for st in ostler_json(root, ["list", "--type", "story", "--json"], "[") or []:
        by_epic.setdefault(str(st.get("epic", "")), []).append(st)

    epics = []
    for slug in queue:
        rows = by_epic.get(slug, [])
        if not rows:
            epics.append({"epic": slug, "authored": False, "stories": []})
            continue
        stories = [{
            "slug": str(st.get("slug", "")),
            "status": str(st.get("status", "")),
            "state": classify(str(st.get("status", ""))),
        } for st in rows]
        epics.append({"epic": slug, "authored": True, "stories": stories})

    all_stories = [s for e in epics for s in e["stories"]]
    counts = {k: sum(1 for s in all_stories if s["state"] == k)
              for k in ("done", "in_progress", "not_started")}

    backlog = ostler_json(root, ["backlog", "list", "--json"], "[")
    backlog_open = len(backlog) if isinstance(backlog, list) else 0

    return {
        "repo": str(root),
        "epics": epics,
        "totals": {"stories": len(all_stories), **counts, "backlog_open": backlog_open},
    }


GLYPH = {"done": "✓", "in_progress": "•", "not_started": "○"}


def render_text(board: dict) -> str:
    out = [f"Board: {board['repo']}", ""]
    if not board["epics"]:
        out.append("(no epics queued — run the author workflow to populate docs/epics)")
    for e in board["epics"]:
        if not e["authored"]:
            out.append(f"{e['epic']}  (not yet authored)")
            continue
        done = sum(1 for s in e["stories"] if s["state"] == "done")
        out.append(f"{e['epic']}  [{done}/{len(e['stories'])} done]")
        for s in e["stories"]:
            out.append(f"  {GLYPH[s['state']]} {s['slug']:<40} {s['status'] or 'Not started'}")
        out.append("")
    t = board["totals"]
    out.append(
        f"Summary: {t['stories']} stories  |  {t['done']} done  |  "
        f"{t['in_progress']} in progress  |  {t['not_started']} not started  |  "
        f"backlog: {t['backlog_open']} open"
    )
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only status board over the author/coder file model.")
    ap.add_argument("--epics-dir", default="docs/epics")
    ap.add_argument("--backlog", default="docs/backlog.md")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the text board")
    args = ap.parse_args()

    board = collect(find_repo_root(), args.epics_dir, args.backlog)
    print(json.dumps(board, indent=2) if args.json else render_text(board))


if __name__ == "__main__":
    main()
