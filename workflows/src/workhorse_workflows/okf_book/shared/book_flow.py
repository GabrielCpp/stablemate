"""The base every okf-book machine sits on: the repo it writes, the folder its records go in, and how it commits a book."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Transition, Workflow
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.kit import commit_returning_refusal
from workhorse_workflows.kit.answer import answer_below
from workhorse_workflows.kit.paths import find_book_root
from workhorse_workflows.kit.agent_files import render_agent_files_returning_failure
from workhorse_workflows.kit.commit_checks import declared_checks_failure
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.metrics import record_turn, turn_metric

COMMIT_GATE = "commit-refused.md"
RENDER_GATE = "agent-files-unrendered.md"
PREFLIGHT_GATE = "preflight-gate.md"
FIX_COMMIT_TIMEOUT = 1800.0
FIX_COMMIT_TURNS = 4
RED_GATE = "python-book-red.md"
BLOCKED_GATE = "python-book-blocked.md"
ENVIRONMENT_GATE = "python-book-environment.md"
DECISIONS_GATE = "python-book-decisions.md"
SKELETON_GATE = "python-book-skeleton.md"
REASONS_GATE = "python-book-reasons.md"
FORMAT_GATE = "python-book-format.md"
ANSWER_LIMIT_CHARS = 8000
MAX_LAPS = 3
COULD_NOT_JUDGE = 3


def blocked_question(service: str, blocked: str) -> str:
    return f"The owner of the {service} book stopped:\n\n{blocked}\n\nAnswer here, and the owner reads your answer on its next turn."


def red_question(service: str, lap: int, said: str) -> str:
    return f"The {service} book is still red after {lap} laps:\n\n{said}\n\nAnswer here, and the owner takes one more lap with your answer."


def environment_question(service: str, verb: str, said: str) -> str:
    return f"The book's {verb} could not judge the {service} book, which is the environment's side:\n\n{said}\n\nFix the environment, then answer here to {verb} again."


def format_question(service: str, said: str) -> str:
    return f"What the book format changed could not be read for the {service} book:\n\n{said}\n\nFix what it names, then answer here to read it again."


def decisions_question(service: str, said: str) -> str:
    return f"The {service} book's decisions could not be listed, so the screens no decision names are unknown:\n\n{said}\n\nFix it, then answer here to list them again."


def no_reply_question(service: str, what: str, items: list[str]) -> str:
    listed = "\n".join(f"- {item}" for item in items)
    return f"A turn writing the {what} of the {service} book ended without a reply. Its batch:\n\n{listed}\n\nAnswer here, and the same batch goes to a new turn with your answer."


def _nothing_refused_in_dry_run(_logger: logging.Logger, *_args: object) -> str:
    return ""


@blueprint.node(stub=_nothing_refused_in_dry_run)
def render_book_agent_files(logger: logging.Logger, root: Path) -> str:
    """Render the repo's agent files, and return why they could not be. A dry run renders nothing."""
    del logger
    return render_agent_files_returning_failure(root)


@blueprint.node(stub=_nothing_refused_in_dry_run)
def commit_book_paths(logger: logging.Logger, root: Path, message: str, pathspecs: tuple[str, ...]) -> str:
    """Commit exactly *pathspecs*, and return what a declared commit check or git said when it refused. A dry run commits nothing."""
    del logger
    return declared_checks_failure(root, message, pathspecs) or commit_returning_refusal(root, message, *pathspecs)


