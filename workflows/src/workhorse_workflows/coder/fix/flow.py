"""Drain the coder's own backlog, one filed item at a time — the port of
`coder/workflow.yaml`'s `flows.fix` (24 nodes, lines 3605-3893).

Standalone only. Nothing hands off to it: the main graph carries its **own** copy of the
drain (`select_fix_item` through `decide_post_drain`, lines 859-1144), which rides inside an
epic's story chain and commits nothing of its own. This flow is the copy you run with no
epic and no story selected — and it differs from the nested one in exactly two ways, both of
which the YAML's comment calls out and both of which are states here::

    draw → plan → dispatch → implement → check → (apply once → recheck)
         → (prune | flag) → document → commit → draw

* it **documents** each drained item, by handing off to the `docs` flow — the nested copy
  runs documentation once at the end of the story, over the whole working tree;
* it **commits** each drained item onto the current branch, one commit per item, no push
  and no PR — the nested copy's changes ride the story's own commit.

And it terminates when the backlog is dry, where the nested copy falls through to
`decide_post_drain` and the story chain continues. Both shapes have to exist; this one is
not reachable from the other.

Twenty-four nodes become nine states. Six are `type: branch` routers reading a value
produced directly above them; `resolve_workspace` is `setup`; `prune_fix_item` and
`fix_give_up` are one deterministic node each, reached from two deciding sites apiece, so
they are the private routers `_prune` and `_flag` rather than states.

Divergences from the YAML, all deliberate:

* **only the first service layer is implemented.** `implement_fix.next` is `check_fix`, not
  `select_fix_layer` — there is no layer loop here, where `flows.dev` has one. A drained fix
  whose plan dispatches two services gets one of them implemented and is then QA'd. That is
  the YAML's wiring, preserved; it is recorded in the progress ledger as a finding, because
  it reads much more like an omission than a decision.
* **`branch_fix_code_repos` is called with `spec_dir` alone.** `flows.dev` passes the story
  branch and the docs path too; this node's YAML argument list is one entry long, so
  `branch` and `docs_path` take their empty defaults. Preserved rather than harmonised —
  passing `self.docs_path` here would change which repos get branched on a run whose docs
  root is not the working directory.
* `implement-plan.md`'s last three args (`impl_instruction_paths`, `qa_run_plan`,
  `verification_setup`) are passed although the YAML node does not list them, for the reason
  `flows.dev` records: the prompt reads them, and under the YAML engine they were in scope
  because `resolve_fix_impl_context` declared them as outputs. Same values, same source
  node, different route.
* `refuel: fix_bullet_id` on `select_fix_item` has no counterpart: pyflow has no gas tank.
  The drain is unbounded in the YAML and bounded here by the transition budget — the same
  loop-2 design question `okf-builder` raised.
* **`fix_documentation_failed` was a `type: fail`**, so the arm that reached it raises
  `WorkflowFailed` at the deciding site.
* there is **no `stamp_specs` after the plan turn**, where `flows.dev` has one. The YAML
  wires `plan_fix` straight to its branch; a drained fix's plan is not registered as an OKF
  Concept. Preserved.
* the `done` terminal declared no outputs, so the flow returns the draw that found nothing —
  `FixPick(has_fix=False)` carries the reason the pool is dry, which is the whole of what
  the YAML had to say at that node.
"""
from __future__ import annotations

from pathlib import Path
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
from workhorse_workflows.coder.shared.dev import (
    branch_code_repos,
    plan_summary,
    read_operator_context,
    resolve_impl_context,
    select_next_layer,
)
from workhorse_workflows.coder.shared.escalation import escalation
from workhorse_workflows.coder.shared.queue import commit_story
from workhorse_workflows.coder.shared.story import prepare_fix_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry, ImplResult, PlanResult
from workhorse_workflows.coder.shared.schemas.qa import QaResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs

