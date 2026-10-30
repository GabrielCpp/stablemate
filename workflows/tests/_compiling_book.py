"""A small book and the QA context packet ostler's own producer derives from it."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ostler import index
from ostler.qa.context import book_context

BOOK = "docs/services/ledger"
LIST_ENTRIES = f"{BOOK}/list-entries.md"
CITED = "api/handlers.py::list_entries"

PAGES = {
    "index.md": "---\n---\n# Ledger\n",
    "entries.md": (
        "---\ntype: entries\ntitle: Ledger\n---\n# Ledger\n\n- [Ledger API](ledger-api.md)\n"
        "- [QA stack](ops/qa-stack.md)\n"
    ),
    "ledger-api.md": (
        f"---\ntype: server\nslug: ledger-api\ntitle: Ledger API\n---\n# Ledger API\n\n- code: `{CITED}`\n\n"
        "## Endpoints\n\n- [list-entries](list-entries.md)\n"
    ),
    "list-entries.md": (
        "---\ntype: endpoint\nslug: list-entries\ntitle: list-entries\n---\n# list-entries\n\n"
        "- server: [Ledger API](ledger-api.md)\n- method: GET\n- path: /entries\n"
        "- does: lists the entries\n- fixture: none, because the route lists whatever is there\n"
        f"- verify: http_status(code=200)\n- verify: json_path(path=\"$.count\", equals=0)\n- code: {CITED}\n"
    ),
    "ops/qa-stack.md": (
        "---\ntype: runbook\nslug: qa-stack\ntitle: QA stack\n---\n# QA stack\n\n"
        "- driver: http\n- surfaces: [Ledger API](../ledger-api.md)\n- entry-url: http://127.0.0.1:18080\n"
        "- health-path: /healthz\n\n## Steps\n\n### serve\n\n- kind: service\n"
        "- run: python3 -B serve.py 18080\n- health: curl -fsS http://127.0.0.1:18080/healthz\n"
    ),
}


def write_packet(root: Path, spec: Path, *, runbook: bool) -> None:
    """Write the book under `root`, and the packet the producer derives from it into `spec`."""
    _ = subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "api").mkdir(parents=True, exist_ok=True)
    _ = (root / "api" / "handlers.py").write_text("def list_entries():\n    return []\n", encoding="utf-8")
    for name, text in PAGES.items():
        if name == "ops/qa-stack.md" and not runbook:
            continue
        page = root / BOOK / name
        page.parent.mkdir(parents=True, exist_ok=True)
        _ = page.write_text(text, encoding="utf-8")
    with index.session(root):
        packet = book_context(
            root, source_roots={"ledger": ["api/handlers.py"]}, repositories=(), books=[BOOK]
        )
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "qa-okf-context.json").write_text(json.dumps(packet), encoding="utf-8")
