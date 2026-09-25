"""Paddock fixture apps, git helpers, a scripted agent keyed by prompt, and flows cut short at a phase."""
from __future__ import annotations

import subprocess
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import override

from pydantic import BaseModel, ConfigDict, TypeAdapter
from workhorse.context import WorkflowContext
from workhorse.pyflow import Continue, Done
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

from workhorse_workflows.okf_book.aggregate.verdict import NumberedContract
from workhorse_workflows.okf_book.main.nodes.surface import EntryPoint, EntryPointListing
from workhorse_workflows.okf_book.shared.entries import services
from workhorse_workflows.okf_book.shared.work import DONE, FILE, ORPHAN, ids
from workhorse_workflows.okf_book.workflow import OkfBook

driver: Callable[[OkfBook, RunEnv], object] = drive

APPS = Path(__file__).resolve().parents[3] / "paddock" / "data" / "apps"
LIST_NODE = "list-entry-points"

Reply = Callable[[dict[str, object]], dict[str, object]]
BRIEFS = TypeAdapter(list[dict[str, object]])
NUMBERED = TypeAdapter(list[NumberedContract])


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout


def commits(repo: Path) -> list[str]:
    """Every commit subject, newest first."""
    return git(repo, "log", "--format=%s").splitlines()


def listing(*slugs: str) -> EntryPointListing:
    return EntryPointListing(entry_points=tuple(EntryPoint(slug=s, title=s.title()) for s in slugs))


def drafted(summary: str, *pages: tuple[str, str]) -> dict[str, object]:
    """A page writer's reply: its summary, then each page's path and whole text between marker lines."""
    blocks = "".join(f"=== page: {path} ===\n{text}=== end ===\n" for path, text in pages)
    return {"value": f"{summary}\n{blocks}"}


def always(payload: dict[str, object]) -> Reply:
    """A reply that ignores the turn's arguments."""

    def _reply(_args: dict[str, object]) -> dict[str, object]:
        return payload

    return _reply


def judged(*problems: str, node: str = "") -> Reply:
    """A verify-page reply that finds every claim it is handed stated at `#here` on the first page it reads, and names `problems` on `node` beside them, or on that same anchor."""

    def _reply(args: dict[str, object]) -> dict[str, object]:
        numbers = [claim.id for contract in NUMBERED.validate_python(args["contracts"]) for claim in contract.claims]
        stated = f"{BRIEFS.validate_python(args['pages'])[0]['page']}#here"
        found = [{"node": node or stated, "problem": problem} for problem in problems]
        return {"claims": [{"claim": number, "node": stated} for number in numbers], "problems": found}

    return _reply


def promised_contracts(args: dict[str, object]) -> dict[str, object]:
    """A document-files reply that promises one thing for each file it is handed."""
    return {"contracts": [
        {"file": brief["file"], "purpose": "It runs part of tally.", "promises": [{"text": "It works."}]}
        for brief in BRIEFS.validate_python(args["files"])
    ]}


class ScriptedRunner(AgentRunner):
    """Answers each turn with the reply scripted for its prompt, and keeps every turn's arguments.

    A reply the turn's validator refuses is asked for once more, with the refusal under `refused` in its arguments, as the ladder asks again.
    """

    def __init__(self, replies: Mapping[str, Reply]) -> None:
        super().__init__(backend=NullBackend())
        self.replies: dict[str, Reply] = dict(replies)
        self.turns: Counter[str] = Counter()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.nodes: list[AgentNode] = []
        self.refused: list[tuple[str, str]] = []

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
    ) -> tuple[str, dict[str, object]]:
        self.turns[node.id] += 1
        args = context.as_dict()
        self.calls.append((node.id, args))
        self.nodes.append(node)
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


def listing_runner(*slugs: str, **replies: Reply) -> ScriptedRunner:
    """A runner whose listing turn names `slugs`, with the other prompts' replies keyed by stem."""
    found = listing(*slugs)
    payload: dict[str, object] = {"entry_points": [p.model_dump() for p in found.entry_points]}
    return ScriptedRunner({LIST_NODE: always(payload), **{k.replace("_", "-"): v for k, v in replies.items()}})


class WorkListView(BaseModel):
    """What the run's work list holds when a phase under test is over."""

    model_config = ConfigDict(frozen=True)

    services: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    pruned: tuple[str, ...] = ()


def work_list_view(flow: OkfBook, services: tuple[str, ...]) -> WorkListView:
    return WorkListView(services=services, files=ids(flow.work, FILE), pruned=ids(flow.work, ORPHAN, DONE))


class EnumerateOnly(OkfBook):
    """Phase 1 alone: the run ends on the seeded work list."""

    @override
    def document(self, services: tuple[str, ...]) -> Continue[...]:
        return Continue(None, self.stop, services=services)

    def stop(self, services: tuple[str, ...]) -> Done:
        """The phase under test is over."""
        return Done(work_list_view(self, services))


class DocumentOnly(OkfBook):
    """Phases 1 and 2's document turns: the run ends before any page is written."""

    @override
    def aggregate(self, services: tuple[str, ...]) -> Continue[...]:
        return Continue(None, self.stop, services=services)

    def stop(self, services: tuple[str, ...]) -> Done:
        """The phase under test is over."""
        return Done(work_list_view(self, services))


class WriteOnly(OkfBook):
    """Phases 1 and 2: the run ends before the stack is brought up."""

    @override
    def exercise(self, services: tuple[str, ...]) -> Continue[...]:
        return Continue(None, self.stop, services=services)

    def stop(self, services: tuple[str, ...]) -> Done:
        """The phase under test is over."""
        return Done(work_list_view(self, services))


class ExerciseOnly(OkfBook):
    """Phase 3 alone, over the book already in the repo."""

    @override
    def start(self) -> Continue[...]:
        return Continue(None, self.exercise, services=services(self.root))
