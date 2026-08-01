"""`coder`: the epic/story loop, and the registry the whole distribution hangs off.

The YAML's main graph was 80 nodes across `workflow.yaml` lines 191–1348, above eight
`flows:` blocks that make up the other three quarters of the file. Those eight are one
directory each here — `dev/`, `qa/`, `genesis/` and the rest — and this module is the
graph that sequences them.

**What the shape buys, at this size.** Twenty-seven states cover eighty nodes, and the
factor of three is not compression for its own sake — it is the `decide_*` nodes
disappearing into the `if` at the end of the state that produced the value they branch on.
`decide_epic` existed because the YAML had no way to write "select an epic, then look at
what came back"; here that is two lines of one function. The same goes for the eight
`incr_*`/`reset_*`/`init_*` counter nodes: a counter is a state parameter, so seeding it is
a keyword on a `Continue` and there is nothing left to be a node.

**Where the state boundaries are.** A state is a resumable unit, and the rule the port
follows everywhere is that a state ends where the *expensive or irreversible* thing begins:
each `handoff` to a sub-flow, each agent turn, and each of the two operator gates starts
one. Deterministic nodes fold forward into whichever state branches on them. That is why
`prune_epic` sits inside `open_pr` (a straight line, and the YAML's own comment says the
pop must precede the PR) while `dev`, `review`, `document` and `qa` are four states rather
than one — a kill during QA must not re-run the implementation.

**The three counters are parameters, and one of them travels a long way.** `ci_rework` and
`merge_rework` live inside the PR cluster. `zero_diff` — consecutive stories whose commit
found nothing to commit — is a *run-global* counter in the YAML, reset only by a commit
that landed something, so it survives the epic boundary and has to be threaded through the
PR/CI/merge cluster to get from one epic's last story to the next epic's first. Threading
it is noisier than a mutable field would be and it is the honest shape: it is state the
checkpoint has to carry, and every other way of writing it hides that.

**Two disjunctions that look alike and are not.** The YAML resolves the working epic two
different ways and the port keeps both apart:

* the story pipeline uses `prepare_story.story_epic or select_story.epic or epic` — the
  epic the *story* belongs to, discovered by scanning when story mode was handed a bare
  slug;
* `commit_story`, `qa_give_up` and `replan_epic` use `select_epic.epic or epic` — the epic
  the *queue* is working, which in story mode is whatever the run was invoked with.

Both are fall-back chains because `self.output()` raises for a node that has not run, and
in story mode neither `select_epic` nor `select_story` ever runs. The queue epic is carried
as a state parameter rather than read back through a guarded `self.output`, so a resumed
run does not have to re-derive it.

**The backlog drain is nested here as well as being a flow.** `fix/flow.py` is the
standalone drain; states `drain` through `fix_recheck` below are the same seven steps run
*inside* a story's run, right after that story goes green, which is what the YAML did at
lines 859–1144. They are not a `handoff` to `Fix` because the two differ in their far end:
the standalone flow documents and commits each drained item on its own, while the nested
copy leaves both to the story's own `final_docs` and commit, so one commit covers the story
and everything drained behind it. The duplication is the YAML's and it is preserved; it is
on loop 2's list, not resolved silently here.
"""
from __future__ import annotations

from typing import ClassVar

