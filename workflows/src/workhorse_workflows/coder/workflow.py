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

**The two counters are parameters.** `ci_rework` and `merge_rework` both live inside the
PR cluster, which is the whole distance either of them travels. There was a third —
`zero_diff`, consecutive stories whose commit found nothing to commit — and it is gone:
the workflow no longer commits on the agent's behalf, so "this story produced no diff" is
no longer a thing this graph is in a position to observe. What replaced it is not a
smaller counter but the check that the agent committed at all, in `commit`, and the two
gates that hang off a tree it left dirty.

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

from pathlib import Path
from typing import Any, ClassVar

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
from workhorse_workflows.coder.shared import paths, roles
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
from workhorse_workflows.coder.shared.ci import epic_branch, poll_pr_checks, push_ci_fix
from workhorse_workflows.coder.shared.worktree import snapshot_worktree_state
from workhorse_workflows.kit.telemetry import counter_labels
from workhorse_workflows.coder.shared.dev import (
    branch_code_repos,
    plan_summary,
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
    check_repos_clean,
    commit_story,
    flag_epic_blocked,
    init_base,
    prune_epic,
    select_epic,
    select_story,
    stamp_story_passed,
)
from workhorse_workflows.coder.shared.story import (
    prepare_fix_story,
    prepare_story,
    resolve_workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry, ImplResult, PlanResult
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.pr import MergeFixResult
from workhorse_workflows.coder.shared.schemas.qa import QaResult
from workhorse_workflows.coder.shared.schemas.queue import ReplanResult, WorktreeSettled
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs


_QA_RETRY_ARTIFACTS = {
    "qa_plan.py",
    "qa-plan.md",
    "qa-plan.yml",
    "qa-plan.yaml",
    "visual-verdicts.json",
}


def _docs_changed_qa_retry_artifact(result: DocsResult, spec_dir: str) -> bool:
    spec = Path(spec_dir).as_posix().rstrip("/")
    specs = {spec}
    marker = "/docs/specs/"
    if marker in spec:
        specs.add(f"docs/specs/{spec.split(marker, 1)[1]}")
    for node in result.authored_nodes:
        path = node.split("#", 1)[0]
        if Path(path).name not in _QA_RETRY_ARTIFACTS:
            continue
        if path.startswith("docs/specs/"):
            return True
        if any(path.startswith(f"{candidate}/") for candidate in specs):
            return True
    return False


def _documented(result: DocsResult) -> bool:
    """`decide_docs_outcome`: did the book end up true of this story?

    `not_applicable` — a repo with no book — passes, because the alternative is that every
    repo without documentation cannot run the workflow. Everything else, blank included, is
    the pessimistic arm the YAML's `default:` took, and every one of them now goes to the
    operator rather than one of them ending the run.
    """
    return result.status in ("passed", "not_applicable")


def _docs_notes(result: DocsResult, what: str) -> str:
    """The reason the gate shows the operator, with the verdict that produced it named.

    A `blocked` result says why in `notes`; a `failed` one often does not, and "no reason
    given" against a named status is more use at the gate than a bare empty string.
    """
    return f"{result.status or 'no status'} — {result.notes or 'no reason given'} ({what})"


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
    #: `auto` lets the sub-flows resolve their own blocks; `human` escalates to a human.
    #: The shipped legacy value `operator` remains an alias for `human`.
    #: It does not reach the CI gate, which is always human — see `_ci_gate`.
    operator_mode: str = "auto"
    #: Which environment QA runs against, passed through to `dev`, `docs` and `qa`.
    target_env: str = "local"
    #: The QA stack manifest `qa` reads to bring services up.
    qa_stack_manifest: str = "qa-stack.yml"
    #: How long a story's QA lane is *expected* to spend inside agent turns, and how much of
    #: that the plan lane is expected to take. Advisory — crossing one is logged, never
    #: terminal. Restated here — as `target_env` and `operator_mode` are — only so an operator
    #: can set them once on the run rather than per story; `Qa.qa_lane_budget_s` is where the
    #: numbers are argued, and the two defaults move together.
    qa_lane_budget_s: int = 3300
    plan_lane_budget_s: int = 2400

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one, which is what carries them into the story sub-flows:
    #: a `handoff` constructs a fresh workflow, so nothing crosses that boundary unless
    #: something puts it there. See `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: `max_ci_reworks` — automated attempts at a red PR before the operator is asked.
    MAX_CI_REWORKS: ClassVar[int] = 3
    #: `max_merge_reworks` — automated attempts at a conflicted merge, ditto.
    MAX_MERGE_REWORKS: ClassVar[int] = 2

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

    #: The graph's own budgets, both of them inside the PR cluster.
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("ci_rework", "merge_rework")

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "coder", self.BUDGET_LABELS)

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

    def select_epic(self) -> Continue | Done:
        """`select_epic` + `decide_epic` + `branch_epic`: take the front of the queue.

        The branch is cut in the same state as the pick because nothing branches between
        them. An empty queue is the run's ordinary end, not a failure.
        """
        pick = self.call(select_epic, self.docs_path, str(self.run_dir))
        if not pick.has_epic:
            self.logger.info("no epic to work: %s", pick.reason)
            return Done(pick)
        base = self.output(init_base).base_branch
        self.call(branch_epic, pick.epic, base, str(self.run_dir))
        return Continue(pick, self.select_story, epic=pick.epic)

    def select_story(self, epic: str = "") -> Continue:
        """`select_story` + `decide_story`: the next unimplemented story of this epic.

        Three outcomes, and the third is the one worth naming: `blocked` does *not* fail the
        run. It flags the epic, and goes back to `select_epic` for the next one — a blocked
        epic is a planning problem, and stopping the whole loop over it would strand every
        other epic behind it.
        """
        pick = self.call(select_story, epic, self.docs_path, str(self.run_dir))
        if pick.story_outcome == "story":
            return Continue(pick, self.prepare, slug=pick.story_slug, epic=epic)
        if pick.story_outcome == "done":
            self.logger.info("epic %s has no stories left — opening its PR", epic)
            return Continue(pick, self.open_pr, epic=epic)
        # `blocked`, and the YAML's `default:` arm, which pointed at the same node.
        self.call(flag_epic_blocked, epic, str(self.run_dir), pick.reason)
        return Continue(pick, self.select_epic)

    # ── one story ─────────────────────────────────────────────────────────────────────

    def prepare(self, slug: str = "", epic: str = "") -> Continue:
        """`prepare_story` + `init_triage_counter`: resolve the slug to paths.

        The triage budget is seeded here rather than inside `qa` for the reason the YAML
        gives at `init_triage_counter`: it has to survive across QA *entries*, because a
        rescope sends the story back to `dev` and re-enters QA, and a budget that reset on
        each entry would never be spent. That is why `triage` is threaded through the four
        pipeline states below instead of starting at zero in `qa`.

        `snapshot_worktree_state` reads the worktree *before* the first dev turn, and
        `document` hands the reading to the docs flow. The grounding gate diffs
        `HEAD..WORKTREE`, so without it a story that died before its commit — a docs
        failure, a QA give-up, a crash — leaves production code in the tree that every
        story selected after it is then held responsible for documenting.
        """
        self.call(snapshot_worktree_state, self.docs_path)
        story = self.call(prepare_story, self.docs_path, slug, epic)
        self.logger.info("preparing %s%s", slug, self._progress(), extra={"activity": True})
        # No `session_id` here: a new story starts a fresh backbone chain, which is
        # `dev`'s default when none is threaded in.
        return Continue(story, self.dev, epic=epic)

    def dev(self, epic: str = "", triage: int = 0, session_id: str = "") -> Continue:
        """`dev` + `decide_dev`: plan and implement the story.

        `replan` is the sub-flow saying the *story* was the wrong thing to build — an
        operator answered a block with an epic-scoped answer — so the epic gets rewritten
        rather than the story retried.

        `session_id` is the story's backbone conversation — empty on a fresh story, or the
        chain a `rescope` return from `qa` handed back. It crosses into `Dev` and the id
        that chain ends up on is threaded into `review`, past `Review` (which never shares
        this conversation — see `review`'s docstring), and on into `document`.
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
            session_id=session_id,
        )
        if result.status == "replan":
            return Continue(result, self.replan, epic=epic, notes=result.operator_notes)
        # `ready` and the YAML's `default:` arm, which was also `review`.
        return Continue(
            result,
            self.review,
            epic=epic,
            triage=triage,
            session_id=result.session_id,
            session_turns=result.session_turns,
        )

    def review(
        self, epic: str = "", triage: int = 0, session_id: str = "", session_turns: int = 0
    ) -> Continue:
        """`review`: code review and reuse, with no branch on the outcome.

        The YAML declared `outputs: []` here and went straight to `docs`. That is not an
        oversight: the review flow either converges or fails the run from inside itself, so
        there is no verdict left for the caller to read. It also takes no `target_env` —
        review reads code, it does not run it.

        `session_id` is handed to `Review` *and* passes through unchanged to `document`.
        The lane judges the diff cold — the review turns open their own conversation, so no
        reviewer inherits what `dev` said about its own work — but the turns that then
        *change* the code rejoin the implementer's conversation, which is the whole of what
        this thread buys (see `Review`'s docstring). Nothing is read back from its result:
        what reaches `document` is exactly what `dev` produced.
        """
        slug = self._story.story_slug
        self.logger.info("reviewing %s%s", slug, self._progress(), extra={"activity": True})
        result = self.handoff(
            Review,
            story=slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
            session_id=session_id,
            session_turns=session_turns,
        )
        return Continue(result, self.document, epic=epic, triage=triage, session_id=session_id)

    def document(
        self, epic: str = "", triage: int = 0, session_id: str = ""
    ) -> Continue:
        """`docs` + `decide_docs_outcome`: fold the story into the OKF book.

        `not_applicable` — a repo with no book — passes, because the alternative is that
        every repo without documentation cannot run the workflow. Anything else, blank
        included, is `documentation_failed`, which was a `type: fail`.

        `preexisting` is `prepare`'s snapshot, so the grounding gate can tell this story's
        changes apart from whatever was already dirty when it started; see `_preexisting`
        for why a run that predates the snapshot passes nothing rather than failing.

        A `blocked` answer and a `failed` one both route to `blocked_docs`. They read
        differently — one is the book refusing the code, the other is the documenting turn
        not finishing — and neither is answerable by trying again unchanged, so both park
        for the operator rather than one parking and the other ending the run.

        `session_id` is the story's backbone chain, carried past `review` from `dev`. Both
        exits thread the id `Docs` ends up on — the blocked one too, because a resume lands
        back at this same state (see `blocked_docs`) and should reopen the conversation the
        first pass left, not a fresh one.
        """
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
            preexisting=self._preexisting(),
            operator_mode=self.operator_mode,
            session_id=session_id,
        )
        if not _documented(result):
            return Continue(result, self.blocked_docs, epic=epic, triage=triage,
                            notes=_docs_notes(result, "story"), session_id=result.session_id)
        return Continue(result, self.qa, epic=epic, triage=triage, session_id=result.session_id)

    def blocked_docs(
        self,
        epic: str = "",
        triage: int = 0,
        notes: str = "",
        resume_at: str = "document",
        attempts: int | str = 0,
        session_id: str = "",
    ) -> Await:
        """The docs phase would not pass the story: the run parks for a human, not ends failed.

        `give_up`'s counterpart for the other verdict that ends a story unfinished — but a
        block is answerable and a QA-on-`target_env="dev"` report is not, so the two no
        longer end the same way. A block is the author or the reviewer saying the book
        cannot be made true of this code — in the run that forced this state, because the
        implementation contradicted a fail-closed guarantee its own plan required — and the
        `Docs` sub-flow's own resolver (`_blocked`) already had its say before returning
        here at all, in the author's stead. What is left once that has happened is a human
        decision, which is exactly what `Await` is for: the same "no cap on escalations"
        every other operator gate in this file gets, not a fourth way for a state to end.
        Committing behind a `[DOCS BLOCKED — needs manual review]` marker and taking the
        next story is the shape this replaces — it read as progress in `git log` while the
        story's own reviewer had refused it, and the run being checkpointed here costs an
        operator no more than that marker would have.

        No re-entry into `Docs` directly, which is still what separates this from a plain
        rework lap: the flow that just refused would refuse again on the same grounds. A
        resume only pays off once the operator has changed the code, the spec or the plan,
        so it lands back at `document` to have the sub-flow judge the fix fresh.

        `notes` carries the refusal's reason into the escalation, because it is the only
        place it is written down — unlike a QA give-up, there is no `qa.md` to point at.

        `resume_at` names which of the three `Docs` handoffs raised this, because they sit
        at different points in the story and a resume has to land back at the one it left.
        Sending `finalize`'s block back to `document` would re-run QA on a story that had
        already passed it; sending `give_up`'s there would restart a story the run had
        already stopped implementing.
        """
        slug = self._story.story_slug
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "docs-operator", slug),
            f"Documentation did not pass for story {slug!r}: {notes or 'no reason given'}.\n\n"
            "Fix the code, the spec or the plan so the book can be made true of it, and "
            "touch this file when the run should try again.",
            self.docs_operator,
            epic=epic,
            triage=triage,
            resume_at=resume_at,
            attempts=attempts,
            session_id=session_id,
        )

    def docs_operator(
        self,
        epic: str = "",
        triage: int = 0,
        resume_at: str = "document",
        attempts: int | str = 0,
        session_id: str = "",
    ) -> Continue:
        """The consume half of the docs gate: re-document on the operator's fix."""
        self.logger.info(
            "operator answered the docs gate — redocumenting %s", self._story.story_slug
        )
        if resume_at == "give_up":
            return Continue(None, self.give_up, epic=epic, attempts=attempts, session_id=session_id)
        if resume_at == "finalize":
            return Continue(None, self.finalize, epic=epic, session_id=session_id)
        return Continue(None, self.document, epic=epic, triage=triage, session_id=session_id)

    def qa(self, epic: str = "", triage: int = 0, session_id: str = "") -> Continue:
        """`qa_phase` + `decide_qa_outcome`: the four-way gate the whole loop turns on.

        `rescope` is the interesting arm. It sends the story back to `dev` carrying the
        triage budget the QA flow spent — the YAML passed `triage_scope_count` in as a bare
        rolling var and took it back out as an output for exactly this, and the re-entry
        deliberately bypasses the seed so the count persists across the loop.

        `preexisting` goes in for the same reason `document` takes it: QA builds its
        obligation packet from the same `HEAD..WORKTREE` diff, so without the snapshot an
        abandoned story's uncommitted code becomes scenarios this story has to write.

        `session_id` is the story's backbone chain, carried from `document`. A `rescope`
        hands it straight back into `dev` — the same story, the same conversation. A
        `passed` verdict threads it through the backlog drain (an unrelated, differently
        shaped unit of work whose own turns never share it) purely so it survives to reach
        `finalize`'s recheck; the next story `select_story` picks up afterward gets none of
        it, because nothing past `commit` threads it further.
        """
        result = self.handoff(
            Qa,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
            qa_stack_manifest=self.qa_stack_manifest,
            qa_lane_budget_s=self.qa_lane_budget_s,
            plan_lane_budget_s=self.plan_lane_budget_s,
            triage_scope_count=triage,
            preexisting=self._preexisting(),
            session_id=session_id,
        )
        if result.status == "replan":
            return Continue(result, self.replan, epic=epic, notes=result.operator_notes)
        if result.status == "rescope":
            self.logger.info("QA rescoped %s — back to dev", self._story.story_slug)
            return Continue(
                result, self.dev, epic=epic, triage=result.triage_scope,
                session_id=result.session_id,
            )
        if result.status == "refix":
            # Triage found the *product* wrong. The QA lane's fixer is briefed on a QA report
            # and told not to broaden behaviour, so it patches the surface the scenario
            # touched; the dev lane owns product code and re-enters review and QA behind
            # itself. The findings are on disk in the story's `qa.md`, which is what `dev`
            # reads — there is no brief to thread through this call.
            self.logger.info(
                "QA found a product defect in %s — back to dev", self._story.story_slug
            )
            return Continue(
                result, self.dev, epic=epic, triage=result.triage_scope,
                session_id=result.session_id,
            )
        if result.status == "inconclusive":
            # The only mode that still lands here is `target_env="dev"`: every other
            # exhaustion now escalates to the operator gate inside the QA sub-flow itself
            # and never returns with this status at all.
            return Continue(
                result, self.give_up, epic=epic, attempts=result.qa_rework,
                session_id=result.session_id,
            )
        # `passed`, and the YAML's `default:` arm, which was also the drain.
        return Continue(
            result,
            self.drain,
            epic=epic,
            docs_recheck_required=result.docs_recheck_required,
            session_id=result.session_id,
        )

    def replan(self, epic: str = "", notes: str = "") -> Continue:
        """`replan_epic`: rewrite the epic from what the operator said, and re-select.

        The one turn in this graph that rewrites planning documents rather than code, which
        is why it is `power="high"`. `notes` is threaded rather than read back: it comes out
        of a sub-flow's return value, and a sub-flow's node records are in its own subscope.
        """
        self.logger.info("replanning epic %s", self._queue_epic(epic), extra={"activity": True})
        turn = roles.turn("replan-epic", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=ReplanResult,
            # high: highest blast radius in the workflow — it rewrites the epic, its
            # stories and the queue from one operator answer.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "epic": self._queue_epic(epic),
                "story_slug": self._story.story_slug,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "operator_context": notes,
            },
        )
        return Continue(result, self.select_story, epic=epic)

    def give_up(
        self, epic: str = "", attempts: int | str = 0, session_id: str = ""
    ) -> Continue:
        """`decide_qa_fail` → `failed_docs`: the dev-target report ends here; the run stops.

        Real QA exhaustion no longer reaches this method: every budget the QA sub-flow can
        run out of now escalates to the operator gate and parks the run there instead of
        returning a terminal result. The only status that still lands here is
        `target_env="dev"`'s `report_dev` — that mode does not own the code, so there is no
        operator-answerable question to gate on, and reporting the findings *is* the terminal
        action. Failing the run (rather than committing behind a `[QA FAILED — needs manual
        review]` marker and taking the next story) is still the right call for that report:
        the marker-and-continue shape used to read as progress in `git log` while the next
        story built on a baseline QA rejected, and the review it asked for never happened
        because nothing stopped to demand it. The run is checkpointed, so stopping costs
        nothing an operator cannot resume — patch the plan or the workflow and re-enter at
        this node.

        Documentation still runs first (the `failed_docs` handoff): whatever *was* built is
        described before the run dies, and the re-entry below exists because documenting can
        legitimately change what QA reported.

        `attempts` names the rework count in the failure message, because the operator
        reading it is as often a `/loop` tick as a human, and "needs manual review" is not
        something a poller can act on.
        """
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
            preexisting=self._preexisting(),
            operator_mode=self.operator_mode,
            session_id=session_id,
        )
        if not _documented(result):
            return Continue(
                result,
                self.blocked_docs,
                epic=epic,
                notes=_docs_notes(result, "failed story"),
                resume_at="give_up",
                attempts=attempts,
                session_id=result.session_id,
            )
        if _docs_changed_qa_retry_artifact(result, self._story.spec_dir):
            self.logger.info(
                "documentation changed QA retry artifacts for %s — rerunning QA",
                self._story.story_slug,
                extra={"activity": True},
            )
            return Continue(result, self.qa, epic=epic, session_id=result.session_id)
        raise WorkflowFailed(
            f"QA never passed for story {self._story.story_slug!r} after {attempts} "
            f"attempt(s); nothing was committed for this story.",
            failure_class="qa-give-up",
            artifacts={"spec_dir": str(self._story.spec_dir)},
        )

    # ── the backlog drain, nested inside the story ────────────────────────────────────

    def drain(
        self, epic: str = "", docs_recheck_required: bool = True, session_id: str = ""
    ) -> Continue:
        """`decide_post_sentinel` + `select_fix_item` + `seed_fix_story` + the seeding.

        The draw does not touch the backlog file — a bullet leaves it only at `_fix_prune`
        or `_fix_flag`, at the far end of the iteration — so a resumed run re-draws the same
        item rather than skipping it.

        `prepare_fix_story` rather than `prepare_story`: the drain runs in the *parent's*
        run scope, so calling the same node would overwrite the record the commit below
        reads to know which story it is committing. The YAML registered the script twice for
        this reason and said so.

        `session_id` is only a pass-through here: the drain works a different, unnamed fix
        story (`self._fix_story`, not `self._story`), and none of its own turns below share
        it — they never have, laps or not. It rides through this whole loop only so it
        survives to reach `finalize`'s recheck of the *original* story once the backlog is
        empty.
        """
        pick = self.call(select_fix_item, self.docs_path)
        if not pick.has_fix:
            return Continue(
                pick,
                self.finalize,
                epic=epic,
                docs_recheck_required=docs_recheck_required,
                session_id=session_id,
            )
        self.logger.info("draining %s: %s", pick.fix_bullet_id, pick.fix_bullet_text)
        seed = self.call(
            seed_fix_story, pick.fix_bullet_id, pick.fix_bullet_text, "", "", self.docs_path
        )
        self.call(prepare_fix_story, self.docs_path, seed.story_slug, seed.epic)
        return Continue(seed, self.fix_plan, epic=epic, session_id=session_id)

    def fix_plan(self, epic: str = "", session_id: str = "") -> Continue:
        """`plan_fix` + `decide_plan_fix`: plan the one-AC fix story."""
        fix = self._fix_story
        self.logger.info("planning %s", fix.story_slug, extra={"activity": True})
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
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "story_slug": fix.story_slug,
                "epic": fix.story_epic,
            },
        )
        if result.status == "blocked":
            return self._fix_flag(result, epic, session_id)
        # The YAML's `default:` arm was `resolve_fix_impl_context`, not the give-up.
        return Continue(result, self.fix_dispatch, epic=epic, session_id=session_id)

    def fix_dispatch(self, epic: str = "", session_id: str = "") -> Continue:
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
            return Continue(pick, self.fix_check, epic=epic, session_id=session_id)
        return Continue(pick, self.fix_implement, epic=epic, session_id=session_id)

    def fix_implement(self, epic: str = "", session_id: str = "") -> Continue:
        """`implement_fix`: the first dispatched layer, and only it.

        Only it, because the nested drain has no loop back to `select_fix_layer` — the YAML
        wired `implement_fix` straight to `check_fix`. A fix whose plan dispatches two
        services gets one implemented and the other QA'd as if it had been. That is the
        YAML's behavior, preserved, and it is on loop 2's list.

        The three `impl_instruction_paths` / `qa_run_plan` / `verification_setup` arguments the `dev`
        flow passes are absent here for the same reason: the nested copy did not pass them.
        """
        layer = self._fix_layer
        fix = self._fix_story
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
                "story_slug": fix.story_slug,
                "epic": fix.story_epic,
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "plan_file": layer.plan_file,
                "service_path": layer.service_path,
                "service_type": layer.type,
                "verification": layer.verification,
            },
        )
        return Continue(result, self.fix_check, epic=epic, session_id=session_id)

    def fix_check(self, epic: str = "", session_id: str = "") -> Continue:
        """`check_fix` + `decide_fix_check`: one QA turn on the drained item."""
        result = self._fix_qa()
        if result.status == "passed":
            return self._fix_prune(result, epic, session_id)
        return Continue(result, self.fix_apply, epic=epic, notes=result.notes, session_id=session_id)

    def fix_apply(self, epic: str = "", notes: str = "", session_id: str = "") -> Continue:
        """`apply_fix_once`: the single retry, on what the QA turn found.

        `notes` crosses from one agent turn to the next, and agent turns are not nodes, so
        it is threaded as a parameter — `self.output` cannot reach it.

        No session chain, unlike the QA lane's fix loop: there is exactly one lap here, so
        there is no second turn for a chain to hand anything to.
        """
        fix = self._fix_story
        self.logger.info("applying QA fixes to the drained item", extra={"activity": True})
        turn = roles.turn("apply-qa-fixes", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=QaResult,
            # high: this retry has to converge, because there is not a second one.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": fix.story_slug,
                "epic": fix.story_epic,
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "qa_dir": fix.qa_dir,
                "qa_notes": notes,
            },
        )
        return Continue(result, self.fix_recheck, epic=epic, session_id=session_id)

    def fix_recheck(self, epic: str = "", session_id: str = "") -> Continue:
        """`recheck_fix` + `decide_recheck`: settle the item either way.

        Only `passed` prunes; everything else, blank included, flags the bullet and moves
        on. The drain never escalates to an operator — a stuck fix stays visible in the
        backlog and stops costing the loop anything.
        """
        result = self._fix_qa()
        if result.status == "passed":
            return self._fix_prune(result, epic, session_id)
        return self._fix_flag(result, epic, session_id)

    # ── the far end of a story ────────────────────────────────────────────────────────

    def finalize(
        self, epic: str = "", docs_recheck_required: bool = True, session_id: str = ""
    ) -> Continue:
        """Recheck documentation after a mutation, then commit the story.

        A clean QA pass needs no redundant second Docs handoff. QA repairs and the nested
        backlog drain set a monotonic taint; only those paths re-enter Docs. Defaults are
        fail-closed so an old checkpoint with no taint still performs the recheck.

        `session_id` is the story's backbone chain, threaded all the way from `document`
        through `qa` and the backlog drain. Nothing downstream of this state needs it —
        `commit`/`commit_pr` lead to the next story, which starts its own chain.
        """
        if not docs_recheck_required:
            if self.mode == "epic":
                return Continue(None, self.commit, epic=epic)
            return Continue(None, self.commit_pr)
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
            preexisting=self._preexisting(),
            operator_mode=self.operator_mode,
            session_id=session_id,
        )
        if not _documented(result):
            return Continue(
                result,
                self.blocked_docs,
                epic=epic,
                notes=_docs_notes(result, "story (final pass)"),
                resume_at="finalize",
                session_id=result.session_id,
            )
        if self.mode == "epic":
            return Continue(result, self.commit, epic=epic)
        return Continue(result, self.commit_pr)

    def commit(self, epic: str = "", dirty_laps: int = 0) -> Continue | Await:
        """`check_repos_clean` + `stamp_story_passed`: the story's work is recorded, or it parks.

        The workflow used to commit for the agent — `git commit -a` per affected repo,
        under a subject this file composed from the story's title. That decided the
        message, the scope and the *boundary* of every story commit from outside the work
        that produced it, and swept whatever else was on disk into whichever story
        happened to finish next. The agent knows all three and commits as it goes now; what
        is left here is the check that it did, which is the failure the sweep was hiding.

        A dirty tree is not an error on the first reading — it is work nobody recorded, and
        the agent that wrote it is the one who can say what belongs where. So the first one
        buys a chained `settle` lap and the second parks for the operator, because a second
        identical reading means the turn that was asked to record it declined twice, and
        committing a stranger's changes under this story's name is not the workflow's call
        to make.

        The stamp stays a node on this path, and stays *after* the check. Story selection
        reads the status line rather than the git log, so a story stamped over work that is
        still only on disk reads as done and is never selected again.
        """
        story = self._story
        state = self.call(
            check_repos_clean, story.story_slug, story.spec_dir, list(self._preexisting())
        )
        if not state.clean:
            if dirty_laps:
                return self._dirty_gate(state.dirty, epic)
            return Continue(state, self.settle, epic=epic, dirty_laps=1)
        self.reset_session(self._settle_chain())
        result = self.call(
            stamp_story_passed, self._queue_epic(epic), story.story_slug, story.story_path
        )
        return Continue(result, self.select_story, epic=epic)

    def settle(self, epic: str = "", dirty_laps: int = 1) -> Continue | Await:
        """One chained turn to record what the story left on disk, then re-read the tree.

        Chained deliberately, and to the story rather than the run: this is the same agent
        being told that what it just built is not in a commit, and the conversation that
        built it is the one that knows which of those paths were its own. A fresh context
        would be handed a list of paths and no way to tell the story's work from the
        operator's.

        It does not decide anything. `commit` re-reads the tree afterwards either way, so a
        turn that reports success it did not achieve buys one more reading, not a pass.
        """
        state = self.output(check_repos_clean)
        story = self._story
        self.logger.info(
            "asking %s to settle %d uncommitted path(s)", story.story_slug, len(state.dirty),
            extra={"activity": True},
        )
        result = self.agent(
            "prompts/settle-worktree.md",
            # medium: deciding what a diff belongs to and writing its commit message, with
            # no design left to do — the work itself is already on disk.
            power="medium",
            returns=WorktreeSettled,
            add_dirs=self._dirs(),
            args={
                "story_path": story.story_path,
                "spec_dir": story.spec_dir,
                "story_slug": story.story_slug,
                "epic": self._queue_epic(epic),
                "dirty_paths": "\n".join(state.dirty),
            },
            session=self._settle_chain(),
        )
        if result.blocked:
            return self._dirty_gate(state.dirty, epic, notes=result.notes)
        return Continue(result, self.commit, epic=epic, dirty_laps=dirty_laps)

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

    def open_pr(self, epic: str = "") -> Continue:
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
            return Continue(gate, self.select_epic)
        return Continue(gate, self.ci, epic=epic)

    def ci(self, epic: str = "", ci_rework: int = 0, merge_rework: int = 0) -> Continue | Await:
        """`await_ci` + `decide_ci` + `guard_ci`: is the epic's PR green?

        `unavailable` passes through to the merge, and that is the deliberate design rather
        than an oversight — offline, CI-less and read-blocked runs still complete, and the
        node logs the reason loudly at each site so it is never silent.

        Both counters are seeded by this state's own defaults, which is what `reset_ci` was:
        it seeded `ci_rework_count` *and* `merge_rework_count` in one node, because the
        merge budget also has to be fresh for each epic's PR.
        """
        gate = self.output(open_pr)
        checks = self.call(poll_pr_checks, "", epic_branch(gate.ci_epic))
        if checks.status in ("passed", "unavailable"):
            return Continue(checks, self.merge, epic=epic, merge_rework=merge_rework)
        # `failed`, and the YAML's `default:`, which was also the guard.
        if ci_rework >= self.MAX_CI_REWORKS:
            return self._ci_gate(gate.ci_epic, ci_rework, checks.summary, epic, merge_rework)
        return Continue(checks, self.repair_ci, epic=epic, ci_rework=ci_rework,
                        merge_rework=merge_rework)

    def repair_ci(
        self, epic: str = "", ci_rework: int = 0, merge_rework: int = 0
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
            FixCi, repo="", branch=epic_branch(gate.ci_epic), ci_summary=summary,
            docs_path=self.docs_path,
        )
        push = self.call(push_ci_fix, "", epic_branch(gate.ci_epic))
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.ci, epic=epic, ci_rework=ci_rework + 1,
                            merge_rework=merge_rework)
        return self._ci_gate(gate.ci_epic, ci_rework, summary, epic, merge_rework)

    def ci_operator(self, epic: str = "", merge_rework: int = 0) -> Continue:
        """The consume half of the CI gate: the operator acted, so poll again.

        The budget resets to zero, which is what `await-ci-operator.py` emitted — the
        operator's intervention buys a fresh set of automated attempts. Nothing here parses
        the answer: the YAML declared an `operator_input` output and no node ever read it,
        because what the operator did is visible in the next poll, not in what they typed.
        """
        self.logger.info("operator answered the CI gate — re-polling")
        return Continue(None, self.ci, epic=epic, ci_rework=0, merge_rework=merge_rework)

    def merge(self, epic: str = "", merge_rework: int = 0) -> Continue | Await:
        """`merge` + `decide_merge` + `guard_merge`: land the epic's PR.

        Best-effort, like the gate above it: with no origin, no token or no open PR the
        merge is a pass-through and HEAD is left on the epic branch, which is exactly what a
        local bind-mounted clone needs. `unavailable` therefore advances to the next epic.
        """
        gate = self.output(open_pr)
        outcome = self.call(merge_pr, gate.ci_epic, gate.ci_base)
        if outcome.merge_status in ("merged", "unavailable"):
            # The epic's merge is settled; the next epic's conflicts are a different worklist.
            self.reset_session(f"merge-fix:{gate.ci_epic}")
            return Continue(outcome, self.select_epic)
        # `failed`, and the blank the YAML's pessimistic `default:` sent the same way.
        if merge_rework >= self.MAX_MERGE_REWORKS:
            return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework, epic)
        return Continue(outcome, self.fix_merge, epic=epic, merge_rework=merge_rework)

    def fix_merge(self, epic: str = "", merge_rework: int = 0) -> Continue | Await:
        """`fix_merge` + `push_merge` + `decide_merge_push` + `incr_merge`.

        The second of the graph's two agent turns. `power="high"` for the reason the YAML
        gives: resolving conflicts on a divergent branch has high blast radius, and a wrong
        resolution corrupts code silently rather than failing loudly.
        """
        gate = self.output(open_pr)
        self.logger.info("resolving the merge for %s", gate.ci_epic, extra={"activity": True})
        result = self.agent(
            "prompts/fix-merge.md",
            returns=MergeFixResult,
            # high: a wrong conflict resolution silently corrupts code.
            power="high",
            add_dirs=self._dirs(),
            args={"ci_epic": gate.ci_epic, "ci_base": gate.ci_base},
            # Rework two is the same two branches still refusing to merge, and the turn that
            # resolved half the conflicts is the one that knows which half.
            session=f"merge-fix:{gate.ci_epic}",
        )
        if result.blocked:
            # The resolver says choosing between the two sides is not its call. Pushing an
            # unresolved branch and re-merging would spend the whole budget re-asking it,
            # so go straight to the gate the budget's own exhaustion goes to — and get
            # there with the resolver's reason, which is the only account of *why*.
            self.logger.info("the merge resolver reported it cannot decide: %s", result.notes)
            return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework, epic)
        push = self.call(push_ci_fix, "", gate.ci_epic)
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.merge, epic=epic, merge_rework=merge_rework + 1)
        return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework, epic)

    def merge_operator(self, epic: str = "") -> Continue:
        """The consume half of the merge gate: try the merge again, budget reset."""
        self.logger.info("operator answered the merge gate — re-merging")
        return Continue(None, self.merge, epic=epic, merge_rework=0)

    def dirty_operator(self, epic: str = "") -> Continue:
        """The consume half of the dirty-tree gate: re-read the tree, budget reset.

        Back to `commit` rather than on to `select_story`, because what the operator
        changed is the thing `commit` reads — and if they left it dirty, the gate is
        exactly where the run should land again.
        """
        self.logger.info("operator answered the dirty-tree gate — re-reading the worktree")
        return Continue(None, self.commit, epic=epic, dirty_laps=0)

    # ── routers and shared turns, none of them states ─────────────────────────────────

    def _ci_gate(
        self,
        ci_epic: str,
        attempts: int,
        summary: str,
        epic: str,
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
            merge_rework=merge_rework,
        )

    def _merge_gate(self, ci_epic: str, ci_base: str, attempts: int, epic: str) -> Await:
        """`flag_merge_fail` + `await_merge_operator`: the merge-side twin of `_ci_gate`."""
        self.call(flag_merge_failure, ci_epic, ci_base, str(attempts))
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "merge-operator", ci_epic),
            f"`{ci_epic}` will not merge into `{ci_base}` after {attempts} automated "
            "attempt(s).\n\nResolve it and touch this file when the run should try again.",
            self.merge_operator,
            epic=epic,
        )

    def _dirty_gate(self, dirty: list[str], epic: str, notes: str = "") -> Await:
        """`commit`'s uncommitted-work arm: the story ends parked, not swept into a commit.

        Reached from two places and for the same reason both times — the tree still holds
        work nobody recorded, and the one turn that could speak for it has had its lap.
        Committing it anyway is what this replaces, and it is how a story's diff used to
        acquire files no one on the story had ever opened.

        The chain the settle lap ran on is dropped here: whatever it holds is a
        conversation that did not settle the tree, and the operator is about to change the
        tree underneath it.
        """
        slug = self._story.story_slug
        self.reset_session(self._settle_chain())
        listing = "\n".join(f"- `{path}`" for path in dirty[:40])
        elided = f"\n\n_… and {len(dirty) - 40} more._" if len(dirty) > 40 else ""
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "dirty-tree-operator", slug),
            f"`{slug}` finished with uncommitted work still on disk, and the lap that was "
            "asked to record it did not.\n\n"
            f"{listing}{elided}\n\n"
            + (f"The agent's own account:\n\n{notes}\n\n" if notes.strip() else "")
            + "Commit what belongs to this story, discard or set aside what does not, and "
            "touch this file when the run should re-read the tree.",
            self.dirty_operator,
            epic=epic,
        )

    def _settle_chain(self) -> str:
        """The conversation the settle lap runs on, keyed per story.

        Per story because two stories in one run left two different sets of paths behind,
        and the whole value of the chain is that it already knows which of them it wrote.
        """
        return f"settle-worktree:{self._story.story_slug}"

    def _fix_prune(self, result: object, epic: str, session_id: str = "") -> Continue:
        """`prune_fix_item`: the drained fix shipped, so its bullet leaves the backlog."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.call(prune_fix_item, bullet, self.docs_path)
        return Continue(
            result,
            self.drain,
            epic=epic,
            docs_recheck_required=True,
            session_id=session_id,
        )

    def _fix_flag(self, result: object, epic: str, session_id: str = "") -> Continue:
        """`fix_give_up`: annotate the bullet in place and draw the next one."""
        bullet = self.output(select_fix_item).fix_bullet_id
        self.logger.info("flagging %s as blocked", bullet)
        self.call(mark_fix_blocked, bullet, BLOCKED_NOTE, self.docs_path)
        return Continue(
            result,
            self.drain,
            epic=epic,
            docs_recheck_required=True,
            session_id=session_id,
        )

    def _fix_qa(self) -> QaResult:
        """`qa-fix-item.md`, which `check_fix` and `recheck_fix` ran with identical arguments.

        Not `qa-story.md` — see `fix/flow.py`'s `_qa` for why that prompt cannot answer this
        turn. The nested drain runs the same one.
        """
        fix = self._fix_story
        self.logger.info("checking %s", fix.story_slug, extra={"activity": True})
        turn = roles.turn("qa-fix-item", self.repo_dir, self.library_dirs)
        return self.agent(
            turn.prompt,
            returns=QaResult,
            # high: the drain has no QA plan, no evidence gate and no audit behind it —
            # this turn is the whole verdict on the fix.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": fix.story_slug,
                "epic": fix.story_epic,
                "story_path": fix.story_path,
                "spec_dir": fix.spec_dir,
                "plan_services": self.call(plan_summary, fix.spec_dir).text,
                "qa_dir": fix.qa_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
            },
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

    def _preexisting(self) -> tuple[str, ...]:
        """What `prepare`'s snapshot found already dirty, or nothing when it never ran.

        A run checkpointed before the snapshot node existed resumes straight into
        `document` or `qa` with no recorded output, and an empty tuple is exactly the
        behaviour both had then — it subtracts nothing. Failing the story instead would
        punish a resume for a fix that is meant to make resumes safer.
        """
        try:
            return tuple(self.output(snapshot_worktree_state).entries)
        except NodeNotRunError:
            return ()

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
    # The eight registered Python sub-flows, by the name `workhorse-coder run <name>`
    # takes. Five are reached by `handoff`; `genesis`, `dream` and `fix` are entered
    # directly.
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
            "code-reuse": {"status": "ok"},
            "dev-fix": {"status": "fixed"},
            "code-review": {"status": "approved"},
            "review-implementation": {"status": "approved"},
            "apply-review": {"status": "applied"},
            "document-story": {"status": "passed"},
            "review-story-documentation": {"status": "passed"},
            "plan-qa": {"status": "complete"},
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
            "dream-reflect": {"status": "complete"},
        }
    )
)
main = console_script(workflow.entry_point(Coder))


__all__ = ["Coder", "main", "workflow"]
