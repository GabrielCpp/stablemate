"""Drain the coder's own backlog, one filed item at a time, each through one owner turn."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.shared.backlog import (
    prune_fix_item,
    seed_fix_story,
    select_fix_item,
)
from workhorse_workflows.coder.shared.conversation import story_chain
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.shared.provenance import changed_files
from workhorse_workflows.coder.shared.service_gates import GATE_ORDER, run_gate
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.failure import from_gate
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    MAX_LAPS,
    SILENCE_S,
    UNBOUNDED,
    owner_profile,
)
from workhorse_workflows.coder.shared.resolution import RESOLVER_POWER, answered, resolver_args
from workhorse_workflows.coder.shared.story_commit import commit_story
from workhorse_workflows.coder.shared.story import (
    guard_story_file,
    prepare_fix_story,
    resolve_workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas.dev import (
    FailureReport,
    ImplResult,
    OperatorResolution,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs


def render_gate(report: FailureReport) -> str:
    """One failing gate, as the owner prompt's `report` section reads it."""
    return (
        f"The `{report.source}` gate failed in `{report.cwd}`.\n\n"
        f"Command: `{report.command}`\n\n"
        f"```\n{report.output}\n```"
    )


class Fix(Workflow):
    """Drain the backlog's `Filed by coder` items, each as a one-AC story, each committed."""

    docs_path: str = ""
    workspace_file: str = ""
    target_env: str = "local"
    operator_mode: str = "auto"

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> WorkspaceDirs:
        """Every directory an agent turn in this run may read."""
        return self.call(resolve_workspace_dirs, self.docs_path)

    def start(self) -> Continue | Done:
        """Draw the next drainable bullet, seed it as a story, and resolve its paths."""
        pick = self.call(select_fix_item, self.docs_path)
        if not pick.has_fix:
            self.logger.info("backlog drained: %s", pick.reason)
            return Done(pick)
        self.logger.info("draining %s: %s", pick.fix_bullet_id, pick.fix_bullet_text)
        seed = self.call(
            seed_fix_story, pick.fix_bullet_id, pick.fix_bullet_text, "", "", self.docs_path
        )
        story = self.call(prepare_fix_story, self.docs_path, seed.story_slug, seed.epic)
        guard_story_file(story)
        return Continue(story, self.work)

    def work(
        self,
        operator_context: str = "",
        report: str = "",
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """The owner turn: its subagents fix the item and QA it, in the item's one session."""
        self.logger.info(
            "owning %s (lap %d)", self._story.story_slug, laps + 1, extra={"activity": True}
        )
        turn = roles.turn(self, "fix-item", returns=ImplResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("fix"),
            session=story_chain(self._story.story_slug),
            add_dirs=self._dirs(),
            args=turn.args
            | self._story_args()
            | {
                "bullet_text": self.output(select_fix_item).fix_bullet_text,
                "qa_dir": self._story.qa_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
                "operator_context": operator_context,
                "report": report,
            },
        )
        if result.blocked:
            return self._block(result, result.notes, "the fix owner turn", blocks)
        return Continue(result, self.check, laps=laps, blocks=blocks)

    def check(self, laps: int = 0, blocks: int = 0) -> Continue | Await:
        """Run the repo's own gates over what the turn changed, and send what failed back."""
        failures = self._gate_failures(laps)
        if not failures:
            self.logger.info("gates are clean for %s", self._story.story_slug)
            bullet = self.output(select_fix_item).fix_bullet_id
            pruned = self.call(prune_fix_item, bullet, self.docs_path)
            return Continue(pruned, self.document)
        text = "\n\n".join(render_gate(f) for f in failures)
        if laps >= MAX_LAPS:
            notes = f"{text}\n\nThe gates still fail after {laps} repair turn(s)."
            return self._block(failures[0], notes, "the gates on the fix-drain item", blocks)
        return Continue(failures[0], self.work, report=text, laps=laps + 1, blocks=blocks)

    def document(self) -> Continue:
        """Fold the drained item into the OKF book, by handing off to the `docs` flow."""
        seed = self.output(seed_fix_story)
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=seed.epic,
            target_env=self.target_env,
        )
        if result.status not in ("passed", "not_applicable"):
            raise WorkflowFailed(
                f"documenting the drained fix {self._story.story_slug!r} failed: "
                f"{result.notes or 'no notes'}"
            )
        return Continue(result, self.commit)

    def commit(self) -> Continue:
        """Commit this one item onto the current branch, then draw the next."""
        seed = self.output(seed_fix_story)
        result = self.call(
            commit_story,
            seed.epic,
            self._story.story_slug,
            self._story.spec_dir,
            kind="fix",
            roots=self._changed_dirs(),
            story_id=self._story.story_id,
        )
        return Continue(result, self.start)

    def resolve(self, notes: str, where: str, blocks: int = 0) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args=resolver_args(
                self,
                block_kind="implementation",
                notes=notes,
                docs_path=self.docs_path,
                story=self._story,
            ),
        )
        if answered(self, result, "implementation"):
            return Continue(result, self.read_operator, blocks=blocks + 1)
        return self._ask(notes, where, blocks, result)

    def read_operator(self, blocks: int = 0) -> Continue:
        """Resume the owner's session with the answer in hand."""
        answer = self.call(read_operator_context, self._story.story_path)
        return Continue(answer, self.work, operator_context=answer.content, blocks=blocks)

    def _block(self, result: object, notes: str, where: str, blocks: int) -> Continue | Await:
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks)
        return Continue(result, self.resolve, notes=notes, where=where, blocks=blocks)

    def _ask(
        self, notes: str, where: str, blocks: int, result: OperatorResolution | None = None
    ) -> Await:
        gate = escalation(
            self,
            block_kind="implementation",
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
            story=self._story,
        )
        return Await(
            context_path(self, self._story.story_path),
            gate.body,
            self.read_operator,
            blocks=blocks + 1,
        )

    def _gate_failures(self, laps: int) -> list[FailureReport]:
        """The first red gate of each changed repository."""
        failures: list[FailureReport] = []
        for repo_dir in self._changed_dirs():
            for gate in GATE_ORDER:
                outcome = self.call(run_gate, repo_dir, "", gate)
                if outcome.status == "dirty":
                    failures.append(from_gate(outcome, repo_dir, laps + 1))
                    break
        return failures

    def _story_args(self) -> dict[str, Any]:
        return {
            "story_slug": self._story.story_slug,
            "story_id": self._story.story_id or self._story.story_slug,
            "epic": self._story.story_epic,
            "story_path": self._story.story_path,
            "spec_dir": self._story.spec_dir,
        }

    def _changed_dirs(self) -> list[str]:
        """The run's repositories that are holding work for this item, git's account of it."""
        return [
            d
            for d in self._dirs()
            if self.call(changed_files, d, self._story.story_slug, self._story.story_id).paths
        ]

    @property
    def _story(self) -> StoryPaths:
        """The story this iteration is draining, as `prepare_fix_story` resolved it."""
        return self.output(prepare_fix_story)

    def _dirs(self) -> list[str]:
        """The `add_dirs` every agent turn in this flow is given."""
        return list(self.ctx.dirs)


__all__ = ["Fix", "render_gate"]
