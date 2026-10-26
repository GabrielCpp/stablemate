"""Git helpers and a scripted agent keyed by prompt."""
from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import override

from workhorse.context import WorkflowContext
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

FIX_COMMIT_NODE = "fix-refused-commit"

Reply = Callable[[dict[str, object]], dict[str, object]]

def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout


class ScriptedRunner(AgentRunner):
    """Answers each turn with the reply scripted for its prompt, and keeps every turn's arguments.

    A reply the turn's validator refuses is asked for once more, with the refusal under `refused` in its arguments, as the ladder asks again.
    A turn sent to a refused commit that no test scripts changes nothing, so the refusal reaches the operator, and counts in no turn.
    """

    def __init__(self, replies: Mapping[str, Reply]) -> None:
        super().__init__(backend=NullBackend())
        self.replies: dict[str, Reply] = dict(replies)
        self.turns: Counter[str] = Counter()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.nodes: list[AgentNode] = []
        self.refused: list[tuple[str, str]] = []
        self.chains: list[tuple[str, str]] = []
        self.resumed: list[bool] = []

    @property
    def total(self) -> int:
        return sum(self.turns.values())

    def args_of(self, node: str) -> list[dict[str, object]]:
        return [args for name, args in self.calls if name == node]

    @override
    def run(
        self,
        node: AgentNode,
        context: WorkflowContext,
        workflow_dir: Path,
        session_id_path: Path | None = None,
        *,
        resume_session: bool = False,
        session_chain: str = "",
        run_dir: Path | None = None,
        visit_dir: Path | None = None,
        validate: Callable[[dict[str, object]], object] | None = None,
        rebrief: Callable[[], str] | None = None,
    ) -> tuple[str, dict[str, object]]:
        args = context.as_dict()
        if node.id == FIX_COMMIT_NODE and node.id not in self.replies:
            return "scripted", {"fixed": ""}
        self.turns[node.id] += 1
        self.calls.append((node.id, args))
        self.nodes.append(node)
        self.chains.append((node.id, session_chain))
        if session_chain and session_id_path is not None:
            self.resumed.append(session_id_path.exists())
            session_id_path.parent.mkdir(parents=True, exist_ok=True)
            _ = session_id_path.write_text(f"session-{self.total}", encoding="utf-8")
        reply = self.replies[node.id](args)
        if validate is None:
            return "scripted", reply
        try:
            _ = validate(reply)
        except ValueError as refusal:
            self.refused.append((node.id, str(refusal)))
            reply = self.replies[node.id]({**args, "refused": str(refusal)})
            _ = validate(reply)
        return "scripted", reply


MEMBER = "api-service"
MEMBER_FOLDER = "api"
MEMBER_FILE = "api/handlers.py"
MEMBER_SOURCE = "def list_entries():\n    return []\n"


@dataclass(frozen=True, slots=True)
class Workspace:
    """A two-repo workspace: the docs home that holds the books, and a product member that holds the source."""

    docs: Path
    member: Path


def head_of(repo: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def status_of(repo: Path) -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True).stdout


SERVICE = "ledger"
BOOK = f"docs/services/{SERVICE}"
CITED = f"repo://{MEMBER}/{MEMBER_FILE}::list_entries"

BRING_UP_MARKER = ".bring-up-cwd"
SERVER = """import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from api.handlers import list_entries


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"count": len(list_entries())}).encode() if self.path == "/entries" else b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return None


HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
"""


def ledger_pages(port: int) -> dict[str, str]:
    return {
        "index.md": "---\n---\n# Ledger\n",
        "entries.md": (
            "---\ntype: entries\ntitle: Ledger\n---\n# Ledger\n\n- [Ledger API](ledger-api.md)\n"
            "- [Read entries](flows/read-entries.md)\n- [QA stack](ops/qa-stack.md)\n"
        ),
        "ledger-api.md": (
            f"---\ntype: server\nslug: ledger-api\ntitle: Ledger API\n---\n# Ledger API\n\n- code: `{CITED}`\n\n"
            "## Endpoints\n\n- [list-entries](list-entries.md)\n"
        ),
        "list-entries.md": (
            "---\ntype: endpoint\nslug: list-entries\ntitle: list-entries\n---\n# list-entries\n\n"
            f"- server: [Ledger API](ledger-api.md)\n- method: GET\n- path: /entries\n- does: lists the entries\n"
            f"- fixture: none, because the route lists whatever is there\n- verify: http_status(code=200)\n- verify: json_path(path=\"$.count\", equals=0)\n- code: {CITED}\n"
        ),
        "flows/read-entries.md": (
            "---\ntype: flow\nslug: read-entries\ntitle: Read entries\n---\n# Read entries\n\n"
            "- fixture: none, because the route lists whatever is there\n- steps:\n  - [list-entries](../list-entries.md)\n"
        ),
        "ops/qa-stack.md": (
            "---\ntype: runbook\nslug: qa-stack\ntitle: QA stack\n---\n# QA stack\n\n"
            f"- driver: http\n- surfaces: [Ledger API](../ledger-api.md)\n- entry-url: http://127.0.0.1:{port}\n- health-path: /healthz\n\n"
            "## Steps\n\n### prepare\n\n- kind: prepare\n"
            f"- run: pwd > {BRING_UP_MARKER}\n- working-directory: repo://{MEMBER}/.\n\n"
            f"### serve\n\n- kind: service\n- run: python3 -B serve.py {port}\n- working-directory: repo://{MEMBER}/.\n"
            f"- health: curl -fsS http://127.0.0.1:{port}/healthz\n"
        ),
    }
