"""One service's Python book written by one owner turn per lap: the turn writes `services/<service>/`, the run judges it with the book's own check and run, and a green book is committed."""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done, Transition, dry_run
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.kit.answer import answer_below
from workhorse_workflows.kit.tools import run_tool
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.metrics import record_turn, turn_metric

WRITE_PROMPT = "main/prompts/write-python-book.md"
MAX_LAPS = 3
GATE_TAIL_LINES = 200
ANSWER_LIMIT_CHARS = 8000
RED_GATE = "python-book-red.md"
BLOCKED_GATE = "python-book-blocked.md"
ENVIRONMENT_GATE = "python-book-environment.md"
COULD_NOT_JUDGE = 3


class BookGate(BaseModel):
    """What one of the book's own commands said: its exit code and the tail of its output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    output: str = ""


class PythonBookReply(BaseModel):
    """What the owner's turn says it did, or what stopped it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    done: str = ""
    blocked: str = ""


class PythonBookOutcome(BaseModel):
    """The book the run committed, and how many laps it took."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    laps: int


def book_module(service: str) -> str:
    return f"services.{service}"


def book_command(*verb: str) -> list[str]:
    return [sys.executable, "-m", "ostler.book", *verb]


def _green(_logger: logging.Logger, *_args: object) -> BookGate:
    return BookGate(exit_code=0, output="dry run")


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-GATE_TAIL_LINES:])


@blueprint.node(stub=_green)
def python_book_check(logger: logging.Logger, root: Path, service: str) -> BookGate:
    """Run the book's check from the repo root, and keep the tail of what it printed."""
    done = run_tool(book_command("check", book_module(service)), cwd=root, logger=logger)
    return BookGate(exit_code=done.returncode, output=_tail(f"{done.stdout}\n{done.stderr}".strip()))


@blueprint.node(stub=_green)
def python_book_run(logger: logging.Logger, root: Path, service: str, out_dir: Path) -> BookGate:
    """Play the book against the live app from the repo root, and keep the tail of what it printed."""
    done = run_tool(book_command("run", book_module(service), "--out", str(out_dir)), cwd=root, logger=logger)
    return BookGate(exit_code=done.returncode, output=_tail(f"{done.stdout}\n{done.stderr}".strip()))


def owner_chain(service: str) -> str:
    return f"pybook:{service}"


@dry_run(service="dry-run")
class WritePythonBook(BookFlow):
    """Sends a service's book owner until the book's check and run both pass, then commits the book's package."""

    service: str = ""
    kind: str = "cli"
    source_folder: str = ""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def package(self) -> str:
        return f"services/{self.service}"

    def start(self) -> Continue[...]:
        """Send the owner its first lap."""
        return Continue(None, self.write, gate="", lap=1).because("send the owner")

    def write(self, gate: str, lap: int) -> Continue[...] | Await[...]:
        """One owner turn writes the book's package until its check and run pass, opening on what the last gate printed. A turn that ends without a reply starts the next one fresh, and the gates judge what it left."""
        started = time.monotonic()
        reply = PythonBookReply()
        try:
            reply = self.agent(
                WRITE_PROMPT,
                returns=PythonBookReply,
                power="high",
                timeout=float("inf"),
                args=self._prompt_args(gate),
                cwd=self.root,
                session=owner_chain(self.service),
            )
        except (OutputParseError, AgentTurnFailed, AgentTimeout) as ended:
            self.logger.warning("the owner's turn on %s ended without a reply: %s", self.service, ended)
            self.reset_session(owner_chain(self.service))
        node = Path(WRITE_PROMPT).stem
        record_turn(self.records_dir, turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node)))
        if reply.blocked:
            question = f"The owner of the {self.service} book stopped:\n\n{reply.blocked}\n\nAnswer here, and the owner reads your answer on its next turn."
            return Await(self.run_dir / BLOCKED_GATE, question, self.heard, question=question, gate_name=BLOCKED_GATE, lap=lap).because(
                "the owner is blocked"
            )
        return Continue(reply, self.check, lap=lap).because("check the book")

    def _prompt_args(self, gate: str) -> dict[str, object]:
        return {
            "service": self.service,
            "kind": self.kind,
            "package": self.package,
            "book_module": book_module(self.service),
            "source_folder": self.source_folder,
            "repo_root": self.root.as_posix(),
            "check": f"python -m ostler.book check {book_module(self.service)}",
            "run": f"python -m ostler.book run {book_module(self.service)}",
            "gate": gate,
        }

    def heard(self, question: str, gate_name: str, lap: int) -> Continue[...]:
        """Hand the operator's answer to the owner's next turn."""
        text = (self.run_dir / gate_name).read_text(encoding="utf-8") if (self.run_dir / gate_name).is_file() else ""
        said = answer_below(text, question, ANSWER_LIMIT_CHARS)
        gate = f"{question}\n\nThe operator answered:\n\n{said}" if said else question
        return Continue(said, self.write, gate=gate, lap=lap).because("the operator answered")

    def check(self, lap: int) -> Continue[...] | Await[...]:
        """Run the book's check. A pass plays the book, and a fail sends the owner another lap."""
        gate = self.call(python_book_check, self.root, self.service)
        if gate.exit_code == 0:
            return Continue(gate, self.play, lap=lap).because("the check passes")
        return self._judged("check", gate, lap, self.check)

    def play(self, lap: int) -> Continue[...] | Await[...]:
        """Play the book against the live app. A pass commits the book, and a fail sends the owner another lap."""
        gate = self.call(python_book_run, self.root, self.service, self.run_dir / "book-run")
        if gate.exit_code == 0:
            return Continue(gate, self.render, lap=lap).because("the book plays green")
        return self._judged("run", gate, lap, self.play)

    def _judged(self, verb: str, gate: BookGate, lap: int, retry: Callable[..., Transition]) -> Continue[...] | Await[...]:
        said = f"`python -m ostler.book {verb} {book_module(self.service)}` exited {gate.exit_code}:\n\n{gate.output}"
        if gate.exit_code == COULD_NOT_JUDGE:
            question = f"The book's {verb} could not judge the {self.service} book, which is the environment's side:\n\n{said}\n\nFix the environment, then answer here to {verb} again."
            return Await(self.run_dir / ENVIRONMENT_GATE, question, retry, lap=lap).because("the book could not be judged")
        if lap >= MAX_LAPS:
            question = f"The {self.service} book is still red after {lap} laps:\n\n{said}\n\nAnswer here, and the owner takes one more lap with your answer."
            return Await(self.run_dir / RED_GATE, question, self.heard, question=question, gate_name=RED_GATE, lap=lap).because(
                "the book is still red after the last lap"
            )
        return Continue(said, self.write, gate=said, lap=lap + 1).because("the book is red")

    def render(self, lap: int) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the book is committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render, lap=lap)
        if waiting:
            return waiting
        return Continue(lap, self.commit, lap=lap).because("commit the book")

    def commit(self, lap: int) -> Done | Await[...]:
        """Commit the book's package. A retry after the commit landed finds nothing to commit."""
        waiting = self._commit_or_await(book_commit_subject(self.service), (self.package,), self.commit, lap=lap)
        if waiting:
            return waiting
        return Done(PythonBookOutcome(service=self.service, laps=lap)).because("the book is committed")