class CommitFix(BaseModel):
    """What the turn sent to a refused commit says it changed, or why it changed nothing."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    fixed: str = ""
    blocked: str = ""


class BookFlow(Workflow):
    """The base each machine's states sit on. A handed-off machine keeps its records in the folder of the run that started it."""

    parent_records_dir: str = ""

    @property
    def root(self) -> Path:
        return find_book_root(self.repo_dir)

    @property
    def records_dir(self) -> Path:
        return Path(self.parent_records_dir) if self.parent_records_dir else self.run_dir

    @property
    def code_root(self) -> Path:
        return Path(self.repo_dir).resolve()

    def _owner_gate(self, question: str, gate_name: str) -> str:
        """What the owner's next prompt opens on after an operator gate: the question, then the operator's answer when there is one."""
        path = self.run_dir / gate_name
        said = answer_below(path.read_text(encoding="utf-8") if path.is_file() else "", question, ANSWER_LIMIT_CHARS)
        return f"{question}\n\nThe operator answered:\n\n{said}" if said else question

    def _add_dirs(self) -> list[Path] | None:
        return [self.code_root] if self.code_root != self.root else None

    def _timed_turn[M: BaseModel](self, service: str, prompt: str, empty: M, ask: Callable[[], M], session: str | None = None) -> M:
        started = time.monotonic()
        reply = empty
        try:
            reply = ask()
        except (OutputParseError, AgentTurnFailed, AgentTimeout) as ended:
            self.logger.warning("the turn %s on %s ended without a reply: %s", prompt, service, ended)
            if session:
                self.reset_session(session)
        node = Path(prompt).stem
        record_turn(self.records_dir, turn_metric(Phase.WRITE, node, (service,), (time.monotonic() - started) / 60, self.turn_usage(node)))
        return reply

    def _render_agent_files_or_await[**P](self, retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs) -> Await[P] | None:
        """Render the repo's agent files before a book commit, so a skill the library changed does not refuse it. A failed render waits for the operator, whose answer renders again."""
        failure = self.call(render_book_agent_files, self.root)
        if not failure:
            return None
        return Await(
            self.run_dir / RENDER_GATE,
            f"The repo's agent files could not be rendered before the book commit:\n\n{failure}\n\nFix it, then answer here to render them again.",
            retry,
            *args,
            **kwargs,
        ).because("the agent files could not be rendered")

    def _commit_or_await[**P](
        self, message: str, pathspecs: tuple[str, ...], retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs
    ) -> Await[P] | None:
        """Commit exactly *pathspecs*. Each new refusal goes to its own turn that fixes what it names, up to four turns, and the commit is tried again after each. A refusal that repeats one already sent, or one after the last turn, waits for the operator, whose answer commits again."""
        refusal = self.call(commit_book_paths, self.root, message, pathspecs)
        seen: list[str] = []
        said = ""
        while refusal and refusal not in seen and len(seen) < FIX_COMMIT_TURNS:
            seen.append(refusal)
            said = self._fix_refused_commit(refusal, pathspecs)
            refusal = self.call(commit_book_paths, self.root, message, pathspecs)
        if not refusal:
            return None
        return self._await_operator_on_refused_commit(f"{refusal}\n\n{said}" if said else refusal, retry, *args, **kwargs)

    def _fix_refused_commit(self, refusal: str, pathspecs: tuple[str, ...]) -> str:
        """One turn at the repo's root reads the refusal and fixes its cause. Returns what the turn said of it, for the operator a second refusal reaches."""
        try:
            fix = self.agent(
                "shared/prompts/fix-refused-commit.md",
                returns=CommitFix,
                timeout=FIX_COMMIT_TIMEOUT,
                args={"refusal": refusal, "paths": list(pathspecs)},
                cwd=self.root,
            )
        except (AgentTurnFailed, AgentTimeout, OutputParseError) as ended:
            self.logger.warning("the turn sent to a refused commit ended without a reply: %s", ended)
            return ""
        if fix.blocked:
            return f"A turn sent to fix it changed nothing: {fix.blocked}"
        return f"A turn sent to fix it said: {fix.fixed}" if fix.fixed else ""

    def _await_operator_on_refused_commit[**P](self, refusal: str, retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs) -> Await[P]:
        """Stop at the operator when the repo refused a book commit. Their answer tries the same commit again."""
        return Await(
            self.run_dir / COMMIT_GATE,
            f"The repo refused the book commit:\n\n{refusal}\n\nFix what it names in the repo, then answer here to commit again.",
            retry,
            *args,
            **kwargs,
        ).because("the repo refused the commit")
