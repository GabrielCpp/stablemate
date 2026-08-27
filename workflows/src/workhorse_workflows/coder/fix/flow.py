"""Drain the coder's own backlog, one filed item at a time.

Standalone only. Nothing hands off to it: the main graph carries its **own** copy of the
drain, which rides inside an epic's story chain and commits nothing of its own. This flow
is the copy you run with no epic and no story selected, and it differs from the nested one
in exactly two ways, both of which are states here::

    start → item → gates → (item | Await) → check → (apply once → recheck)
          → (prune | flag) → document → commit → start

* it **documents** each drained item, by handing off to the `docs` flow — the nested copy
  runs documentation once at the end of the story, over the whole working tree;
* it **commits** each drained item onto the current branch, one commit per item, no push
  and no PR — the nested copy's changes ride the story's own commit.

And it terminates when the backlog is dry, where the nested copy's drain falls through and
the story chain continues. Both shapes have to exist; this one is not reachable from the
other.

**One turn per item.** A drained bullet is a one-criterion repair, so the lane does not
mimic `dev`'s plan → dispatch → implement split: a single session plans the fix and writes
it, and the gates that judge the result run afterwards, in Python, against the repositories
git says the turn actually changed. The split is what produced the two defects that lived
here — a plan whose dispatch named two services got exactly one of them implemented, and
the planner filed new backlog items into the very list this loop drains — and deleting it
is what fixes them.

The QA tail is unchanged and deliberately so: one verdict, one retry, one recheck. A fix
that will not converge in that budget is annotated in the backlog rather than escalated —
see `recheck`.
"""
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
from workhorse_workflows.coder.shared.story import prepare_fix_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.dev import FailureReport, ImplResult
from workhorse_workflows.coder.shared.schemas.qa import QaRunResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs

#: The note `mark_fix_blocked` is handed, verbatim. One way in now that the plan turn
#: is gone: `recheck` is the only caller of `_flag`, and every other block parks.
BLOCKED_NOTE = "blocked in fix loop (QA still failing after one retry)"

#: Repair laps a red gate buys before the block goes to an operator. The same budget
#: `dev` spends on the same failure, for the same reason: a gate that is still red on the
#: fourth reading of its own output is not going to be read into submission.
MAX_FIX_LAPS = 3



def render_gate(report: FailureReport) -> str:
    """The failing gate, as the prompt's `gate_report` section reads it.

    Rendered here rather than in the template because the payload is a pydantic model and
    a model handed to Jinja renders as its Python repr. The turn needs the command, the
    directory to re-run it in, and the output — anything else it can read off the tree.
    """
    return (
        f"Repair lap {report.lap}: the `{report.source}` gate failed in `{report.cwd}`.\n\n"
        f"Command: `{report.command}`\n\n"
        f"```\n{report.output}\n```"
    )


