"""Drain the coder's own backlog, one filed item at a time."""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.shared.backlog import (
    mark_fix_blocked,
    prune_fix_item,
    seed_fix_story,
    select_fix_item,
)
from workhorse_workflows.coder.shared.conversation import story_chain
from workhorse_workflows.coder.shared.dev import (
    GATE_ORDER,
    changed_files,
    plan_summary,
    read_operator_context,
    run_gate,
)
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.failure import from_gate
from workhorse_workflows.coder.shared.queue import commit_story
from workhorse_workflows.coder.shared.story import (
    guard_story_file,
    prepare_fix_story,
    resolve_workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.dev import FailureReport, ImplResult
from workhorse_workflows.coder.shared.schemas.qa import QaRunResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs

BLOCKED_NOTE = "blocked in fix loop (QA still failing after one retry)"

MAX_FIX_LAPS = 3



def render_gate(report: FailureReport) -> str:
    """The failing gate, as the prompt's `gate_report` section reads it."""
    return (
        f"Repair lap {report.lap}: the `{report.source}` gate failed in `{report.cwd}`.\n\n"
        f"Command: `{report.command}`\n\n"
        f"```\n{report.output}\n```"
    )


class Fix(Workflow):
    """Drain the backlog's `Filed by coder` items, each as a one-AC story, each committed."""

    docs_path: str = ""
    workspace_file: str = ""
    target_env: str = "local"

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
        return Continue(story, self.item)

    def item(
        self,
        gate_report: str = "",
        operator_context: str = "",
        impl_blocks: int = 0,
        lap: int = 0,
    ) -> Continue | Await:
        """Plan and write the repair, in one session — and re-enter it for each repair lap."""
        self.logger.info(
            "fixing %s (lap %d)", self._story.story_slug, lap + 1, extra={"activity": True}
        )
        repair = bool(gate_report)
        turn = roles.turn(self, "fix-item-repair" if repair else "fix-item", returns=ImplResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            add_dirs=self._dirs(),
            session=story_chain(self._story.story_slug),
            args=turn.args
            | {
                "story_slug": self._story.story_slug,
                "story_id": self._story.story_id or self._story.story_slug,
                "epic": self._story.story_epic,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "bullet_text": self.output(select_fix_item).fix_bullet_text,
                "operator_context": operator_context,
            }
            | ({"gate_report": gate_report} if repair else {}),
        )
        if result.blocked:
            return self._gate_impl(result, gate_report, impl_blocks, lap)
        return Continue(result, self.gates, lap=lap)

    def gates(self, lap: int = 0, impl_blocks: int = 0) -> Continue | Await:
        """Run the repo's own gates over what the turn changed, and buy a lap when one is red."""
        for repo_dir in self._changed_dirs():
            for gate in GATE_ORDER:
                outcome = self.call(run_gate, repo_dir, "", gate)
                if outcome.status != "dirty":
                    continue
                report = from_gate(outcome, repo_dir, lap + 1)
                if lap + 1 < MAX_FIX_LAPS:
                    return Continue(
                        report,
                        self.item,
                        gate_report=render_gate(report),
                        impl_blocks=impl_blocks,
                        lap=lap + 1,
                    )
                return self._gate_red(report, impl_blocks)
        self.logger.info("gates are clean for %s", self._story.story_slug)
        return Continue(self._story, self.check)

    def read_operator_impl(
        self, gate_report: str = "", impl_blocks: int = 0, lap: int = 0
    ) -> Continue:
        """Consume the operator's answer and re-enter the turn with it in hand."""
        answer = self.call(read_operator_context, self._story.story_path)
        return Continue(
            answer,
            self.item,
            gate_report=gate_report,
            operator_context=answer.content,
            impl_blocks=impl_blocks,
            lap=lap,
        )

    def check(self) -> Continue:
        """QA the fix."""
        result = self._qa()
        if result.status == "passed":
            return self._prune(result)
        return Continue(result, self.apply_once, notes=result.notes)

    def apply_once(self, notes: str = "", impl_blocks: int = 0) -> Continue | Await:
        """The single retry: apply what QA found."""
        self.logger.info("applying QA fixes to the drained item", extra={"activity": True})
        turn = roles.turn(self, "apply-qa-fixes", returns=QaRunResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            add_dirs=self._dirs(),
            session=story_chain(self._story.story_slug),
            args=turn.args | {
                "story_slug": self._story.story_slug,
                "story_id": self._story.story_id or self._story.story_slug,
                "epic": self._story.story_epic,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "qa_dir": self._story.qa_dir,
                "qa_notes": notes,
            },
        )
        if result.status == "blocked":
            return self._gate_impl(result, "", impl_blocks, 0)
        return Continue(result, self.recheck)

    def recheck(self) -> Continue:
        """QA it again, and settle the item either way."""
        result = self._qa()
        if result.status == "passed":
            return self._prune(result)
        return self._flag(result)


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


    def _prune(self, result: CoderResult) -> Continue:
        """The fix shipped, so its bullet leaves the backlog."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.call(prune_fix_item, bullet, self.docs_path)
        return Continue(result, self.document)

    def _flag(self, result: CoderResult) -> Continue:
        """The bullet is annotated in place, and the drain moves on."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.logger.info("flagging %s as blocked", bullet)
        self.call(mark_fix_blocked, bullet, BLOCKED_NOTE, self.docs_path)
        return Continue(result, self.document)

    def _gate_impl(
        self, result: ImplResult | QaRunResult, gate_report: str, impl_blocks: int, lap: int
    ) -> Await:
        """A turn said it could not — park on the story and ask."""
        gate = escalation(
            self,
            block_kind="implementation",
            where="the fix-drain implementation turn",
            notes=result.notes,
            number=impl_blocks + 1,
            findings=result.actionable,
            story=self._story,
        )
        return Await(
            context_path(self, self._story.story_path),
            gate.body,
            self.read_operator_impl,
            gate_report=gate_report,
            impl_blocks=impl_blocks + 1,
            lap=lap,
        )

    def _gate_red(self, report: FailureReport, impl_blocks: int) -> Await:
        """The repair budget is spent and the gate is still red — ask, do not give up."""
        gate = escalation(
            self,
            block_kind="implementation",
            where=f"the {report.source} gate on the fix-drain item",
            notes=(
                f"`{report.command or report.source}` still fails in {report.cwd} after "
                f"{report.lap} repair lap(s).\n\n{report.output}"
            ),
            number=impl_blocks + 1,
            findings=report.actionable,
            story=self._story,
        )
        return Await(
            context_path(self, self._story.story_path),
            gate.body,
            self.read_operator_impl,
            gate_report=render_gate(report),
            impl_blocks=impl_blocks + 1,
            lap=0,
        )

    def _qa(self) -> QaRunResult:
        """`qa-fix-item.md`, which `check` and `recheck` run with identical arguments."""
        self.logger.info("checking %s", self._story.story_slug, extra={"activity": True})
        turn = roles.turn(self, "qa-fix-item", returns=QaRunResult)
        return self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self._story.story_slug,
                "story_id": self._story.story_id or self._story.story_slug,
                "epic": self._story.story_epic,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "plan_services": self.call(plan_summary, self._story.spec_dir).text,
                "qa_dir": self._story.qa_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
            },
        )

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


__all__ = ["BLOCKED_NOTE", "MAX_FIX_LAPS", "Fix", "render_gate"]
