"""`coder`: the epic/story loop.

Eight of the nine flows are one directory each — `dev/`, `qa/`, `genesis/` and the rest —
and this module is the graph that sequences them. It is a flow package like they are, for
the same reason: the machine, the nodes only it calls (`nodes/`) and the prompts only it
renders sit together, and `coder/workflow.py` is left holding the registry that composes
all nine.

**Where the state boundaries are.** A state is a resumable unit, and the rule this graph
follows everywhere is that a state ends where the *expensive or irreversible* thing
begins: each `handoff` to a sub-flow, each agent turn, and each of the two operator gates
starts one. Deterministic work folds forward into whichever state branches on it. That is
why `prune_epic` sits inside `open_pr` — a straight line, and the pop must precede the PR
— while `dev`, `review`, `document` and `qa` are four states rather than one: a kill
during QA must not re-run the implementation.

**The two counters are parameters.** `ci_rework` and `merge_rework` both live inside the
PR cluster, which is the whole distance either of them travels. A counter is a state
parameter, so seeding one is a keyword on a `Continue` rather than a node of its own.

**Two disjunctions that look alike and are not.** The working epic resolves two different
ways, and the graph keeps them apart:

* the story pipeline uses `prepare_story.story_epic or select_story.epic or epic` — the
  epic the *story* belongs to, discovered by scanning when story mode was handed a bare
  slug;
* `commit_story`, `qa_give_up` and `replan_epic` use `select_epic.epic or epic` — the epic
  the *queue* is working, which in story mode is whatever the run was invoked with.

Both are fall-back chains because `self.output()` raises for a node that has not run, and
in story mode neither `select_epic` nor `select_story` ever runs. The queue epic is carried
as a state parameter rather than read back through a guarded `self.output`, so a resumed
run does not have to re-derive it.

**The backlog drain is the `fix` flow, handed off to.** A story that goes green drains
whatever it filed on the way, and `drain` below is one `handoff` — not a second copy of
the loop.

The two flows still differ at the far end, and that difference is `Fix`'s, not this
file's: `Fix` documents and commits each drained item itself. This story's own final
documentation pass and commit run behind it, over whatever is left.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

from workhorse.pyflow import (
    Await,
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.fix import Fix
from workhorse_workflows.coder.fix_ci import FixCi
from workhorse_workflows.coder.qa import Qa
from workhorse_workflows.coder.qa.nodes import teardown_stack
from workhorse_workflows.coder.review import Review
from workhorse_workflows.coder.shared.ci import epic_branch, poll_pr_checks, push_ci_fix
from workhorse_workflows.coder.shared.worktree import snapshot_worktree_state
from workhorse_workflows.kit.telemetry import counter_labels
from workhorse_workflows.coder.main.nodes.pr import (
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
from workhorse_workflows.coder.shared.story import prepare_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.pr import MergeFixResult
from workhorse_workflows.coder.shared.schemas.queue import ReplanResult, WorktreeSettled
from workhorse_workflows.coder.shared.schemas.render import schema_block
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
    """Did the book end up true of this story?

    `not_applicable` — a repo with no book — passes, because the alternative is that every
    repo without documentation cannot run the workflow. Everything else, blank included, is
    the pessimistic arm, and every one of them goes to the operator rather than ending
    the run.
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

    #: `epic` (walk the queue) or `story` (one named slug).
    mode: Literal["epic", "story"] = "epic"
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
    operator_mode: Literal["auto", "human", "operator"] = "auto"
    #: Which environment QA runs against, passed through to `dev`, `docs` and `qa`.
    target_env: Literal["local", "dev"] = "local"

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

        Resolved here rather than on the story path, because the two agent turns this
        graph runs outside a story — `fix_merge` and `replan_epic` — are reachable before
        the first story is picked, and would otherwise be granted nothing. The node's one
        argument is `docs_path`, a run input, so this is the same call at a strictly
        earlier point.
        """
        return self.call(resolve_workspace_dirs, self.docs_path)

    def labels(self) -> dict[str, str]:
        """Which story, which epic, which mode, how far through: what a run's activity line shows.

        `work_id` and `progress` come off `select_story`'s record when there is one. Story
        mode never runs that node, so both fall back to the run's own arguments.
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
        """The queue, or the one story we were pointed at.

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
        """Take the front of the queue, and branch every repo for it.

        The branch is cut in the same state as the pick because nothing branches between
        them. An empty queue is the run's ordinary end, not a failure.
        """
        pick = self.call(select_epic, self.docs_path, str(self.run_dir))
        if not pick.has_epic:
            self.logger.info("no epic to work: %s", pick.reason)
            # The QA stack outlives every story on purpose (see the reuse policy), which
            # leaves exactly one place responsible for reaping it: the state where there is
            # no next story to serve. Nothing called this before, so a finished run left its
            # compose project and emulators holding their ports indefinitely.
            self.call(teardown_stack, self.docs_path)
            return Done(pick)
        base = self.output(init_base).base_branch
        self.call(branch_epic, pick.epic, base, str(self.run_dir))
        return Continue(pick, self.select_story, epic=pick.epic)

    def select_story(self, epic: str = "") -> Continue:
        """The next unimplemented story of this epic.

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
        # `blocked`, and every other verdict: the epic is set aside and the queue advances.
        self.call(flag_epic_blocked, epic, str(self.run_dir), pick.reason)
        return Continue(pick, self.select_epic)

    # ── one story ─────────────────────────────────────────────────────────────────────

    def prepare(self, slug: str = "", epic: str = "") -> Continue:
        """Resolve the slug to paths, and seed the triage counter.

        The triage budget is seeded here rather than inside `qa` because it has to
        survive across QA *entries*: a rescope sends the story back to `dev` and re-enters
        QA, and a budget that reset on each entry would never be spent. That is why `triage` is threaded through the four
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
        return Continue(story, self.dev, epic=epic)

    def dev(self, epic: str = "", triage: int = 0) -> Continue:
        """Plan and implement the story.

        `replan` is the sub-flow saying the *story* was the wrong thing to build — an
        operator answered a block with an epic-scoped answer — so the epic gets rewritten
        rather than the story retried.

        Nothing here names the story's backbone conversation. `Dev` derives that chain's
        key from the story slug, and a handed-off lane shares this run's chain directory,
        so `review`, `document` and `qa` find whatever `Dev` left there without being told
        — and a lane run on its own finds nothing and starts cold, which is what makes a
        replay of one lane honest.
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
            return Continue(result, self.replan, epic=epic, notes=result.operator_notes)
        # `ready`, and every other verdict: on to the review.
        return Continue(
            result,
            self.review,
            epic=epic,
            triage=triage,
            session_turns=result.session_turns,
        )

    def review(self, epic: str = "", triage: int = 0, session_turns: int = 0) -> Continue:
        """Code review and reuse, with no branch on the outcome.

        Nothing is read back, and that is not an oversight: the review flow either
        converges or fails the run from inside itself, so there is no verdict left for the
        caller to read. It also takes no `target_env` —
        review reads code, it does not run it.

        The lane judges the diff cold — the review turns open their own conversation, so no
        reviewer inherits what `dev` said about its own work — but the turns that then
        *change* the code rejoin the implementer's conversation, which they find under the
        story's own chain key (see `Review`'s docstring). Nothing is read back from its
        result: what reaches `document` is exactly what `dev` produced.
        """
        slug = self._story.story_slug
        self.logger.info("reviewing %s%s", slug, self._progress(), extra={"activity": True})
        result = self.handoff(
            Review,
            story=slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
            inherited_turns=session_turns,
        )
        return Continue(result, self.document, epic=epic, triage=triage)

    def document(self, epic: str = "", triage: int = 0) -> Continue:
        """Fold the story into the OKF book.

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
        """
        result = self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            target_env=self.target_env,
            preexisting=self._preexisting(),
            operator_mode=self.operator_mode,
        )
        if not _documented(result):
            return Continue(result, self.blocked_docs, epic=epic, triage=triage,
                            notes=_docs_notes(result, "story"))
        return Continue(result, self.qa, epic=epic, triage=triage)

    def blocked_docs(
        self,
        epic: str = "",
        triage: int = 0,
        notes: str = "",
        resume_at: Literal["document", "give_up", "finalize"] = "document",
        attempts: int = 0,
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
        )

    def docs_operator(
        self,
        epic: str = "",
        triage: int = 0,
        resume_at: Literal["document", "give_up", "finalize"] = "document",
        attempts: int = 0,
    ) -> Continue:
        """The consume half of the docs gate: re-document on the operator's fix."""
        self.logger.info(
            "operator answered the docs gate — redocumenting %s", self._story.story_slug
        )
        if resume_at == "give_up":
            return Continue(None, self.give_up, epic=epic, attempts=attempts)
        if resume_at == "finalize":
            return Continue(None, self.finalize, epic=epic)
        return Continue(None, self.document, epic=epic, triage=triage)

    def qa(self, epic: str = "", triage: int = 0) -> Continue:
        """The four-way gate the whole loop turns on.

        `rescope` is the interesting arm. It sends the story back to `dev` carrying the
        triage budget the QA flow spent, and the re-entry deliberately bypasses the seed
        so the count persists across the loop.

        `preexisting` goes in for the same reason `document` takes it: QA builds its
        obligation packet from the same `HEAD..WORKTREE` diff, so without the snapshot an
        abandoned story's uncommitted code becomes scenarios this story has to write.

        A `rescope` hands the story straight back to `dev`, which rejoins the same
        backbone conversation because the key is the story's and the chain file is the
        run's. The next story `select_story` picks up has a different slug, so it names a
        different chain and starts cold.
        """
        result = self.handoff(
            Qa,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(epic),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
            triage_scope=triage,
            preexisting=self._preexisting(),
        )
        if result.status == "replan":
            return Continue(result, self.replan, epic=epic, notes=result.operator_notes)
        if result.status == "rescope":
            self.logger.info("QA rescoped %s — back to dev", self._story.story_slug)
            return Continue(result, self.dev, epic=epic, triage=result.triage_scope)
        if result.status == "refix":
            # Triage found the *product* wrong. The QA lane's fixer is briefed on a QA report
            # and told not to broaden behaviour, so it patches the surface the scenario
            # touched; the dev lane owns product code and re-enters review and QA behind
            # itself. The findings are on disk in the story's `qa.md`, which is what `dev`
            # reads — there is no brief to thread through this call.
            self.logger.info(
                "QA found a product defect in %s — back to dev", self._story.story_slug
            )
            return Continue(result, self.dev, epic=epic, triage=result.triage_scope)
        if result.status == "inconclusive":
            # The only mode that still lands here is `target_env="dev"`: every other
            # exhaustion now escalates to the operator gate inside the QA sub-flow itself
            # and never returns with this status at all.
            return Continue(result, self.give_up, epic=epic, attempts=result.qa_rework)
        # `passed`, and every other verdict: the story is green, so drain what it filed.
        return Continue(
            result,
            self.drain,
            epic=epic,
            docs_recheck_required=result.docs_recheck_required,
        )

    def replan(self, epic: str = "", notes: str = "") -> Continue:
        """Rewrite the epic from what the operator said, and re-select.

        The one turn in this graph that rewrites planning documents rather than code, which
        is why it is `power="high"`. `notes` is threaded rather than read back: it comes out
        of a sub-flow's return value, and a sub-flow's node records are in its own subscope.
        """
        self.logger.info("replanning epic %s", self._queue_epic(epic), extra={"activity": True})
        turn = roles.turn(self, "replan-epic", returns=ReplanResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
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

    def give_up(self, epic: str = "", attempts: int = 0) -> Continue:
        """QA could not be carried: the dev-target report ends here, and the run stops.

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
        )
        if not _documented(result):
            return Continue(
                result,
                self.blocked_docs,
                epic=epic,
                notes=_docs_notes(result, "failed story"),
                resume_at="give_up",
                attempts=attempts,
            )
        if _docs_changed_qa_retry_artifact(result, self._story.spec_dir):
            self.logger.info(
                "documentation changed QA retry artifacts for %s — rerunning QA",
                self._story.story_slug,
                extra={"activity": True},
            )
            return Continue(result, self.qa, epic=epic)
        raise WorkflowFailed(
            f"QA never passed for story {self._story.story_slug!r} after {attempts} "
            f"attempt(s); nothing was committed for this story.",
            failure_class="qa-give-up",
            artifacts={"spec_dir": str(self._story.spec_dir)},
        )

    # ── the backlog drain ─────────────────────────────────────────────────────────────

    def drain(self, epic: str = "", docs_recheck_required: bool = True) -> Continue:
        """Hand the backlog to the `fix` flow, which drains it to dry and returns.

        `Fix` documents and commits each item it drains, so nothing about the drained work
        is left for this story to record. `docs_recheck_required` is carried through
        untouched: it is QA's answer about *this story*, and the drain neither sets nor
        clears it.
        """
        result = self.handoff(
            Fix,
            docs_path=self.docs_path,
            target_env=self.target_env,
        )
        return Continue(
            result,
            self.finalize,
            epic=epic,
            docs_recheck_required=docs_recheck_required,
        )

    # ── the far end of a story ────────────────────────────────────────────────────────

    def finalize(self, epic: str = "", docs_recheck_required: bool = True) -> Continue:
        """Recheck documentation after a mutation, then commit the story.

        A clean QA pass needs no redundant second Docs handoff. QA repairs and the nested
        backlog drain set a monotonic taint; only those paths re-enter Docs. Defaults are
        fail-closed so an old checkpoint with no taint still performs the recheck.
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
        )
        if not _documented(result):
            return Continue(
                result,
                self.blocked_docs,
                epic=epic,
                notes=_docs_notes(result, "story (final pass)"),
                resume_at="finalize",
            )
        if self.mode == "epic":
            return Continue(result, self.commit, epic=epic)
        return Continue(result, self.commit_pr)

    def commit(self, epic: str = "", dirty_laps: int = 0) -> Continue | Await:
        """The story's work is recorded, or it parks.

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
            "main/prompts/settle-worktree.md",
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
                "result_schema": schema_block(WorktreeSettled),
            },
            session=self._settle_chain(),
        )
        if result.blocked:
            return self._dirty_gate(state.dirty, epic, notes=result.notes)
        return Continue(result, self.commit, epic=epic, dirty_laps=dirty_laps)

    def commit_pr(self) -> Done:
        """Story mode's end: commit what the story left, and open its PR.

        The epic argument is blank: a story-mode run commits under the story's own
        identity. The branch to push and open the PR from comes from
        `branch_story`, the node that cut it — never re-derived from the slug here, which is
        how the two drifted once.
        """
        story = self._story
        branch = self.output(branch_story)
        self.call(commit_story, "", story.story_slug, story.spec_dir, story.story_path)
        self.call(teardown_stack, self.docs_path)
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
        """The epic is done, so ship it.

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
        """Is the epic's PR green?

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
        # `failed`, and every other verdict: the guard decides whether a lap is left.
        if ci_rework >= self.MAX_CI_REWORKS:
            return self._ci_gate(gate.ci_epic, ci_rework, checks.summary, epic, merge_rework)
        return Continue(checks, self.repair_ci, epic=epic, ci_rework=ci_rework,
                        merge_rework=merge_rework)

    def repair_ci(
        self, epic: str = "", ci_rework: int = 0, merge_rework: int = 0
    ) -> Continue | Await:
        """One automated attempt at red CI: fix it, push it, spend a lap.

        `repo=""` into the sub-flow means "iterate every workspace repo with failing CI".

        A resolution that cannot be pushed can never make the next poll come back green, so
        `failed` escalates rather than spending another attempt on an unmoved branch head.
        """
        gate = self.output(open_pr)
        summary = self.output(poll_pr_checks).summary
        self.handoff(
            FixCi, repo="", branch=epic_branch(gate.ci_epic), docs_path=self.docs_path,
        )
        push = self.call(push_ci_fix, "", epic_branch(gate.ci_epic))
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.ci, epic=epic, ci_rework=ci_rework + 1,
                            merge_rework=merge_rework)
        return self._ci_gate(gate.ci_epic, ci_rework, summary, epic, merge_rework)

    def ci_operator(self, epic: str = "", merge_rework: int = 0) -> Continue:
        """The consume half of the CI gate: the operator acted, so poll again.

        The budget resets to zero: the operator's intervention buys a fresh set of
        automated attempts. Nothing here parses the answer, because what the operator did
        is visible in the next poll, not in what they typed.
        """
        self.logger.info("operator answered the CI gate — re-polling")
        return Continue(None, self.ci, epic=epic, ci_rework=0, merge_rework=merge_rework)

    def merge(self, epic: str = "", merge_rework: int = 0) -> Continue | Await:
        """Land the epic's PR.

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
        # `failed`, and a blank, which is pessimistic for the same reason.
        if merge_rework >= self.MAX_MERGE_REWORKS:
            return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework, epic)
        return Continue(outcome, self.fix_merge, epic=epic, merge_rework=merge_rework)

    def fix_merge(self, epic: str = "", merge_rework: int = 0) -> Continue | Await:
        """One automated attempt at a merge that would not land.

        The second of the graph's two agent turns, and `power="high"`: resolving conflicts
        on a divergent branch has high blast radius, and a wrong resolution corrupts code
        silently rather than failing loudly.
        """
        gate = self.output(open_pr)
        self.logger.info("resolving the merge for %s", gate.ci_epic, extra={"activity": True})
        result = self.agent(
            "main/prompts/fix-merge.md",
            returns=MergeFixResult,
            # high: a wrong conflict resolution silently corrupts code.
            power="high",
            add_dirs=self._dirs(),
            args={
                "ci_epic": gate.ci_epic,
                "ci_base": gate.ci_base,
                "result_schema": schema_block(MergeFixResult),
            },
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
        """The automated attempts are spent, so the epic parks for a person.

        **This gate is human whatever `operator_mode` says**: a red PR that cannot be
        pushed is an infrastructure or credential wall, not a question an agent can answer
        by trying harder.

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
        """The merge-side twin of `_ci_gate`."""
        self.call(flag_merge_failure, ci_epic, ci_base, str(attempts))
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "merge-operator", ci_epic),
            f"`{ci_epic}` will not merge into `{ci_base}` after {attempts} automated "
            "attempt(s).\n\nResolve it and touch this file when the run should try again.",
            self.merge_operator,
            epic=epic,
        )

    def _dirty_gate(self, dirty: list[str], epic: str, notes: str = "") -> Await:
        """The uncommitted-work arm of `commit`: the story parks, it is not swept into a commit.

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

    def _story_epic(self, epic: str) -> str:
        """`prepare_story.story_epic or select_story.epic or epic` — the *story's* epic.

        `prepare_story` discovers it by scanning when story mode was handed a bare slug, so
        its answer wins; the queue epic is the fall-back. `select_story.epic` is skipped
        between them because it is the value `epic` already carries: the pick was made *for*
        that epic.
        """
        return self._story.story_epic or epic or self.epic

    def _queue_epic(self, epic: str) -> str:
        """`select_epic.epic or epic` — the epic the *queue* is working.

        Distinct from `_story_epic` and not interchangeable with it: this one is blank in
        story mode unless the run was invoked with an epic.
        """
        return epic or self.epic

    def _progress(self) -> str:
        """The ` · 3/7` suffix an activity line carries when the run knows how far through it is."""
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
        """The directories every agent turn in this graph may read."""
        return list(self.ctx.dirs)

    @property
    def _story(self) -> StoryPaths:
        """The story this iteration is building, as `prepare` resolved it."""
        return self.output(prepare_story)