class Fix(Workflow):
    """Drain the backlog's `Filed by coder` items, each as a one-AC story, each committed."""

    #: The docs repo root, when the planning documents live in a checkout of their own.
    #: Empty walks up from `repo_dir`, i.e. the docs sit beside the code.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""
    #: `local` or `dev` — passed to both QA turns.
    target_env: str = "local"

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> WorkspaceDirs:
        """Every directory an agent turn in this run may read.

        Unlike every other per-story flow, `fix` has no story at setup time — it draws one
        per iteration — so the workspace is the only thing that can be resolved once and
        used by all of them.
        """
        return self.call(resolve_workspace_dirs, self.docs_path)

    # ── the drain loop ────────────────────────────────────────────────────────────────

    def start(self) -> Continue | Done:
        """Draw the next drainable bullet, seed it as a story, and resolve its paths.

        The draw does not touch the backlog file — pruning and flagging happen at the far
        end of the iteration — which is what lets a resumed run re-draw the same item and
        land on the same story rather than skipping it.
        """
        pick = self.call(select_fix_item, self.docs_path)
        if not pick.has_fix:
            self.logger.info("backlog drained: %s", pick.reason)
            return Done(pick)
        self.logger.info("draining %s: %s", pick.fix_bullet_id, pick.fix_bullet_text)
        seed = self.call(
            seed_fix_story, pick.fix_bullet_id, pick.fix_bullet_text, "", "", self.docs_path
        )
        story = self.call(prepare_fix_story, self.docs_path, seed.story_slug, seed.epic)
        return Continue(story, self.item)

    def item(
        self,
        gate_report: str = "",
        operator_context: str = "",
        impl_blocks: int = 0,
        lap: int = 0,
    ) -> Continue | Await:
        """Plan and write the repair, in one session — and re-enter it for each repair lap.

        A state of its own because it is the expensive turn, and a checkpoint is written
        before a state runs: a kill during QA re-enters at QA rather than implementing a
        second time.

        The verdict is branched on. A turn reporting it could not implement was discarded
        here for the whole of this lane's life, so the drain went on to QA a change nobody
        had written and then flagged the bullet as if the *fix* were the thing that had
        failed. It is a block like any other now — it parks on the story's `context.md` and
        re-enters this state with the answer in hand.

        `gate_report` is also which of the two prompts this is. A blank one is the first
        pass — plan the repair and write it — and a rendered one is a gate that went red,
        which is a different job with a different input and so a different file. The flow
        knows which it is dispatching, so it names the prompt rather than describing both
        arrivals to the agent and asking it to sniff which one it got.

        `operator_context` is what an answered block said, and is not a third arrival: it
        is ground truth added to whichever of the two laps parked on the question.
        """
        self.logger.info(
            "fixing %s (lap %d)", self._story.story_slug, lap + 1, extra={"activity": True}
        )
        repair = bool(gate_report)
        turn = roles.turn(self, "fix-item-repair" if repair else "fix-item", returns=ImplResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            # high: the first pass is both the plan and the production change, and a
            # repair lap is the same code under a gate that already objected once.
            power="high",
            add_dirs=self._dirs(),
            # The repair laps and the operator's answers are one conversation: the turn
            # that wrote the line a gate objects to knows why it is there.
            session=story_chain(self._story.story_slug),
            args=turn.args
            | {
                "story_slug": self._story.story_slug,
                "epic": self._story.story_epic,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "bullet_text": self.output(select_fix_item).fix_bullet_text,
                "operator_context": operator_context,
            }
            # Only the repair prompt renders it, and only it is ever handed it: an
            # argument a template never reads is one a reader has to go and check.
            | ({"gate_report": gate_report} if repair else {}),
        )
        if result.blocked:
            return self._gate_impl(result, gate_report, impl_blocks, lap)
        return Continue(result, self.gates, lap=lap)

    def gates(self, lap: int = 0, impl_blocks: int = 0) -> Continue | Await:
        """Run the repo's own gates over what the turn changed, and buy a lap when one is red.

        The targets are derived from git rather than from a plan: every repository this run
        can reach is asked what it is holding, and the ones with changes get one pass of
        each gate. That is the deterministic half of the split this lane used to have — a
        plan naming its services was the agent's account of where the work went, and this
        is git's.

        No service name is passed, because a drained item is not dispatched per layer:
        `run_gate` falls back to the repository's own `make <gate>`, which is the whole
        check for a repo-wide repair.
        """
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
        """Consume the operator's answer and re-enter the turn with it in hand.

        The thin consume state an `Await` asks for — resume replays its target from the
        top, so everything but the answer is read by reference. `SCOPE: epic` has no
        meaning here and is deliberately not honoured: the drain has no epic queue to hand
        a story back to, and every item it draws is its own one-AC story.
        """
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
        """QA the fix.

        `qa-fix-item.md` run directly rather than the whole `qa` flow: a drained fix gets
        one QA turn and, if it fails, one fix-and-recheck.
        """
        result = self._qa()
        if result.status == "passed":
            return self._prune(result)
        return Continue(result, self.apply_once, notes=result.notes)

    def apply_once(self, notes: str = "", impl_blocks: int = 0) -> Continue | Await:
        """The single retry: apply what QA found.

        `notes` is the check's verdict, threaded as an argument because it crosses from one
        agent turn to the next and agent turns are not nodes — `self.output` cannot reach
        them.

        The verdict this turn returns was parsed and then dropped, which meant a fixer that
        reported it could not apply the findings was rechecked anyway and the bullet flagged
        as if QA had failed twice. `blocked` parks instead: the retry produced no change to
        recheck, and asking is what a block is for.
        """
        self.logger.info("applying QA fixes to the drained item", extra={"activity": True})
        turn = roles.turn(self, "apply-qa-fixes", returns=QaRunResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            # high: this retry has to converge, because there is not a second one.
            power="high",
            add_dirs=self._dirs(),
            session=story_chain(self._story.story_slug),
            args=turn.args | {
                "story_slug": self._story.story_slug,
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
        """QA it again, and settle the item either way.

        The only arm that prunes is `passed`; anything else flags the bullet and moves on.
        *This* arm never escalates to an operator, which is the design: a fix that will not
        converge stays visible in the backlog, annotated, and stops costing the loop
        anything. The residue is caught where it is cheap to catch — a flagged bullet is
        still in the backlog the next drain reads, and the run that filed it reads its own
        annotation rather than re-deriving the failure.

        That is a statement about a QA verdict the drain believes, not about its tolerance
        for blocks — a turn that says it cannot proceed has produced no verdict to believe,
        and `item` and `apply_once` both park on one.
        """
        result = self._qa()
        if result.status == "passed":
            return self._prune(result)
        return self._flag(result)

    # ── the far end of an iteration ───────────────────────────────────────────────────

    def document(self) -> Continue:
        """Fold the drained item into the OKF book, by handing off to the `docs` flow.

        `not_applicable` — no OKF book here — is a pass, and anything else fails the run:
        an undocumented item that has already been pruned off the backlog is invisible to
        every drain after this one.
        """
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
        """Commit this one item onto the current branch, then draw the next.

        The repos are the ones git says this iteration changed, for the same reason the
        gates are: there is no plan context to read them off, and the workspace manifest
        lists every repo the run *may* touch rather than the ones it did. No push and no
        PR — this flow is standalone, and there is no epic branch to open one against.

        `kind="fix"` is the one override of the story default: every item this flow drains
        was *filed* — by a review, by QA, by an operator — against behaviour that already
        shipped. Committing those as `feat` would bump a minor version for a repair and
        list the defect in the changelog's features.
        """
        seed = self.output(seed_fix_story)
        result = self.call(
            commit_story,
            seed.epic,
            self._story.story_slug,
            self._story.spec_dir,
            kind="fix",
            roots=self._changed_dirs(),
        )
        return Continue(result, self.start)

    # ── routers and shared turns, none of them states ─────────────────────────────────

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
        """A turn said it could not — park on the story and ask.

        Straight to the file, with no resolver arm: the drain has no `operator_mode` and no
        resolver turn of its own, because unlike `dev` it is not running inside a story
        queue whose other stories are waiting on this one. Nothing is lost by asking, and
        `escalation` publishes the turn's own findings so whoever answers is not
        re-deriving them.

        Uncapped, per AGENTS.md: `impl_blocks` numbers the escalations for a reader and
        bounds nothing. A block that recurs asks again.
        """
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
        """The repair budget is spent and the gate is still red — ask, do not give up.

        A spent budget is a block, not a failure: the change is real, the gate's own output
        says what is wrong with it, and the answer is one an operator can give. The turn
        re-enters with the same report in hand, which is why it is rendered into the
        `Await` rather than recomputed on the way back.
        """
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
        """`qa-fix-item.md`, which `check` and `recheck` run with identical arguments.

        Not `qa-story.md`: that prompt assesses a run ostler already executed, and the drain
        has no runner behind it — it never passes `runner_status`, and it asks back for a
        `passed | failed | blocked` verdict, not an assessment's disposition.
        """
        self.logger.info("checking %s", self._story.story_slug, extra={"activity": True})
        turn = roles.turn(self, "qa-fix-item", returns=QaRunResult)
        return self.agent(
            turn.prompt,
            returns=turn.returns,
            # high: the drain has no QA plan, no evidence gate and no audit behind it — this
            # turn is the whole verdict on the fix.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self._story.story_slug,
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
        """The run's repositories that are holding work for this item, git's account of it.

        Asked of every directory the workspace resolved rather than of a plan, so a repair
        spanning two repos is gated in both and committed in both. A repo holding nothing
        is dropped: gating it would run the whole suite of a repository this item never
        touched.
        """
        return [
            d
            for d in self._dirs()
            if self.call(changed_files, d, self._story.story_slug).paths
        ]

    @property
    def _story(self) -> StoryPaths:
        """The story this iteration is draining, as `prepare_fix_story` resolved it.

        Read off the node's recorded output rather than threaded through eight states as a
        parameter — and it survives the `docs` handoff, because a handoff subscopes the run
        writer, so the child's own `prepare_story` call cannot overwrite this one.
        """
        return self.output(prepare_fix_story)

    def _dirs(self) -> list[str]:
        """The `add_dirs` every agent turn in this flow is given."""
        return list(self.ctx.dirs)


__all__ = ["BLOCKED_NOTE", "MAX_FIX_LAPS", "Fix", "render_gate"]
