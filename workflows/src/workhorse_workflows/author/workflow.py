"""The author workflow: a backlog becomes epics, epics become coder-ready stories.

Ported from `base-library/workflows/author/workflow.yaml` — 84 nodes reduced to 26
states. The reduction is mechanical and always the same four collapses:

* a `branch` node is an `if` in the state that produced the value it branches on, so
  every `decide_*` disappears into its producer;
* a counter is a **state parameter**, so `init_counter` / `incr_counter` disappear into
  the transition that resets or bumps it — `reset_epics_rework` is `reworks=0` on an
  edge, and `incr_story` is `reworks=reworks + 1` on another;
* a `guard_*` budget check and its `gate_*` operator-mode switch are two lines at the
  top of the `resolve_*` state they guard, because that is the only thing they decide;
* `await_operator` is the driver's `Await`, and the 280-line ctypes inotify watcher it
  ran is gone — the driver polls.

Two shapes here are not in `research`, and both are the reason this port came first:

**`handoff`.** `survey_intake` and `parity_survey_intake` are the two `type: flow`
nodes. `Surveyor` and `ParitySurveyor` are registered on *this* registry, so they run
with the parent's node index and prompt directory (see `flows/__init__.py`) — which is
what keeps `prompts/surveyor/…` resolving.

**`Await`.** The YAML's `resolve_* → await_*` edges are unconditional: the resolver
agent wrote `STATUS: ANSWERED` or `STATUS: AWAITING_OPERATOR` into the context file and
`await-operator.py` read that line to decide whether to block. `Await` in the driver
always blocks, so a literal transcription would hang forever on a block the resolver had
already answered. Every `resolve_*` state below therefore branches on the resolver's own
`decision` — which is what the YAML *already* did at `decide_reconcile_resolve`,
`decide_integrity_resolve` and the surveyor's `decide_verify_resolve`. This port
generalizes that pattern to the four gates that lacked it.

`docs/plans/author-workflow-python/` is the rendered reference this follows. Two file-shape
divergences from it: the operator gates are folded into their `resolve_*` states rather
than living in `_gate_*` helpers (only the story-rework and coverage gates keep a helper,
because three states route into each), and the config models hold repo-relative strings,
because that is what the scripts emitted and what a checkpoint has to survive a machine
change with.
"""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import (
    Await,
    Continue,
    Done,
    NodeNotRunError,
    Registry,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.author import paths
from workhorse_workflows.author.flows import ParitySurveyor, Surveyor
from workhorse_workflows.author.nodes import (
    blueprint,
    branch_author,
    check_story_feedback,
    check_story_grounding,
    commit_author,
    load_config,
    open_author_pr,
    prune_backlog,
    prune_bullet,
    record_attempt,
    seed_story,
    select_epic,
    select_story,
    validate_artifacts,
    validate_coverage,
    validate_story,
    verify_integrity,
    verify_reconcile,
)
from workhorse_workflows.author.nodes.survey import blueprint as survey_blueprint
from workhorse_workflows.author.schemas import (
    AuditResult,
    CoverageReview,
    DecomposeResult,
    EpicReview,
    MockupResult,
    OperatorResolution,
    RunContext,
    StorySplit,
    WriteEpicResult,
    WriteStoryResult,
)

#: Reworks of one stage before it is handed to the operator: the epic decomposition, one
#: story, and one epic's story coverage all share this bound (`vars.max_reworks`).
MAX_REWORKS = 3
#: Autonomous resolutions of one block before every later one goes to a human. The YAML
#: wrote these as six separate vars, all `"2"`; they are six because each gate counts its
#: own attempts, and they are equal because nothing yet argues for different bounds.
MAX_EPICS_RESOLVES = 2
MAX_WRITE_EPIC_RESOLVES = 2
MAX_SPLIT_RESOLVES = 2
MAX_WRITE_STORY_RESOLVES = 2
MAX_RECONCILE_RESOLVES = 2
MAX_INTEGRITY_RESOLVES = 2
#: The seven operator-resolution turns run under `timeout: infinity` in the YAML. They
#: stand in for a human, so a wall-clock ceiling on them is the wrong bound entirely —
#: the flow is already blocked and the only question is what unblocks it.
UNBOUNDED = float("inf")


class Author(Workflow):
    """Turn a backlog into epics, and each epic into stories a coder can build.

    Three entry modes, all ending at the same git tail. `epic` (the default) decomposes
    the backlog and authors every epic it finds. `survey` runs the surveyor first, so the
    backlog it decomposes is one exhaustive discovery produced, then authors it. `story`
    authors ONE bullet into an epic that already exists, and stops there.
    """

    #: `epic`, `survey`, `parity-survey` or `story`. Anything else reads as `epic`, which
    #: is the YAML's `cases:` with `default:` on the epic arm.
    mode: str = "epic"
    #: `story` mode: the epic slug to author into; it must already exist. In `epic` mode
    #: this stays blank and `select_epic` names the epic instead.
    epic: str = ""
    #: `story` mode: a backlog `[id]`, or the literal bullet text to author.
    bullet: str = ""
    #: The worklist. Story mode resolves `bullet` against **this** file, and the coverage
    #: tail prunes the bullets an authored epic consumed from it.
    backlog: str = "docs/backlog.md"
    #: Where epics live, one directory each.
    epics_dir: str = "docs/epics"
    #: `survey` mode: the rubric handed to the surveyor sub-flow.
    rubric: str = "docs/survey/rubric.md"
    #: `survey` mode: where the surveyor's own artifacts live.
    survey_dir: str = "docs/survey"
    #: `parity-survey` mode: the committed inventory the new build is measured against.
    baseline_inventory: str = ""
    #: `parity-survey` mode: the feature docs describing the target.
    target_features: str = "docs/features"
    #: `parity-survey` mode: where the parity survey's artifacts live.
    parity_survey_dir: str = "docs/survey/legacy-vs-new"
    #: `auto` lets the resolver agent stand in for the human at every gate; `human` sends
    #: every block straight to the context file.
    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        """Resolve the run's paths, then cut the branch it works on.

        `load_config` + `branch_author`. Neither decides anything a state has to revisit:
        the paths are fixed for the run, and the branch is keyed off `run_dir`, so a
        resume lands back on the same branch instead of cutting a second one.
        """
        cfg = self.call(load_config, self.backlog, self.epics_dir)
        branches = self.call(branch_author, str(self.run_dir), self.mode)
        return RunContext(
            **cfg.model_dump(),
            base_branch=branches.base_branch,
            author_branch=branches.author_branch,
        )

    def labels(self) -> dict[str, str]:
        """Which story, which epic, how far along — the YAML's `labels:` block verbatim.

        Both `select_*` nodes are read exactly as the YAML read them, with the same
        fall-back chain. Story mode never runs `select_story`, so its `work_id` is the
        epic it was pointed at — which is also what the YAML rendered there.
        """
        epic = self._epic_label() or self.epic
        try:
            pick = self.output(select_story)
        except NodeNotRunError:
            return {"work_id": epic, "epic": epic, "progress": ""}
        return {
            "work_id": pick.story_slug or epic,
            "epic": epic,
            "progress": pick.progress,
        }

    # --- what the states say twice -------------------------------------------
    #
    # Private, so state discovery skips them (a leading underscore is not a state).

    def _epic_label(self) -> str:
        """`select_epic`'s epic, or blank before the first pick."""
        try:
            return self.output(select_epic).epic
        except NodeNotRunError:
            return ""

    def _epic_dir(self, epic: str) -> str:
        """The YAML's `{{ epic_dir }}`, rebuilt rather than carried.

        Both producers — `select_epic` and story mode's `seed_story` — derive it from
        `epics_dir` and the slug, so deriving it here is the same string with one fewer
        parameter in every story-loop signature.
        """
        return paths.epic_dir(self.epics_dir, epic)

    def _abs(self, rel: str) -> Path:
        """A repo-relative path made absolute, which is what `Await` writes to."""
        return Path(self.ctx.repo_root) / rel

    def _author_context(self) -> str:
        """The run-wide operator context file, repo-relative: the epic-split and
        whole-graph gates all record their Q&A here."""
        return paths.author_context(self.epics_dir)

    def _activity(self, message: str, node: object) -> None:
        """The YAML's `activity:` line: what is being authored, plus queue progress.

        The progress half came from `get_node_output(…, 'progress')` guarded by an
        `{% if %}`; before the first pick there is nothing to read, which is the run's
        normal first state and not a problem.
        """
        try:
            progress = self.output(node).progress
        except NodeNotRunError:
            progress = ""
        suffix = f" · {progress}" if progress else ""
        self.logger.info("%s%s", message, suffix, extra={"activity": True})

    def _resolve(self, stage: str, notes: str, context: str, epic_dir: str) -> OperatorResolution:
        """One operator-resolution turn: `prompts/resolve-operator.md`.

        Six of the YAML's gates shared this prompt and differed only in the four
        arguments, so they share one call here. High-power and unbounded because it is
        standing in for a human, with full tool access.
        """
        self.logger.info("resolving the %s block", stage, extra={"activity": True})
        return self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": context,
                "epic_dir": epic_dir,
                "block_stage": stage,
                "block_notes": notes,
            },
        )

    def _story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str,
        cov_reworks: int,
        split_resolves: int,
    ) -> dict[str, object]:
        """The story-loop parameters every state in it passes on unchanged.

        `cov_reworks` and `split_resolves` are the two budgets that belong to the *epic*
        and have to survive the story loop, because the YAML held them in vars that the
        loop never touched: an epic whose coverage comes back with gaps re-enters
        `split_stories` on the budget it left with, not on a fresh one.
        """
        return {
            "epic": epic,
            "story_slug": story_slug,
            "story_dir": story_dir,
            "story_path": story_path,
            "mockup": mockup,
            "cov_reworks": cov_reworks,
            "split_resolves": split_resolves,
        }

    # --- mode dispatch --------------------------------------------------------

    def start(self) -> Continue | Done:
        """Which machine this run is: epic, survey, parity-survey or story.

        `decide_mode` plus the node each arm led to. There is deliberately no
        surface-coverage gate at intake: the one that used to sit here graded the
        *previous* run, because the seeds it read are written downstream of intake.
        """
        # Keywords, not positionals: a `Workflow` subclass is a pydantic model, and its
        # synthesised `__init__` takes none.
        if self.mode == "survey":
            result = self.handoff(
                Surveyor,
                rubric=self.rubric,
                survey_dir=self.survey_dir,
                backlog=self.backlog,
                operator_mode=self.operator_mode,
            )
            return Continue(result, self.split_epics)
        if self.mode == "parity-survey":
            result = self.handoff(
                ParitySurveyor,
                baseline_inventory=self.baseline_inventory,
                target_features=self.target_features,
                survey_dir=self.parity_survey_dir,
                backlog=self.backlog,
                epics_dir=self.epics_dir,
            )
            # `parity_survey_done` is a terminal in the YAML: a parity survey emits a
            # backlog and stops, it does not go on to author what it found.
            return Done(result)
        if self.mode == "story":
            seeded = self.call(seed_story, self.epic, self.epics_dir, self.bullet, self.backlog)
            return Continue(
                seeded,
                self.design_mockup,
                epic=self.epic,
                story_slug=seeded.story_slug,
                story_dir=seeded.story_dir,
                story_path=seeded.story_path,
            )
        return Continue(None, self.split_epics)

    # --- 1. epic split --------------------------------------------------------

    def split_epics(self, resolves: int = 0) -> Continue:
        """Split the backlog into epics.

        `reset_epics_rework` + `reset_epics_resolve` + `decompose_epics`. The rework
        budget resets here because this is the stage entry — and because `await_epics`
        reset it too, which is why it is not a parameter. The resolve budget is one,
        since the operator gate loops back through here and must not get a fresh one.
        """
        result = self.agent(
            "prompts/decompose-epics.md",
            returns=DecomposeResult,
            # high: the split decides the shape of every epic and story below it.
            power="high",
            cwd=self.ctx.repo_root,
            args={"backlog": self.backlog, "epics_dir": self.epics_dir},
        )
        return Continue(result, self.review_epics, resolves=resolves)

    def review_epics(self, reworks: int = 0, resolves: int = 0) -> Continue | Await:
        """Read the decomposition back before a single story is written.

        `review_epics` + `decide_epics` + `guard_epics` + `gate_epics`. `needs_rework` is
        the default arm: a review that returns nothing legible is not an approval.
        """
        result = self.agent(
            "prompts/review-epics.md",
            returns=EpicReview,
            power="high",
            cwd=self.ctx.repo_root,
            args={"backlog": self.backlog, "epics_dir": self.epics_dir},
        )
        if result.status == "approved":
            return Continue(result, self.next_epic)
        notes = result.notes
        if result.status != "blocked" and reworks < MAX_REWORKS:
            return Continue(result, self.rework_epics, notes=notes, reworks=reworks, resolves=resolves)
        if self.operator_mode == "human" or resolves >= MAX_EPICS_RESOLVES:
            return Await(self._abs(self._author_context()), notes, self.split_epics, resolves=resolves)
        return Continue(result, self.resolve_epics, notes=notes, resolves=resolves)

    def rework_epics(self, notes: str, reworks: int = 0, resolves: int = 0) -> Continue:
        """Re-derive the decomposition against the review's findings.

        `rework_epics` + `incr_epics`. Same product as `decompose_epics`, which is why
        both return `DecomposeResult`.
        """
        result = self.agent(
            "prompts/rework-epics.md",
            returns=DecomposeResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "backlog": self.backlog,
                "epics_dir": self.epics_dir,
                "review_notes": notes,
            },
        )
        return Continue(result, self.review_epics, reworks=reworks + 1, resolves=resolves)

    def resolve_epics(self, notes: str, resolves: int = 0) -> Continue | Await:
        """Stand in for the operator on an epic-split block, or escalate to one.

        `resolve_epics` + `incr_epics_resolve` + the `await_epics` that followed them
        unconditionally. Re-entering `split_epics` *is* the re-verification: the split
        and the review both re-read the context file the resolver just answered.
        """
        result = self._resolve("epic-split", notes, self._author_context(), self.epics_dir)
        if result.decision == "answered":
            return Continue(result, self.split_epics, resolves=resolves + 1)
        return Await(self._abs(self._author_context()), notes, self.split_epics, resolves=resolves + 1)

    # --- 2. the per-epic loop -------------------------------------------------

    def next_epic(self) -> Continue:
        """Take the next unauthored epic, or fall through to the whole-run gates.

        `select_epic` + `decide_epic` + the two budget resets its arms led to. "No epic
        left" is the loop's success exit: a fully decomposed backlog has nothing to pick.
        """
        pick = self.call(select_epic, self.epics_dir)
        if pick.has_epic:
            return Continue(pick, self.author_epic, epic=pick.epic)
        return Continue(pick, self.reconcile)

    def author_epic(self, epic: str, resolves: int = 0) -> Continue | Await:
        """Write one epic's `epic.md` and its seeds.

        `reset_write_epic_resolve` + `write_epic` + `decide_write_epic` +
        `gate_write_epic` + `guard_write_epic_resolve`. `complete` is the default arm.
        """
        self._activity(f"authoring epic {epic}", select_epic)
        result = self.agent(
            "prompts/write-epic.md",
            returns=WriteEpicResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "epic_dir": self._epic_dir(epic),
                "backlog": self.backlog,
                "features_dir": self.ctx.features_dir,
            },
        )
        if result.status != "blocked":
            return Continue(result, self.split_stories, epic=epic)
        context = paths.epic_context(self._epic_dir(epic))
        if self.operator_mode == "human" or resolves >= MAX_WRITE_EPIC_RESOLVES:
            return Await(self._abs(context), result.notes, self.author_epic, epic=epic, resolves=resolves)
        return Continue(result, self.resolve_epic_doc, epic=epic, notes=result.notes, resolves=resolves)

    def resolve_epic_doc(self, epic: str, notes: str, resolves: int = 0) -> Continue | Await:
        """Stand in for the operator on a write-epic block, or escalate to one.

        `resolve_write_epic` + `incr_write_epic_resolve` + `await_write_epic`. The budget
        is *not* reset by the loop back into `author_epic`, which is what bounds a block
        the resolver cannot actually clear.
        """
        epic_dir = self._epic_dir(epic)
        context = paths.epic_context(epic_dir)
        result = self._resolve("write-epic", notes, context, epic_dir)
        if result.decision == "answered":
            return Continue(result, self.author_epic, epic=epic, resolves=resolves + 1)
        return Await(self._abs(context), notes, self.author_epic, epic=epic, resolves=resolves + 1)

    # --- 2b. story split ------------------------------------------------------

    def split_stories(
        self,
        epic: str,
        split_resolves: int = 0,
        cov_reworks: int = 0,
        rework_notes: str = "",
    ) -> Continue | Await:
        """Group one epic's seeds into story-sized units.

        `reset_cov_rework` + `reset_split_resolve` + `split_stories` + `decide_split` +
        `gate_split` + `guard_split_resolve`.

        `rework_notes` is the coverage loop's worklist, and it arrives as a parameter for
        the reason the YAML needed a counter guard to render it: as a var it still held
        the *previous* epic's verdict on a fresh entry. A parameter has no previous
        value, so only the edge that actually has notes passes them.
        """
        result = self.agent(
            "prompts/split-stories.md",
            returns=StorySplit,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "epic_dir": self._epic_dir(epic),
                "rework_notes": rework_notes,
            },
        )
        if result.status == "standoff":
            # The splitter was handed a rework and judged that no change is warranted.
            # Nothing about its inputs changes on another lap, so the disagreement goes
            # to the coverage gate — where the resolver can see both positions.
            notes = f"{rework_notes}\n\nStory-split stage declined this rework: {result.notes}"
            return self._gate_coverage(result, notes, epic, split_resolves)
        if result.status != "blocked":
            return Continue(
                result,
                self.next_story,
                epic=epic,
                cov_reworks=cov_reworks,
                split_resolves=split_resolves,
            )
        context = paths.epic_context(self._epic_dir(epic))
        if self.operator_mode == "human" or split_resolves >= MAX_SPLIT_RESOLVES:
            return Await(
                self._abs(context),
                result.notes,
                self.split_stories,
                epic=epic,
                split_resolves=split_resolves,
                cov_reworks=cov_reworks,
                rework_notes=rework_notes,
            )
        return Continue(
            result,
            self.resolve_split,
            epic=epic,
            notes=result.notes,
            split_resolves=split_resolves,
            cov_reworks=cov_reworks,
            rework_notes=rework_notes,
        )

    def resolve_split(
        self,
        epic: str,
        notes: str,
        split_resolves: int = 0,
        cov_reworks: int = 0,
        rework_notes: str = "",
    ) -> Continue | Await:
        """Stand in for the operator on a story-split block, or escalate to one.

        `resolve_split` + `incr_split_resolve` + `await_split`. `rework_notes` is carried
        across the gate because the YAML re-rendered it from a var on the way back in: a
        block resolved mid-coverage-rework must return to the same worklist.
        """
        epic_dir = self._epic_dir(epic)
        context = paths.epic_context(epic_dir)
        result = self._resolve("story-split", notes, context, epic_dir)
        params = {
            "epic": epic,
            "split_resolves": split_resolves + 1,
            "cov_reworks": cov_reworks,
            "rework_notes": rework_notes,
        }
        if result.decision == "answered":
            return Continue(result, self.split_stories, **params)
        return Await(self._abs(context), notes, self.split_stories, **params)

    # --- 2c. the per-story loop -----------------------------------------------

    def next_story(self, epic: str, cov_reworks: int = 0, split_resolves: int = 0) -> Continue:
        """Take the next unwritten story of this epic, or check the epic's coverage.

        `select_story` + `decide_story`.
        """
        pick = self.call(select_story, self._epic_dir(epic))
        if not pick.has_story:
            return Continue(
                pick,
                self.check_coverage,
                epic=epic,
                cov_reworks=cov_reworks,
                split_resolves=split_resolves,
            )
        return Continue(
            pick,
            self.design_mockup,
            epic=epic,
            story_slug=pick.story_slug,
            story_dir=pick.story_dir,
            story_path=pick.story_path,
            cov_reworks=cov_reworks,
            split_resolves=split_resolves,
        )

    def design_mockup(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        cov_reworks: int = 0,
        split_resolves: int = 0,
    ) -> Continue:
        """Sketch a genuinely new screen before writing the story against it.

        `reset_story_rework` + `reset_write_story_resolve` + `design_mockup`. Advisory
        throughout: a story on an existing surface is a pass-through, and a failed mockup
        must never block authoring — `write_story` falls back to the feature doc.
        """
        result = self.agent(
            "prompts/design-mockup.md",
            returns=MockupResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "surface_manifest": self.ctx.surface_manifest,
                "mockup_dir": self.ctx.mockup_dir,
            },
        )
        story = self._story(
            epic, story_slug, story_dir, story_path, result.mockup, cov_reworks, split_resolves
        )
        return Continue(result, self.write_story, **story)

    def write_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue | Await:
        """Write one story: the coder-ready contract.

        `write_story` + `decide_write_story`. `written` is the default arm; the
        validators below are what actually decide whether it is a contract.
        """
        self._activity(f"authoring {story_slug}", select_story)
        result = self.agent(
            "prompts/write-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup,
            },
        )
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        if result.status == "blocked":
            return self._gate_story(result, result.notes, story, resolves)
        return Continue(result, self.check_story, **story, reworks=reworks, resolves=resolves)

    def check_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue | Await:
        """Two deterministic gates: is it a contract, and is it grounded?

        `validate_story` + `decide_validate_story` + `check_story_grounding` +
        `decide_story_grounding`. Structure first, because a story that is not a contract
        cannot be grounded in anything; then grounding, which is presence and nothing
        semantic — refuting the story is the auditor's job.
        """
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        structure = self.call(validate_story, story_dir)
        if not structure.ok:
            return self._rework(structure, structure.errors, story, reworks, resolves)
        grounding = self.call(
            check_story_grounding, story_dir, self._epic_dir(epic), self.ctx.features_dir
        )
        if not grounding.ok:
            return self._rework(grounding, grounding.errors, story, reworks, resolves)
        return Continue(grounding, self.audit_story, **story, reworks=reworks, resolves=resolves)

    def audit_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue | Await:
        """A skeptical reader tries to refute that a coder could build this.

        `audit_story` + `decide_story_audit`. `failed` is the only arm that reworks: the
        YAML declared `default: {status: passed}` for this node, and the default branch
        was `passed` too, so an unreadable audit upholds the story either way.
        """
        result = self.agent(
            "prompts/audit-story.md",
            returns=AuditResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
            },
        )
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        if result.status == "failed":
            return self._rework(result, result.notes, story, reworks, resolves)
        return Continue(result, self.story_feedback, **story, reworks=reworks, resolves=resolves)

    def _rework(
        self, result: object, notes: str, story: dict[str, object], reworks: int, resolves: int
    ) -> Continue | Await:
        """`guard_story`: one more rework pass, or hand the story to the operator.

        Not a state — the routing half of a branch, called from the three gates that can
        fail a story (structure, grounding, audit). The YAML's three `→ guard_story`
        edges are these three call sites.
        """
        if reworks >= MAX_REWORKS:
            return self._gate_story(result, notes, story, resolves)
        return Continue(result, self.rework_story, **story, notes=notes, reworks=reworks, resolves=resolves)

    def _gate_story(
        self, result: object, notes: str, story: dict[str, object], resolves: int
    ) -> Continue | Await:
        """`gate_write_story` + `guard_write_story_resolve`: resolver, or human.

        Reached from a `blocked` write and from a story-rework loop that will not
        converge — two states, hence a helper rather than an inlined pair of lines.
        Both arms re-enter `write_story` with the rework budget reset, because
        `await_write_story` reset it on the way through.
        """
        context = paths.story_context(str(story["story_dir"]))
        if self.operator_mode == "human" or resolves >= MAX_WRITE_STORY_RESOLVES:
            return Await(self._abs(context), notes, self.write_story, **story, reworks=0, resolves=resolves)
        return Continue(result, self.resolve_story, **story, notes=notes, resolves=resolves)

    def rework_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        notes: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue:
        """Rewrite the story against whichever gate failed it, and what already failed.

        `record_attempt` + `rework_story` + `incr_story`. The ledger is the point of the
        first: a bounded loop that carries only the *latest* failure lets the reworker
        re-try an approach that already failed two laps ago.
        """
        ledger = self.call(
            record_attempt, f"{story_dir.rstrip('/')}/attempts.md", str(reworks), notes
        )
        result = self.agent(
            "prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "validation_errors": notes,
                "prior_attempts": ledger.prior_attempts,
            },
        )
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        return Continue(result, self.check_story, **story, reworks=reworks + 1, resolves=resolves)

    def resolve_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        notes: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        resolves: int = 0,
    ) -> Continue | Await:
        """Stand in for the operator on a story block, or escalate to one.

        `resolve_write_story` + `incr_write_story_resolve` + `await_write_story`.
        """
        context = paths.story_context(story_dir)
        result = self._resolve("write-story", notes, context, self._epic_dir(epic))
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        if result.decision == "answered":
            return Continue(result, self.write_story, **story, reworks=0, resolves=resolves + 1)
        return Await(self._abs(context), notes, self.write_story, **story, reworks=0, resolves=resolves + 1)

    def story_feedback(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue | Done:
        """The story holds. Poll for feedback a human dropped while the run was busy.

        `check_story_feedback` + `decide_story_feedback` + `decide_story_loop` +
        `story_prune`. Never blocks: reading the inbox marks it `CONSUMED`, so one drop
        reworks the story exactly once.

        Story mode ends here, and it ends **without committing** — `decide_story_loop`
        routed `story` to `story_prune`, whose `next` is the `done` terminal. See the
        progress ledger: the story arm of the commit-message builder is unreachable in
        the YAML, and the port reproduces that rather than quietly fixing it.
        """
        feedback = self.call(check_story_feedback, paths.story_feedback(story_dir))
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        if feedback.present:
            return Continue(
                feedback,
                self.apply_feedback,
                **story,
                notes=feedback.content,
                reworks=reworks,
                resolves=resolves,
            )
        if self.mode == "story":
            seeded = self.output(seed_story)
            return Done(self.call(prune_bullet, self.backlog, seeded.bullet_id, seeded.from_backlog))
        return Continue(
            feedback, self.next_story, epic=epic, cov_reworks=cov_reworks, split_resolves=split_resolves
        )

    def apply_feedback(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        notes: str,
        mockup: str = "",
        cov_reworks: int = 0,
        split_resolves: int = 0,
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue:
        """Rework the story once against the operator's note, then re-validate.

        `apply_story_feedback`. Its own state, not folded into `story_feedback`, because
        reading the inbox consumed it: a crash between the read and this turn would lose
        the note if one state did both, and the YAML checkpointed between them.

        The rework budget is threaded rather than reset — the YAML's counter was a var
        that still held its value when this edge re-entered the rework loop.
        """
        result = self.agent(
            "prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                # None — the operator's feedback is the work.
                "validation_errors": "",
                "operator_feedback": notes,
            },
        )
        story = self._story(epic, story_slug, story_dir, story_path, mockup, cov_reworks, split_resolves)
        return Continue(result, self.check_story, **story, reworks=reworks, resolves=resolves)

    # --- 2d. epic coverage ----------------------------------------------------

    def check_coverage(
        self, epic: str, cov_reworks: int = 0, split_resolves: int = 0
    ) -> Continue | Await:
        """Every seed of this epic covered by some story — mechanically, then judged.

        `validate_coverage` + `decide_coverage_validate` + `review_coverage` +
        `decide_coverage_review` + `prune_backlog` + `guard_coverage` + `incr_cov`.
        Either failure re-enters `split_stories` with the worklist, bounded; `ok` prunes
        the bullets the epic consumed and moves to the next epic.
        """
        epic_dir = self._epic_dir(epic)
        mechanical = self.call(validate_coverage, epic_dir)
        if not mechanical.ok:
            return self._rework_coverage(
                mechanical, mechanical.errors, epic, cov_reworks, split_resolves
            )
        review = self.agent(
            "prompts/review-coverage.md",
            returns=CoverageReview,
            power="high",
            cwd=self.ctx.repo_root,
            args={"epic": epic, "epic_dir": epic_dir, "backlog": self.backlog},
        )
        if review.status == "ok":
            pruned = self.call(prune_backlog, self.backlog, epic_dir)
            return Continue(pruned, self.next_epic)
        if review.status == "blocked":
            return self._gate_coverage(review, review.notes, epic, split_resolves)
        # `gaps` is also the default arm: a review that returns nothing legible has not
        # accounted for the epic's seeds, and the bounded rework loop is the safe read.
        return self._rework_coverage(review, review.notes, epic, cov_reworks, split_resolves)

    def _rework_coverage(
        self, result: object, notes: str, epic: str, cov_reworks: int, split_resolves: int
    ) -> Continue | Await:
        """`guard_coverage` + `incr_cov`: split again against the gaps, or escalate.

        Not a state — the routing half of a branch, called from the mechanical check and
        from the review's `gaps` arm. The notes travel to `split_stories` as its
        `rework_notes`, which is the whole point of the lap.
        """
        if cov_reworks >= MAX_REWORKS:
            return self._gate_coverage(result, notes, epic, split_resolves)
        return Continue(
            result,
            self.split_stories,
            epic=epic,
            split_resolves=split_resolves,
            cov_reworks=cov_reworks + 1,
            rework_notes=notes,
        )

    def resolve_coverage(
        self, epic: str, notes: str, split_resolves: int = 0
    ) -> Continue | Await:
        """Stand in for the operator on a coverage block, or escalate to one.

        `resolve_coverage` + `await_coverage`. This is the one gate the YAML gave no
        retry budget — the coverage loop's own `cov_rework_count` is the bound — so there
        is no `resolves` here, and `await_coverage` reset the rework counter on the way
        back into `split_stories`.
        """
        context = paths.epic_context(self._epic_dir(epic))
        result = self._resolve("coverage", notes, context, self._epic_dir(epic))
        params = {"epic": epic, "split_resolves": split_resolves}
        if result.decision == "answered":
            return Continue(result, self.split_stories, **params)
        return Await(self._abs(context), notes, self.split_stories, **params)

    def _gate_coverage(
        self, result: object, notes: str, epic: str, split_resolves: int
    ) -> Continue | Await:
        """`gate_coverage`: hand the coverage block to the resolver, or to the human.

        Reached from three places — a `blocked` review, a coverage loop that will not
        converge, and the splitter's `standoff` — so it is a helper. Both arms re-enter
        `split_stories` with the rework budget reset, as `await_coverage` did.
        """
        context = paths.epic_context(self._epic_dir(epic))
        if self.operator_mode == "human":
            return Await(
                self._abs(context), notes, self.split_stories, epic=epic, split_resolves=split_resolves
            )
        return Continue(result, self.resolve_coverage, epic=epic, notes=notes, split_resolves=split_resolves)

    # --- 3. write-time reconciliation ----------------------------------------

    def reconcile(self, resolves: int = 0) -> Continue | Await:
        """Scope this run silently dropped, measured against the last commit.

        `reset_reconcile_resolve` + `verify_reconcile` + `decide_reconcile` +
        `gate_reconcile` + `guard_reconcile_resolve`. Fail-open on `skip`: no git
        baseline is not a defect in the epics.
        """
        report = self.call(verify_reconcile, self.epics_dir)
        if report.holds or report.skipped:
            return Continue(report, self.integrity)
        if self.operator_mode == "human" or resolves >= MAX_RECONCILE_RESOLVES:
            return Await(self._abs(self._author_context()), report.errors, self.integrity)
        return Continue(report, self.resolve_reconcile, notes=report.errors, resolves=resolves)

    def resolve_reconcile(self, notes: str, resolves: int = 0) -> Continue | Await:
        """Investigate each dropped entity: meant to go, or a regression to restore?

        `resolve_reconcile` + `decide_reconcile_resolve` + `incr_reconcile_resolve`. The
        answered arm re-runs the *same deterministic check* rather than trusting the
        resolver's say-so, and `escalated` skips that recheck because the resolver has
        told us the state is unchanged.
        """
        result = self._resolve("reconciliation", notes, self._author_context(), self.epics_dir)
        if result.decision == "escalated":
            return Await(self._abs(self._author_context()), notes, self.integrity)
        return Continue(result, self.reconcile, resolves=resolves + 1)

    # --- 4. referential integrity --------------------------------------------

    def integrity(self, resolves: int = 0) -> Continue | Await:
        """`ostler doctor` over the whole planning-doc graph.

        `reset_integrity_resolve` + `verify_integrity` + `decide_integrity` +
        `gate_integrity` + `guard_integrity_resolve`. Warnings never block; error-level
        findings do. `await_integrity` deliberately does not loop back to re-run the
        check — final validation is the backstop for whatever the human path leaves.
        """
        report = self.call(verify_integrity)
        if report.holds or report.skipped:
            return Continue(report, self.close)
        if self.operator_mode == "human" or resolves >= MAX_INTEGRITY_RESOLVES:
            return Await(self._abs(self._author_context()), report.errors, self.close)
        return Continue(report, self.resolve_integrity, notes=report.errors, resolves=resolves)

    def resolve_integrity(self, notes: str, resolves: int = 0) -> Continue | Await:
        """Relink each graph break with `ostler edit` — never by deleting a reference.

        `resolve_integrity` + `decide_integrity_resolve` + `incr_integrity_resolve`. Its
        own prompt, not the shared resolver: the argument names differ (`epics_dir`,
        `integrity_errors`) because the work is mechanical reconciliation, not Q&A.
        """
        self.logger.info("resolving the integrity block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-integrity.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self._author_context(),
                "epics_dir": self.epics_dir,
                "integrity_errors": notes,
            },
        )
        if result.decision == "escalated":
            return Await(self._abs(self._author_context()), notes, self.close)
        return Continue(result, self.integrity, resolves=resolves + 1)

    # --- 5. final validation, and the git tail -------------------------------

    def close(self) -> Done:
        """Validate everything the run wrote, then commit it and open the PR.

        `validate_artifacts` + `decide_artifacts` + `commit_incomplete` + `commit_author`
        + `open_author_pr` + the `done` / `author_failed` terminals.

        Broken work neither vanishes nor gets a PR: the partial docs are committed under
        an unmistakable message — a rerun resumes from them — and *then* the run ends
        red. The two commit nodes are one node called with two modes, because that is all
        `commit-author.py` ever did with the difference.
        """
        report = self.call(validate_artifacts)
        if not report.ok:
            self.call(commit_author, "incomplete", self.epic, self.bullet)
            raise WorkflowFailed(f"authored artifacts did not validate:\n{report.errors}")
        self.call(commit_author, self.mode, self.epic, self.bullet)
        return Done(
            self.call(
                open_author_pr,
                self.ctx.base_branch,
                self.ctx.author_branch,
                self.mode,
                self.epic,
                self.bullet,
            )
        )


workflow = (
    Registry("author")
    .add_blueprints(blueprint, survey_blueprint)
    .add_flows(surveyor=Surveyor, **{"parity-surveyor": ParitySurveyor})
    .stub_agents(
        {
            "review-epics": {"status": "approved"},
            "write-epic": {"status": "complete"},
            "split-stories": {"status": "complete"},
            "write-story": {"status": "written"},
            "audit-story": {"status": "passed"},
            "review-coverage": {"status": "ok"},
            "resolve-operator": {"decision": "answered"},
            "resolve-integrity": {"decision": "answered"},
            # The sub-flows' turns. Keyed by prompt STEM, so `prompts/resolve-operator.md`
            # and `prompts/surveyor/resolve-operator.md` share the entry above — which
            # is what they want here, both being the same operator-resolution reply.
            "plan-units": {"status": "complete"},
            "assess-unit": {"status": "assessed"},
            "assess-parity-unit": {"status": "assessed"},
            "fix-record": {"status": "fixed"},
            "partition-findings": {"status": "complete"},
        }
    )
)
main = workflow.main(Author)