from workhorse.cli import console_script
from workhorse.pyflow import (
    Await,
    Continue,
    Done,
    NodeNotRunError,
    Registry,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.dream import Dream
from workhorse_workflows.coder.fix import BLOCKED_NOTE, Fix
from workhorse_workflows.coder.fix_ci import FixCi
from workhorse_workflows.coder.genesis import Genesis
from workhorse_workflows.coder.qa import Qa
from workhorse_workflows.coder.review import Review
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.backlog import (
    mark_fix_blocked,
    prune_fix_item,
    seed_fix_story,
    select_fix_item,
)
from workhorse_workflows.coder.shared.ci import poll_pr_checks, push_ci_fix
from workhorse_workflows.coder.shared.dev import (
    branch_code_repos,
    resolve_impl_context,
    select_next_layer,
)
from workhorse_workflows.coder.nodes.pr import (
    flag_ci_failure,
    flag_merge_failure,
    merge_pr,
    open_pr,
    open_story_pr,
)
from workhorse_workflows.coder.shared.queue import (
    begin_run,
    branch_epic,
    branch_story,
    commit_story,
    flag_epic_blocked,
    flag_qa_failure,
    init_base,
    prune_epic,
    select_epic,
    select_story,
)
from workhorse_workflows.coder.shared.story import (
    prepare_fix_story,
    prepare_story,
    resolve_workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry, ImplResult, PlanResult
from workhorse_workflows.coder.shared.schemas.pr import MergeFixResult
from workhorse_workflows.coder.shared.schemas.qa import QaResult
from workhorse_workflows.coder.shared.schemas.queue import ReplanResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs


class Coder(Workflow):
    """Implement one epic's stories end to end, or one named story.

    `mode` decides which: `epic` walks the queue in the epics root's `index.md`, taking the front
    epic, then each of its unimplemented stories in turn, and opens one pull request for the
    whole epic when the last story lands. `story` skips the queue, cuts a branch for the one
    slug it was given, and opens that story's own PR at the end.

    Every story takes the same five steps — implement, review, document, QA, commit — with
    the backlog drain wedged between QA and commit, so a fix filed while the story was being
    built ships in the same commit as the story that filed it.
    """

    #: `epic` (walk the queue) or `story` (one named slug). Anything else takes the
    #: YAML `default:` arm, which was `init_base` — the epic path.
    mode: str = "epic"
    #: The docs repo root, when the planning documents live in a checkout of their own
    #: rather than beside the code. Blank walks up from `repo_dir`.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""
    #: The story slug, in story mode. Ignored in epic mode, where the queue picks.
    story: str = ""
    #: The epic to work, when it should not be read off the front of the queue.
    epic: str = ""
    #: `auto` lets the sub-flows resolve their own blocks; `operator` escalates to a human.
    #: It does not reach the CI gate, which is always human — see `_ci_gate`.
    operator_mode: str = "auto"
    #: Which environment QA runs against, passed through to `dev`, `docs` and `qa`.
    target_env: str = "local"
    #: The QA stack manifest `qa` reads to bring services up.
    qa_stack_manifest: str = "qa-stack.yml"

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one, which is what carries them into the eight sub-flows:
    #: a `handoff` constructs a fresh workflow, so nothing crosses that boundary unless
    #: something puts it there. See `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: `max_ci_reworks` — automated attempts at a red PR before the operator is asked.
    MAX_CI_REWORKS: ClassVar[int] = 3
    #: `max_merge_reworks` — automated attempts at a conflicted merge, ditto.
    MAX_MERGE_REWORKS: ClassVar[int] = 2
    #: `max_zero_diff_commits` — consecutive stories whose commit found nothing to commit
    #: before the run gives up. Three in a row is not a run making progress.
    MAX_ZERO_DIFF_COMMITS: ClassVar[int] = 3

    # Eighty nodes with several loops in them: the default budget is not generous here.
    max_transitions: ClassVar[int] = 4000

    def setup(self) -> WorkspaceDirs:
        """Resolve every directory this run's agent turns may read, once.

        `resolve_workspace` in the YAML, which sat on the *story* path only — so the two
        agent turns in the main graph that take `add_dirs: {{ workspace_dirs }}`
        (`fix_merge` and `replan_epic`) rendered it empty on any run that reached them
        before the first story. The node's one argument is `docs_path`, which is a run
        input, so resolving it in `setup()` is the same call at a strictly earlier point.
        It is a widening and it is recorded as one.
        """
        return self.call(resolve_workspace_dirs, self.docs_path)

    def labels(self) -> dict[str, str]:
        """Which story, which epic, which mode, how far through — the YAML's `labels:`.

        `work_id` and `progress` come off `select_story`'s record when there is one. Story
        mode never runs that node, so both fall back the way the YAML's `or story` did.
        """
        base = {"work_id": self.story, "epic": self.epic, "mode": self.mode, "progress": ""}
        try:
            pick = self.output(select_story)
        except NodeNotRunError:
            return base
        return {
            **base,
            "work_id": pick.story_slug or self.story,
            "epic": pick.epic or self.epic,
            "progress": pick.progress,
        }

    # ── mode ──────────────────────────────────────────────────────────────────────────

    def start(self) -> Continue:
        """`decide_mode`: the queue, or the one story we were pointed at.

        Story mode cuts its branch here — off the current HEAD, recording the base it came
        from, because the PR at the far end has to target that base and re-deriving it from
        the slug is how the two drifted once.

        `begin_run` goes first in both modes: the run dir is stable across runs, so this is
        where a previous run's set-aside epics and given-up stories stop being ours.
        """
        self.call(begin_run, str(self.run_dir))
        if self.mode == "story":
            branch = self.call(branch_story, self.story, self.docs_path)
            self.logger.info("story mode: %s off %s", branch.story_branch, branch.base_branch)
            return Continue(branch, self.prepare, slug=self.story, epic=self.epic)
        return Continue(self.call(init_base), self.select_epic)

    # ── the epic queue ────────────────────────────────────────────────────────────────

    def select_epic(self, zero_diff: int = 0) -> Continue | Done:
        """`select_epic` + `decide_epic` + `branch_epic`: take the front of the queue.

        The branch is cut in the same state as the pick because nothing branches between
        them. An empty queue is the run's ordinary end, not a failure.
        """
        pick = self.call(select_epic, self.docs_path, str(self.run_dir))
        if not pick.has_epic:
            self.logger.info("no epic to work: %s", pick.reason)
            return Done(pick)
        base = self.output(init_base).base_branch
        self.call(branch_epic, pick.epic, base)
        return Continue(pick, self.select_story, epic=pick.epic, zero_diff=zero_diff)

    def select_story(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`select_story` + `decide_story`: the next unimplemented story of this epic.

        Three outcomes, and the third is the one worth naming: `blocked` does *not* fail the
        run. It flags the epic, and goes back to `select_epic` for the next one — a blocked
        epic is a planning problem, and stopping the whole loop over it would strand every
        other epic behind it.
        """
        pick = self.call(select_story, epic, self.docs_path, str(self.run_dir))
        if pick.story_outcome == "story":
            return Continue(pick, self.prepare, slug=pick.story_slug, epic=epic,
                            zero_diff=zero_diff)
        if pick.story_outcome == "done":
            self.logger.info("epic %s has no stories left — opening its PR", epic)
            return Continue(pick, self.open_pr, epic=epic, zero_diff=zero_diff)
        # `blocked`, and the YAML's `default:` arm, which pointed at the same node.
        self.call(flag_epic_blocked, epic, str(self.run_dir), pick.reason)
        return Continue(pick, self.select_epic, zero_diff=zero_diff)

    # ── one story ─────────────────────────────────────────────────────────────────────

    def prepare(self, slug: str = "", epic: str = "", zero_diff: int = 0) -> Continue:
        """`prepare_story` + `init_triage_counter`: resolve the slug to paths.

        The triage budget is seeded here rather than inside `qa` for the reason the YAML
        gives at `init_triage_counter`: it has to survive across QA *entries*, because a
        rescope sends the story back to `dev` and re-enters QA, and a budget that reset on
        each entry would never be spent. That is why `triage` is threaded through the four
        pipeline states below instead of starting at zero in `qa`.
        """
        story = self.call(prepare_story, self.docs_path, slug, epic)
        self.logger.info("preparing %s%s", slug, self._progress(), extra={"activity": True})
        return Continue(story, self.dev, epic=epic, zero_diff=zero_diff)

    def dev(self, epic: str = "", zero_diff: int = 0, triage: int = 0) -> Continue:
        """`dev` + `decide_dev`: plan and implement the story.

        `replan` is the sub-flow saying the *story* was the wrong thing to build — an
        operator answered a block with an epic-scoped answer — so the epic gets rewritten
        rather than the story retried.
        """
        slug = self._story.story_slug
        self.logger.info("implementing %s%s", slug, self._progress(), extra={"activity": True})
        result = self.handoff(
            Dev,
            story=slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
        )
        if result.status == "replan":
            return Continue(result, self.replan, epic=epic, zero_diff=zero_diff,
                            notes=result.operator_notes)
        # `ready` and the YAML's `default:` arm, which was also `review`.
        return Continue(result, self.review, epic=epic, zero_diff=zero_diff, triage=triage)

    def review(self, epic: str = "", zero_diff: int = 0, triage: int = 0) -> Continue:
        """`review`: code review and reuse, with no branch on the outcome.

        The YAML declared `outputs: []` here and went straight to `docs`. That is not an
        oversight: the review flow either converges or fails the run from inside itself, so
        there is no verdict left for the caller to read. It also takes no `target_env` —
        review reads code, it does not run it.
        """
        slug = self._story.story_slug
        self.logger.info("reviewing %s%s", slug, self._progress(), extra={"activity": True})
        result = self.handoff(
            Review,
            story=slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
        )
        return Continue(result, self.document, epic=epic, zero_diff=zero_diff, triage=triage)

    def document(self, epic: str = "", zero_diff: int = 0, triage: int = 0) -> Continue:
        """`docs` + `decide_docs_outcome`: fold the story into the OKF book.

        `not_applicable` — a repo with no book — passes, because the alternative is that
        every repo without documentation cannot run the workflow. Anything else, blank
        included, is `documentation_failed`, which was a `type: fail`.
        """
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
        )
        self._require_documented(result, "story")
        return Continue(result, self.qa, epic=epic, zero_diff=zero_diff, triage=triage)

    def qa(self, epic: str = "", zero_diff: int = 0, triage: int = 0) -> Continue:
        """`qa_phase` + `decide_qa_outcome`: the four-way gate the whole loop turns on.

        `rescope` is the interesting arm. It sends the story back to `dev` carrying the
        triage budget the QA flow spent — the YAML passed `triage_scope_count` in as a bare
        rolling var and took it back out as an output for exactly this, and the re-entry
        deliberately bypasses the seed so the count persists across the loop.
        """
        result = self.handoff(
            Qa,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
            qa_stack_manifest=self.qa_stack_manifest,
            triage_scope_count=triage,
        )
        if result.status == "replan":
            return Continue(result, self.replan, epic=epic, zero_diff=zero_diff,
                            notes=result.operator_notes)
        if result.status == "rescope":
            self.logger.info("QA rescoped %s — back to dev", self._story.story_slug)
            return Continue(result, self.dev, epic=epic, zero_diff=zero_diff,
                            triage=result.triage_scope)
        if result.status == "exhausted":
            # `result.spent` names which budget actually ran out. `qa_rework` stays as the
            # fallback for a result that carries no name: the empty-story arm, which really
            # did spend nothing, and a checkpoint written before the field existed.
            return Continue(result, self.give_up, epic=epic, zero_diff=zero_diff,
                            attempts=result.spent or result.qa_rework)
        # `passed`, and the YAML's `default:` arm, which was also the drain.
        return Continue(result, self.drain, epic=epic, zero_diff=zero_diff)

    def replan(self, epic: str = "", zero_diff: int = 0, notes: str = "") -> Continue:
        """`replan_epic`: rewrite the epic from what the operator said, and re-select.

        The one turn in this graph that rewrites planning documents rather than code, which
        is why it is `power="high"`. `notes` is threaded rather than read back: it comes out
        of a sub-flow's return value, and a sub-flow's node records are in its own subscope.
        """
        self.logger.info("replanning epic %s", self._queue_epic(epic), extra={"activity": True})
        result = self.agent(
            "prompts/replan-epic.md",
            returns=ReplanResult,
            # high: highest blast radius in the workflow — it rewrites the epic, its
            # stories and the queue from one operator answer.
            power="high",
            add_dirs=self._dirs(),
            args={
                "epic": self._queue_epic(epic),
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "operator_context": notes,
            },
        )
        return Continue(result, self.select_story, epic=epic, zero_diff=zero_diff)

    def give_up(
        self, epic: str = "", zero_diff: int = 0, attempts: int | str = 0
    ) -> Continue:
        """`decide_qa_fail` → `failed_docs` → `qa_give_up`: QA is out of attempts.

        In story mode this is the end of the run and it is a failure — there is no next
        story to move on to. In epic mode the story is flagged, whatever *was* built is
        still documented (the `failed_docs` handoff, which is why documentation runs even on
        the failing path), and the loop takes the next story.

        `attempts` is a count only for a result that predates `QaFlowResult.spent`; normally
        it is that field's phrase ("3 QA-plan repair"), which is why it is stringified rather
        than counted here. Both forms read correctly in the marker commit and the flag.
        """
        if self.mode != "epic":
            raise WorkflowFailed(
                f"QA never passed for story {self._story.story_slug!r} after {attempts} "
                "attempt(s); giving up."
            )
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
        )
        self._require_documented(result, "failed story")
        self.call(
            flag_qa_failure,
            self._queue_epic(epic),
            self._story.story_slug,
            str(attempts),
            self._story.story_path,
            self._story.spec_dir,
            str(self.run_dir),
        )
        return Continue(result, self.select_story, epic=epic, zero_diff=zero_diff)

    # ── the backlog drain, nested inside the story ────────────────────────────────────

    def drain(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`decide_post_sentinel` + `select_fix_item` + `seed_fix_story` + the seeding.

        The draw does not touch the backlog file — a bullet leaves it only at `_fix_prune`
        or `_fix_flag`, at the far end of the iteration — so a resumed run re-draws the same
        item rather than skipping it.

        `prepare_fix_story` rather than `prepare_story`: the drain runs in the *parent's*
        run scope, so calling the same node would overwrite the record the commit below
        reads to know which story it is committing. The YAML registered the script twice for
        this reason and said so.
        """
        pick = self.call(select_fix_item, self.docs_path)
        if not pick.has_fix:
            return Continue(pick, self.finalize, epic=epic, zero_diff=zero_diff)
        self.logger.info("draining %s: %s", pick.fix_bullet_id, pick.fix_bullet_text)
        seed = self.call(
            seed_fix_story, pick.fix_bullet_id, pick.fix_bullet_text, "", "", self.docs_path
        )
        self.call(prepare_fix_story, self.docs_path, seed.story_slug, seed.epic)
        return Continue(seed, self.fix_plan, epic=epic, zero_diff=zero_diff)

    def fix_plan(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`plan_fix` + `decide_plan_fix`: plan the one-AC fix story."""
        fix = self._fix_story
        self.logger.info("planning %s", fix.story_slug, extra={"activity": True})
        result = self.agent(
            "prompts/plan-story.md",
            returns=PlanResult,
            # high: the same planner `dev` runs. A fix story is small, but the plan still
            # decides what production code gets touched.
            power="high",
            add_dirs=self._dirs(),
            args={"story_path": fix.story_path, "spec_dir": fix.spec_dir},
        )
        if result.status == "blocked":
            return self._fix_flag(result, epic, zero_diff)
        # The YAML's `default:` arm was `resolve_fix_impl_context`, not the give-up.
        return Continue(result, self.fix_dispatch, epic=epic, zero_diff=zero_diff)

    def fix_dispatch(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`resolve_fix_impl_context` + `branch_fix_code_repos` + `select_fix_layer`.

        `branch_code_repos` is called with `spec_dir` alone here, as the YAML's nested copy
        was — one argument where the `dev` flow passes more. A plan that dispatches no layer
        at all is legitimate (a fix that changes only documents) and goes straight to QA.
        """
        fix = self._fix_story
        self.call(resolve_impl_context, fix.spec_dir, self.target_env, self.docs_path)
        self.call(branch_code_repos, fix.spec_dir)
        pick = self.call(select_next_layer, fix.spec_dir, -1)
        if not pick.has_layer:
            self.logger.info("no service layer dispatched — checking the fix as it stands")
            return Continue(pick, self.fix_check, epic=epic, zero_diff=zero_diff)
        return Continue(pick, self.fix_implement, epic=epic, zero_diff=zero_diff)

    def fix_implement(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`implement_fix`: the first dispatched layer, and only it.

        Only it, because the nested drain has no loop back to `select_fix_layer` — the YAML
        wired `implement_fix` straight to `check_fix`. A fix whose plan dispatches two
        services gets one implemented and the other QA'd as if it had been. That is the
        YAML's behavior, preserved, and it is on loop 2's list.

        The three `impl_instruction_paths` / `qa_run_plan` / `qa_stack` arguments the `dev`
        flow passes are absent here for the same reason: the nested copy did not pass them.
        """
        layer = self._fix_layer
        fix = self._fix_story
        self.logger.info("implementing %s", layer.service or "the fix", extra={"activity": True})
        result = self.agent(
            "prompts/implement-plan.md",
            returns=ImplResult,
            # high: writes the production change.
            power="high",
            cwd=layer.cwd,
            add_dirs=self._dirs(),
            args={
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "plan_file": layer.plan_file,
                "service_path": layer.service_path,
                "service_type": layer.type,
                "verification": layer.verification,
            },
        )
        return Continue(result, self.fix_check, epic=epic, zero_diff=zero_diff)

    def fix_check(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`check_fix` + `decide_fix_check`: one QA turn on the drained item."""
        result = self._fix_qa()
        if result.status == "passed":
            return self._fix_prune(result, epic, zero_diff)
        return Continue(result, self.fix_apply, epic=epic, zero_diff=zero_diff,
                        notes=result.notes)

    def fix_apply(self, epic: str = "", zero_diff: int = 0, notes: str = "") -> Continue:
        """`apply_fix_once`: the single retry, on what the QA turn found.

        `notes` crosses from one agent turn to the next, and agent turns are not nodes, so
        it is threaded as a parameter — `self.output` cannot reach it.
        """
        fix = self._fix_story
        self.logger.info("applying QA fixes to the drained item", extra={"activity": True})
        result = self.agent(
            "prompts/apply-qa-fixes.md",
            returns=QaResult,
            # high: this retry has to converge, because there is not a second one.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "qa_dir": fix.qa_dir,
                "qa_notes": notes,
            },
        )
        return Continue(result, self.fix_recheck, epic=epic, zero_diff=zero_diff)

    def fix_recheck(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`recheck_fix` + `decide_recheck`: settle the item either way.

        Only `passed` prunes; everything else, blank included, flags the bullet and moves
        on. The drain never escalates to an operator — a stuck fix stays visible in the
        backlog and stops costing the loop anything.
        """
        result = self._fix_qa()
        if result.status == "passed":
            return self._fix_prune(result, epic, zero_diff)
        return self._fix_flag(result, epic, zero_diff)

    # ── the far end of a story ────────────────────────────────────────────────────────

    def finalize(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`decide_post_drain` + `final_docs` + `decide_final_docs`: document, then commit.

        A second `docs` pass, after the drain, so whatever the drain changed is in the book
        before the one commit that covers story and drained fixes together. Story mode goes
        to its own PR tail; epic mode commits and takes the next story.
        """
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
        )
        self._require_documented(result, "story (final pass)")
        if self.mode == "epic":
            return Continue(result, self.commit, epic=epic, zero_diff=zero_diff)
        return Continue(result, self.commit_pr)

    def commit(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`commit_story` + `decide_committed` + the zero-diff guard.

        A commit that found nothing to commit is not an error by itself — a story can be
        satisfied by what is already there — but three in a row is a loop that is not
        building anything, and the run stops rather than walking the whole epic producing
        nothing. The counter resets on any commit that landed.
        """
        story = self._story
        result = self.call(
            commit_story, self._queue_epic(epic), story.story_slug, story.spec_dir,
            story.story_path,
        )
        if result.committed:
            return Continue(result, self.select_story, epic=epic, zero_diff=0)
        zero_diff += 1
        self.logger.info(
            "%s committed nothing (%d/%d in a row)",
            story.story_slug, zero_diff, self.MAX_ZERO_DIFF_COMMITS,
        )
        if zero_diff >= self.MAX_ZERO_DIFF_COMMITS:
            raise WorkflowFailed(
                f"{zero_diff} stories in a row committed no changes — the loop is not "
                "making progress; stopping rather than walking the rest of the epic."
            )
        return Continue(result, self.select_story, epic=epic, zero_diff=zero_diff)

    def commit_pr(self) -> Done:
        """`commit_story_pr` + `open_story_pr`: story mode's end.

        The epic argument is blank, as the YAML's was: a story-mode run commits under the
        story's own identity. The branch to push and open the PR from comes from
        `branch_story`, the node that cut it — never re-derived from the slug here, which is
        how the two drifted once.
        """
        story = self._story
        branch = self.output(branch_story)
        self.call(commit_story, "", story.story_slug, story.spec_dir, story.story_path)
        return Done(
            self.call(
                open_story_pr,
                story.story_slug,
                branch.base_branch,
                story.story_path,
                story.spec_dir,
                branch.story_branch,
            )
        )

    # ── the epic's pull request, and the two gates behind it ──────────────────────────

    def open_pr(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """`prune_epic` + `open_pr` + `decide_gate`: the epic is done, so ship it.

        The pop comes *before* the PR deliberately: `open_pr` commits the docs it finds, so
        popping first is what puts the pruned queue file into the epic's own pull request
        instead of leaving it behind on the base branch.

        `should_gate` false — no remote, no token, no PR to gate on — skips straight to the
        next epic, which is what makes the whole workflow run offline. It is also how an
        epic whose branch carries a *set-aside* epic declines to ship: `open_pr` refuses to
        PR work that would merge past another epic's gate, and the queue advances anyway.
        """
        self.call(prune_epic, self._queue_epic(epic))
        gate = self.call(open_pr, self._queue_epic(epic), self.output(init_base).base_branch,
                         str(self.run_dir))
        if not gate.should_gate:
            self.logger.info("no PR to gate on for %s — taking the next epic", epic)
            return Continue(gate, self.select_epic, zero_diff=zero_diff)
        return Continue(gate, self.ci, epic=epic, zero_diff=zero_diff)

    def ci(
        self, epic: str = "", zero_diff: int = 0, ci_rework: int = 0, merge_rework: int = 0
    ) -> Continue | Await:
        """`await_ci` + `decide_ci` + `guard_ci`: is the epic's PR green?

        `unavailable` passes through to the merge, and that is the deliberate design rather
        than an oversight — offline, CI-less and read-blocked runs still complete, and the
        node logs the reason loudly at each site so it is never silent.

        Both counters are seeded by this state's own defaults, which is what `reset_ci` was:
        it seeded `ci_rework_count` *and* `merge_rework_count` in one node, because the
        merge budget also has to be fresh for each epic's PR.
        """
        gate = self.output(open_pr)
        checks = self.call(poll_pr_checks, "", gate.ci_epic)
        if checks.status in ("passed", "unavailable"):
            return Continue(checks, self.merge, epic=epic, zero_diff=zero_diff,
                            merge_rework=merge_rework)
        # `failed`, and the YAML's `default:`, which was also the guard.
        if ci_rework >= self.MAX_CI_REWORKS:
            return self._ci_gate(gate.ci_epic, ci_rework, checks.summary, epic, zero_diff,
                                 merge_rework)
        return Continue(checks, self.repair_ci, epic=epic, zero_diff=zero_diff,
                        ci_rework=ci_rework, merge_rework=merge_rework)

    def repair_ci(
        self, epic: str = "", zero_diff: int = 0, ci_rework: int = 0, merge_rework: int = 0
    ) -> Continue | Await:
        """`fix_ci` + `push_ci` + `decide_push` + `incr_ci`: one automated attempt at red CI.

        `repo=""` into the sub-flow means "iterate every workspace repo with failing CI",
        which is the YAML's own comment on the argument.

        A resolution that cannot be pushed can never make the next poll come back green, so
        `failed` escalates rather than spending another attempt on an unmoved branch head.
        """
        gate = self.output(open_pr)
        summary = self.output(poll_pr_checks).summary
        self.handoff(
            FixCi, repo="", branch=gate.ci_epic, ci_summary=summary, docs_path=self.docs_path
        )
        push = self.call(push_ci_fix, "", gate.ci_epic)
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.ci, epic=epic, zero_diff=zero_diff,
                            ci_rework=ci_rework + 1, merge_rework=merge_rework)
        return self._ci_gate(gate.ci_epic, ci_rework, summary, epic, zero_diff, merge_rework)

    def ci_operator(
        self, epic: str = "", zero_diff: int = 0, merge_rework: int = 0
    ) -> Continue:
        """The consume half of the CI gate: the operator acted, so poll again.

        The budget resets to zero, which is what `await-ci-operator.py` emitted — the
        operator's intervention buys a fresh set of automated attempts. Nothing here parses
        the answer: the YAML declared an `operator_input` output and no node ever read it,
        because what the operator did is visible in the next poll, not in what they typed.
        """
        self.logger.info("operator answered the CI gate — re-polling")
        return Continue(None, self.ci, epic=epic, zero_diff=zero_diff, ci_rework=0,
                        merge_rework=merge_rework)

    def merge(self, epic: str = "", zero_diff: int = 0, merge_rework: int = 0) -> Continue | Await:
        """`merge` + `decide_merge` + `guard_merge`: land the epic's PR.

        Best-effort, like the gate above it: with no origin, no token or no open PR the
        merge is a pass-through and HEAD is left on the epic branch, which is exactly what a
        local bind-mounted clone needs. `unavailable` therefore advances to the next epic.
        """
        gate = self.output(open_pr)
        outcome = self.call(merge_pr, gate.ci_epic, gate.ci_base)
        if outcome.merge_status in ("merged", "unavailable"):
            return Continue(outcome, self.select_epic, zero_diff=zero_diff)
        # `failed`, and the blank the YAML's pessimistic `default:` sent the same way.
        if merge_rework >= self.MAX_MERGE_REWORKS:
            return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework, epic, zero_diff)
        return Continue(outcome, self.fix_merge, epic=epic, zero_diff=zero_diff,
                        merge_rework=merge_rework)

    def fix_merge(
        self, epic: str = "", zero_diff: int = 0, merge_rework: int = 0
    ) -> Continue | Await:
        """`fix_merge` + `push_merge` + `decide_merge_push` + `incr_merge`.

        The second of the graph's two agent turns. `power="high"` for the reason the YAML
        gives: resolving conflicts on a divergent branch has high blast radius, and a wrong
        resolution corrupts code silently rather than failing loudly.
        """
        gate = self.output(open_pr)
        self.logger.info("resolving the merge for %s", gate.ci_epic, extra={"activity": True})
        self.agent(
            "prompts/fix-merge.md",
            returns=MergeFixResult,
            # high: a wrong conflict resolution silently corrupts code.
            power="high",
            add_dirs=self._dirs(),
            args={"ci_epic": gate.ci_epic, "ci_base": gate.ci_base},
        )
        push = self.call(push_ci_fix, "", gate.ci_epic)
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.merge, epic=epic, zero_diff=zero_diff,
                            merge_rework=merge_rework + 1)
        return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework, epic, zero_diff)

    def merge_operator(self, epic: str = "", zero_diff: int = 0) -> Continue:
        """The consume half of the merge gate: try the merge again, budget reset."""
        self.logger.info("operator answered the merge gate — re-merging")
        return Continue(None, self.merge, epic=epic, zero_diff=zero_diff, merge_rework=0)

    # ── routers and shared turns, none of them states ─────────────────────────────────

    def _ci_gate(
        self,
        ci_epic: str,
        attempts: int,
        summary: str,
        epic: str,
        zero_diff: int,
        merge_rework: int,
    ) -> Await:
        """`flag_ci_fail` + `await_ci_operator`: the automated attempts are spent.

        **This gate is human whatever `operator_mode` says**, and that is the YAML's own
        decision, recorded on the var: a red PR that cannot be pushed is an infrastructure
        or credential wall, not a question an agent can answer by trying harder.

        The note on the PR is best-effort — with no token or no open PR there is nothing to
        comment on — and the gate below it is the real escalation.
        """
        self.call(flag_ci_failure, ci_epic, str(attempts), summary)
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "ci-operator", ci_epic),
            f"CI is still failing on `{ci_epic}` after {attempts} automated attempt(s).\n\n"
            f"{summary or 'no summary available'}\n\n"
            "Fix it on the branch (or in the pipeline) and touch this file when the run "
            "should poll again.",
            self.ci_operator,
            epic=epic,
            zero_diff=zero_diff,
            merge_rework=merge_rework,
        )

    def _merge_gate(
        self, ci_epic: str, ci_base: str, attempts: int, epic: str, zero_diff: int
    ) -> Await:
        """`flag_merge_fail` + `await_merge_operator`: the merge-side twin of `_ci_gate`."""
        self.call(flag_merge_failure, ci_epic, ci_base, str(attempts))
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "merge-operator", ci_epic),
            f"`{ci_epic}` will not merge into `{ci_base}` after {attempts} automated "
            "attempt(s).\n\nResolve it and touch this file when the run should try again.",
            self.merge_operator,
            epic=epic,
            zero_diff=zero_diff,
        )

    def _fix_prune(self, result: object, epic: str, zero_diff: int) -> Continue:
        """`prune_fix_item`: the drained fix shipped, so its bullet leaves the backlog."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.call(prune_fix_item, bullet, self.docs_path)
        return Continue(result, self.drain, epic=epic, zero_diff=zero_diff)

    def _fix_flag(self, result: object, epic: str, zero_diff: int) -> Continue:
        """`fix_give_up`: annotate the bullet in place and draw the next one."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.logger.info("flagging %s as blocked", bullet)
        self.call(mark_fix_blocked, bullet, BLOCKED_NOTE, self.docs_path)
        return Continue(result, self.drain, epic=epic, zero_diff=zero_diff)

    def _fix_qa(self) -> QaResult:
        """`qa-fix-item.md`, which `check_fix` and `recheck_fix` ran with identical arguments.

        Not `qa-story.md` — see `fix/flow.py`'s `_qa` for why that prompt cannot answer this
        turn. The nested drain runs the same one.
        """
        fix = self._fix_story
        self.logger.info("checking %s", fix.story_slug, extra={"activity": True})
        return self.agent(
            "prompts/qa-fix-item.md",
            returns=QaResult,
            # high: the drain has no QA plan, no evidence gate and no audit behind it —
            # this turn is the whole verdict on the fix.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "qa_dir": fix.qa_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
            },
        )

    def _require_documented(self, result: object, what: str) -> None:
        """`decide_docs_outcome`, shared by the three `docs` handoffs that branch alike."""
        status = getattr(result, "status", "")
        if status not in ("passed", "not_applicable"):
            raise WorkflowFailed(
                f"documenting the {what} {self._story.story_slug!r} failed: "
                f"{getattr(result, 'notes', '') or 'no notes'}"
            )

    def _story_epic(self, epic: str) -> str:
        """`prepare_story.story_epic or select_story.epic or epic` — the *story's* epic.

        `prepare_story` discovers it by scanning when story mode was handed a bare slug, so
        its answer wins; the queue epic is the fall-back. `select_story.epic` is the middle
        rung in the YAML and is skipped here because it is the value `epic` already carries:
        the pick was made *for* that epic.
        """
        return self._story.story_epic or epic or self.epic

    def _queue_epic(self, epic: str) -> str:
        """`select_epic.epic or epic` — the epic the *queue* is working.

        Distinct from `_story_epic` and not interchangeable with it: this one is blank in
        story mode unless the run was invoked with an epic, which is what the YAML rendered
        there too.
        """
        return epic or self.epic

    def _progress(self) -> str:
        """The ` · 3/7` suffix the two `activity:` templates appended when there was one."""
        try:
            progress = self.output(select_story).progress
        except NodeNotRunError:
            return ""
        return f" · {progress}" if progress else ""

    def _dirs(self) -> list[str]:
        """`{{ workspace_dirs }}` — the `add_dirs` every agent turn in this graph was given."""
        return list(self.ctx.dirs)

    @property
    def _story(self) -> StoryPaths:
        """The story this iteration is building, as `prepare_story` resolved it."""
        return self.output(prepare_story)

    @property
    def _fix_story(self) -> StoryPaths:
        """The drained item's story — a *different* node id, see `drain`."""
        return self.output(prepare_fix_story)

    @property
    def _fix_layer(self) -> DispatchEntry:
        """The one service layer the drained fix implements, as `select_fix_layer` picked it."""
        return self.output(select_next_layer).layer


workflow = (
    Registry("coder")
    .add_blueprints(blueprint)
    # The eight `flows:` blocks, by the name `workhorse-coder run <name>` takes. Five are
    # only ever reached by `handoff`; `genesis`, `dream` and `fix` are entered directly,
    # which is the whole reason they need names here.
    .add_flows(
        genesis=Genesis,
        dev=Dev,
        review=Review,
        docs=Docs,
        qa=Qa,
        fix=Fix,
        fix_ci=FixCi,
        dream=Dream,
    )
    .stub_agents(
        {
            # Keyed by prompt STEM: the reply that makes a dry run *progress* past each
            # gate rather than taking the pessimistic blank arm.
            "plan-story": {"status": "complete"},
            "refine-plan": {"status": "complete"},
            "implement-plan": {"status": "complete"},
            "check-code-reuse": {"status": "ok"},
            "code-reuse": {"status": "ok"},
            "fix-lint": {"status": "fixed"},
            "code-review": {"status": "approved"},
            "review-implementation": {"status": "approved"},
            "apply-review": {"status": "applied"},
            "document-story": {"status": "passed"},
            "review-story-documentation": {"status": "passed"},
            "plan-qa": {"status": "complete"},
            "review-qa-plan": {"status": "approved"},
            "qa-story": {"status": "passed"},
            "audit-qa": {"status": "passed"},
            "apply-qa-fixes": {"status": "passed"},
            "triage-qa": {"status": "resolved"},
            "repair-qa-context": {"status": "repaired"},
            "report-qa-dev": {"status": "reported"},
            "report-qa-dev-pass": {"status": "reported"},
            "fix-regression": {"status": "fixed"},
            "setup-fix": {"status": "fixed"},
            "fix-ci": {"status": "fixed"},
            "fix-merge": {"status": "resolved"},
            "replan-epic": {"status": "complete"},
            "resolve-operator": {"decision": "answered"},
            "apply-genesis-conventions": {"status": "complete"},
            "fix-genesis": {"status": "complete"},
            "dream-reflect": {"status": "complete"},
        }
    )
)
main = console_script(workflow.entry_point(Coder))


__all__ = ["Coder", "main", "workflow"]