#: The note `mark-fix-blocked.py` was handed, verbatim — it names both ways in.
BLOCKED_NOTE = "blocked in fix loop (plan blocked, or QA still failing after one retry)"


class Fix(Workflow):
    """Drain the backlog's `Filed by coder` items, each as a one-AC story, each committed."""

    #: The docs repo root, when the planning documents live in a checkout of their own.
    #: Empty walks up from `repo_dir`, i.e. the docs sit beside the code.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""
    #: `local` or `dev` — passed to the impl-context decode and to both QA turns.
    target_env: str = "local"

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> WorkspaceDirs:
        """Every directory an agent turn in this run may read.

        `resolve_workspace` is the whole of it. Unlike every other per-story flow, `fix` has
        no story at setup time — it draws one per iteration — so the workspace is the only
        thing that can be resolved once and used by all of them.
        """
        return self.call(resolve_workspace_dirs, self.docs_path)

    # ── the drain loop ────────────────────────────────────────────────────────────────

    def start(self) -> Continue | Done:
        """Draw the next drainable bullet, seed it as a story, and resolve its paths.

        `select_fix_item` + `decide_fix_item` + `seed_fix_story` + `prepare_fix_story`. The
        two seeding nodes are deterministic and unbranched, so they belong to the state that
        decided there was something to seed.

        The draw does not touch the backlog file — pruning and flagging happen at the far end
        of the iteration — which is what lets a resumed run re-draw the same item and land on
        the same story rather than skipping it.
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
        return Continue(story, self.plan)

    def plan(self) -> Continue:
        """Plan the one-AC fix story — the same planner `dev` runs, on a much smaller story.

        `plan_fix` + `decide_plan_fix`. A `blocked` plan is the first of the two ways an item
        gets flagged rather than pruned; a blank status takes the YAML's `default:` arm and
        proceeds, exactly as `dev`'s plan gate does.
        """
        self.logger.info("planning %s", self._story.story_slug, extra={"activity": True})
        turn = roles.turn("plan-story", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=PlanResult,
            # high: the same planner `dev` runs. A fix story is small, but the plan still
            # decides what production code gets touched.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args
            | {
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "story_slug": self._story.story_slug,
                "epic": self._story.story_epic,
            },
        )
        if result.status == "blocked":
            return self._flag(result)
        return Continue(result, self.dispatch)

    def dispatch(self) -> Continue:
        """Decode the plan, branch the repos it names, and take the first service layer.

        `resolve_fix_impl_context` + `branch_fix_code_repos` + `select_fix_layer` +
        `decide_fix_layer`. All three nodes are deterministic and the branch reads the
        third's own output, so they are one state.

        A plan that dispatches no layer at all is legitimate — a fix that changes only
        documents — and goes straight to the QA turn, which is what `decide_fix_layer`'s
        `"no"` arm did.
        """
        self.call(resolve_impl_context, self._story.spec_dir, self.target_env, self.docs_path)
        self.call(branch_code_repos, self._story.spec_dir)
        pick = self.call(select_next_layer, self._story.spec_dir, -1)
        if not pick.has_layer:
            self.logger.info("no service layer dispatched — checking the fix as it stands")
            return Continue(pick, self.check)
        return Continue(pick, self.implement)

    def implement(self, operator_context: str = "", impl_blocks: int = 0) -> Continue | Await:
        """Implement the first service layer, and only it — see the module docstring.

        A state of its own for the reason `dev`'s is: it is the expensive turn, and a
        checkpoint is written before a state runs, so a kill during QA re-enters at QA rather
        than implementing a second time.

        The verdict is branched on, which is the same root cause `dev` was repaired for and
        the reason this state was rewritten: a turn reporting it could not implement the plan
        used to be discarded here, so the drain went on to QA a change nobody had written and
        then flagged the bullet as if the *fix* were the thing that had failed. It is a block
        like any other now — it parks on the story's `context.md` and re-enters this state
        with the answer in hand.

        `operator_context` is what the answer said; the prompt reads it, and a blank one is
        the ordinary first pass.
        """
        layer = self._layer
        impl = self.output(resolve_impl_context)
        self.logger.info("implementing %s", layer.service or "the fix", extra={"activity": True})
        turn = roles.turn("implement-plan", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=ImplResult,
            # high: writes the production change.
            power="high",
            cwd=layer.cwd,
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self._story.story_slug,
                "epic": self._story.story_epic,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "plan_file": layer.plan_file,
                "service_path": layer.service_path,
                "service_type": layer.type,
                "verification": layer.verification,
                "impl_instruction_paths": impl.impl_instruction_paths,
                "impl_instructions": impl.impl_instructions,
                "qa_run_plan": impl.qa_run_plan,
                "verification_setup": impl.verification_setup,
                "operator_context": operator_context,
            },
        )
        if result.blocked:
            return self._gate_impl(result, impl_blocks)
        return Continue(result, self.check)

    def read_operator_impl(self, impl_blocks: int = 0) -> Continue:
        """Consume the operator's answer and implement again with it in hand.

        The thin consume state an `Await` asks for — resume replays its target from the top,
        so everything but the answer is read by reference. `SCOPE: epic` has no meaning here
        and is deliberately not honoured: the drain has no epic queue to hand a story back
        to, and every item it draws is its own one-AC story.
        """
        answer = self.call(read_operator_context, self._story.story_path)
        return Continue(
            answer, self.implement, operator_context=answer.content, impl_blocks=impl_blocks
        )

    def check(self) -> Continue:
        """QA the fix. `check_fix` + `decide_fix_check`.

        `qa-story.md` run directly rather than the whole `qa` flow: a drained fix gets one QA
        turn and, if it fails, one fix-and-recheck. Anything the YAML's `default:` arm caught
        — a blank status included — spends that retry.
        """
        result = self._qa()
        if result.status == "passed":
            return self._prune(result)
        return Continue(result, self.apply_once, notes=result.notes)

    def apply_once(self, notes: str = "") -> Continue:
        """The single retry: apply what QA found. `apply_fix_once`.

        `notes` is `{{ get_node_output('check_fix','qa_result').notes }}`, threaded as an
        argument because it crosses from one agent turn to the next and agent turns are not
        nodes — `self.output` cannot reach them.

        No session chain, unlike the QA lane's fix loop: there is exactly one lap here, so
        there is no second turn for a chain to hand anything to.
        """
        self.logger.info("applying QA fixes to the drained item", extra={"activity": True})
        turn = roles.turn("apply-qa-fixes", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=QaResult,
            # high: this retry has to converge, because there is not a second one.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self._story.story_slug,
                "epic": self._story.story_epic,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "qa_dir": self._story.qa_dir,
                "qa_notes": notes,
            },
        )
        return Continue(result, self.recheck)

    def recheck(self) -> Continue:
        """QA it again, and settle the item either way. `recheck_fix` + `decide_recheck`.

        The only arm that prunes is `passed`; everything else — including the blank the
        YAML's `default:` caught — flags the bullet and moves on. *This* arm never escalates
        to an operator, which is the design: a fix that will not converge stays visible in
        the backlog, annotated, and stops costing the loop anything. That is a statement
        about a QA verdict the drain believes, not about the drain's tolerance for blocks —
        an implementation turn that says it cannot proceed has produced no verdict to
        believe, and `implement` parks on it.
        """
        result = self._qa()
        if result.status == "passed":
            return self._prune(result)
        return self._flag(result)

    # ── the far end of an iteration ───────────────────────────────────────────────────

    def document(self) -> Continue:
        """Fold the drained item into the OKF book. `document_fix_item` + its two branches.

        The `docs` flow, handed off to. `not_applicable` — no OKF book here — is a pass, and
        anything else is `fix_documentation_failed`, which was a `type: fail`.
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

        `commit_fix_item`, which is `commit-story.py` unchanged: it resolves the affected
        repos from *this* fix's own plan context, via this iteration's `spec_dir`, so each
        commit covers exactly the repos its own plan touched. No push and no PR — this flow
        is standalone, and there is no epic branch for it to open one against.

        `kind="fix"` is the one override of the story default: every item this flow drains
        was *filed* — by a review, by QA, by an operator — against behavior that already
        shipped. Committing those as `feat` would bump a minor version for a repair and
        list the defect in the changelog's features.
        """
        seed = self.output(seed_fix_story)
        result = self.call(
            commit_story, seed.epic, self._story.story_slug, self._story.spec_dir, kind="fix"
        )
        return Continue(result, self.start)

    # ── routers and shared turns, none of them states ─────────────────────────────────

    def _prune(self, result: CoderResult) -> Continue:
        """`prune_fix_item`: the fix shipped, so its bullet leaves the backlog."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.call(prune_fix_item, bullet, self.docs_path)
        return Continue(result, self.document)

    def _flag(self, result: CoderResult) -> Continue:
        """`fix_give_up`: the bullet is annotated in place, and the drain moves on.

        Reached from the blocked plan and from a second failing QA. Both wrote the same note,
        which is why it is one string and not two.
        """
        bullet = self.output(select_fix_item).fix_bullet_id
        self.logger.info("flagging %s as blocked", bullet)
        self.call(mark_fix_blocked, bullet, BLOCKED_NOTE, self.docs_path)
        return Continue(result, self.document)

    def _gate_impl(self, result: ImplResult, impl_blocks: int) -> Await:
        """`implement` said it could not — park on the story and ask.

        Straight to the file, with no resolver arm: the drain has no `operator_mode` and no
        resolver turn of its own, because unlike `dev` it is not running inside a story
        queue whose other stories are waiting on this one. Nothing is lost by asking, and
        `escalation` publishes the turn's own findings so whoever answers is not re-deriving
        them.

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
            self._context, gate.body, self.read_operator_impl, impl_blocks=impl_blocks + 1
        )

    @property
    def _context(self) -> Path:
        """The file an `Await` writes its questions into: `<story-folder>/context.md`.

        The drained item's own story folder, not the run's — this flow has a new story per
        iteration, so the question lands beside the item it is about.
        """
        return paths.story_context_path(self._story.story_path)

    def _qa(self) -> QaResult:
        """`qa-fix-item.md`, which `check_fix` and `recheck_fix` ran with identical arguments.

        Not `qa-story.md`: that prompt assesses a run ostler already executed, and the drain
        has no runner behind it — it never passes `runner_status`, and it asks back for a
        `passed | failed | blocked` verdict, not an assessment's disposition. The YAML pointed
        both here and there, so the turn could not parse and always defaulted to a blank
        status, which the branch below reads as "not passed".
        """
        self.logger.info("checking %s", self._story.story_slug, extra={"activity": True})
        turn = roles.turn("qa-fix-item", self.repo_dir, self.library_dirs)
        return self.agent(
            turn.prompt,
            returns=QaResult,
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

    @property
    def _story(self) -> StoryPaths:
        """The story this iteration is draining, as `prepare_fix_story` resolved it.

        Read off the node's recorded output rather than threaded through eight states as a
        parameter — and it survives the `docs` handoff, because a handoff subscopes the run
        writer, so the child's own `prepare_story` call cannot overwrite this one.
        """
        return self.output(prepare_fix_story)

    @property
    def _layer(self) -> DispatchEntry:
        """The one service layer this fix implements, as `select_fix_layer` picked it."""
        return self.output(select_next_layer).layer

    def _dirs(self) -> list[str]:
        """`{{ workspace_dirs }}` — the `add_dirs` every agent turn in this flow was given."""
        return list(self.ctx.dirs)


__all__ = ["BLOCKED_NOTE", "Fix"]
