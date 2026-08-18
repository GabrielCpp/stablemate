"""Plan a story and implement it, one service layer at a time — the port of
`coder/workflow.yaml`'s `flows.dev` (35 nodes, lines 1349-1832).

It is reached from the main graph as a `type: flow` node, and standalone as
`workhorse-coder run dev`. Three loops share the same states rather than nesting::

    plan → (reuse gate)* → (path gate)* → dispatch → (layer → implement → (lint → fix)* )*

Thirty-five nodes become twelve states — fifteen once the implement turn split into the
tests / red-gate / code chain, which is post-port work with no YAML counterpart (see
`shared/red_gate.py`). Six of the thirty-five are `type: branch` routers
that read a value the node directly above them had just produced, so each folds into the
`if` at the end of the state that produced it; five more are `type: call fn: seed/incr`
counter nodes, which disappear entirely, because a counter is a state parameter now. What is
left is the work: four agent turns (two of them the same prompt at three call sites), five
deterministic nodes, and the operator gate.

**The operator gate never decides on the operator's behalf, exactly as `author` and
`surveyor` settled it.** `resolve_plan` below investigates and always `Await`s — it does
not read a `decision` field to choose between looping and waiting, because there is no
loop it could choose instead: a block always parks. `_gate_plan` decides only whether the
resolver gets a turn first (`plan_blocks` below `MAX_PLAN_BLOCKS`) or the block goes
straight to a human — never whether to wait at all. The half of `await_operator.py` that
is not about waiting — read the answer, take its `SCOPE:`, flip `ANSWERED` to `CONSUMED`
— is `read_operator_context`, a node.

Divergences from the YAML, all deliberate:

* `current_layer_index` was a var; it is the `layer` state's parameter, which is the port
  rule for a loop cursor. `plan_rework_count`, `reuse_rework_count` and `lint_rework_count`
  go the same way, and their `seed`/`incr` nodes go with them.
* **`branch` is an input.** `branch_code_repos`'s YAML argument was
  `get_node_output('branch_story', 'story_branch') or story` — a read across the flow
  boundary into a node the *main graph* runs. The main graph passes it in explicitly now,
  and a standalone run still falls back to the story slug, which is what the `or` did.
* `guard_validate`'s comment cites `vars.max_validate_reworks`, which the flow never
  declares — the literal `"3"` is the only budget there is. It is `MAX_VALIDATE_REWORKS`
  here, a `ClassVar` rather than an input, so the port does not invent an operator control
  the YAML did not have. Recorded in the progress ledger as a finding; it is the same
  inert-var shape as `genesis`'s `max_genesis_reworks`.
* `stamp_specs` runs after the first plan turn only, never after a refine pass — which is
  the YAML's wiring (`rework_plan` goes straight back to `decide_plan`) and not obviously
  intended, since a refine pass rewrites the same spec docs. Behavior preserved, recorded as
  a finding.
* `validate_plan` is `validate_paths` here, and the name is not a preference. `Workflow`
  is a pydantic model, state discovery skips every name already on `dir(Workflow)`, and
  `validate` is one of them — pydantic v1's deprecated classmethod. A state called
  `validate` would not be a state at all: no error, no warning, just a transition to a
  target nothing dispatches. It is the one reserved name any of the four workflows came
  close to taking, and it is recorded in the progress ledger.
* the three `refine-plan.md` call sites share one node id (the driver ids an agent node by
  its prompt stem), where the YAML had three. Nothing reads that output by node name, and
  each site's *next* state is what distinguished them.
* **`plan_blocks` bounds the *resolver*, not the block.** It counts trips through
  `_gate_plan` that actually invoked `resolve_plan`, and is the only counter that
  survives an operator answer. Once it reaches `MAX_PLAN_BLOCKS`, `_gate_plan` stops
  spending a resolver turn and routes every further block straight to a human — it does
  not fail the run and it does not stop counting the story's trips back to this gate,
  because there is no cap on those: a plan blocked forever keeps coming back to this gate
  forever, across as many resumes as it takes (AGENTS.md, "a workflow never gives up —
  it can only be blocked"). Two cycles feed it. A plan that comes back `blocked` from
  every refine pass laps `_gate_plan → resolve_plan → read_operator → rework_plan →
  _gate_plan`; and a service path nothing can repair laps the *wider* ring —
  `validate_paths` spends its three reworks, escalates, and `read_operator` hands back a
  plan stage whose `plan_rework` has been reset to 0 (see its docstring: the YAML
  re-emitted `plan_rework_count: 0`, and that reset is deliberate), so the same three
  reworks are spent again. Both laps run the unbounded-timeout resolver at
  `power="high"`. `plan_blocks` is therefore threaded through the reuse and path gates
  too, not just the operator states.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.dev import (
    branch_code_repos,
    read_operator_context,
    resolve_impl_context,
    run_lint,
    select_next_layer,
    validate_plan_context,
)
from workhorse_workflows.coder.shared.escalation import escalation
from workhorse_workflows.coder.shared.red_gate import arm_red_gate, run_red_gate
from workhorse_workflows.coder.shared.story import (
    prepare_story,
    resolve_workspace_dirs,
    stamp_specs,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    DevResult,
    FixLintResult,
    ImplResult,
    OperatorGate,
    OperatorResolution,
    PlanResult,
    ReuseResult,
    TestsResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels

#: `timeout: infinity` — the resolver stands in for a human and must not be cut off
#: mid-resolution. A finite number of seconds here caps it.
UNBOUNDED = float("inf")

#: Layer types with no behavior a test can observe red — a docs layer and an infra plan
#: take the classic single implement turn instead of the tests/code split.
NON_TDD_TYPES = ("docs", "terraform")


class Dev(Workflow):
    """Plan a story, gate the plan three ways, then implement it service by service."""

    #: The story slug. ostler resolves the story path and spec dir from it.
    story: str = ""
    #: The docs repo root, when the planning documents live in a checkout of their own.
    #: Empty walks up from `repo_dir`, i.e. the docs sit beside the code.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""
    #: The epic slug. Empty finds the story under whichever epic carries it.
    epic: str = ""
    #: `auto` stands a high-effort agent in for the operator; `human` halts and waits.
    operator_mode: str = "auto"
    #: `local` or `dev` — which environment the run targets. Decides whether `-local` QA
    #: skills survive into the QA plan.
    target_env: str = "local"
    #: The story branch every code repo should be on. Empty falls back to the story slug.
    #: See the module docstring: the YAML read this off the main graph's `branch_story`.
    branch: str = ""
    #: Per-layer lint fix attempts before the loop moves on. QA re-runs lint as the binding
    #: gate, so the dev-time one is self-healing best-effort and never a dead end.
    max_lint_reworks: int = 2
    #: Plan-level code-reuse rework passes before implementation proceeds anyway.
    max_reuse_reworks: int = 2
    #: Per-layer trips back to the tests turn when the red gate rejects it (a green suite,
    #: production code in the diff, no test file written, or a red the new tests did not
    #: cause). Spent, the layer proceeds fail-open: the reviewer's
    #: coverage audit is the binding check, and a gate must not dead-end the loop.
    max_tests_reworks: int = 2


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: Path-validation rework passes before the block goes to the operator. `ClassVar`
    #: because the YAML exposed no var for it — see the module docstring.
    MAX_VALIDATE_REWORKS: ClassVar[int] = 3

    #: Trips through the operator gate that get a resolver turn before every further
    #: block goes straight to a human — not a cap on how many times the plan stage may
    #: block; there isn't one. `ClassVar` for the same reason: the YAML had no bound at
    #: all here, so exposing one as an input would invent an operator control the port
    #: is not entitled to invent.
    MAX_PLAN_BLOCKS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories.

        Neither is decided on by any state below — every one of them reads the same paths
        and hands the same directory list to its agent turn — so both are `setup`. The
        workspace list is read back with `self.output` rather than returned, because
        `self.ctx` is one value and the paths are what nearly every state wants.

        `prepare_story` is also the authored-story gate: a story ostler knows and reports
        unauthored fails the run here rather than being planned against.
        """
        self.call(resolve_workspace_dirs, self.docs_path)
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    #: The three bounded budgets, each already a parameter of the state that guards it.
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = (
        "plan_rework",
        "reuse_rework",
        "tests_rework",
        "lint_rework",
        "plan_blocks",
    )

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on.

        A state that does not take a given counter reports nothing for it rather than
        zero — `implement` has no opinion about the reuse budget.
        """
        return self.labels() | counter_labels(params, "dev", self.BUDGET_LABELS)

    # --- planning -----------------------------------------------------------

    def start(self) -> Continue | Await:
        """Author the plan, stamp what it wrote, and route on whether it is blocked.

        `plan` + `stamp_specs_plan` + `decide_plan`. The plan gate is deliberately
        permissive: a blank status takes the YAML's `default:` arm, which is `done`, because
        depth and correctness are enforced downstream by implementation review and by QA,
        not by a second plan-reviewing agent — one was tried and caught nothing actionable.
        Only a genuine `blocked` — a dangerous or undecidable prod operation the planner
        could not resolve — reaches the operator.
        """
        self.logger.info("planning %s", self.ctx.story_slug, extra={"activity": True})
        result = self.agent(
            "prompts/plan-story.md",
            returns=PlanResult,
            # high: authors the plan, including high-stakes prod operations (deploys,
            # security-group / egress changes) — worth the stronger reasoning.
            power="high",
            add_dirs=self._dirs(),
            args={"story_path": self.ctx.story_path, "spec_dir": self.ctx.spec_dir},
        )
        # The plan agent writes plan.md / plan-<svc>.md / executive.md as free-form
        # markdown, so the frontmatter that makes them OKF Concepts is only as reliable as
        # the model's memory. Stamp it mechanically instead of trusting the prompt.
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "blocked":
            return self._gate_plan(result, result.summary, 0)
        return Continue(result, self.check_reuse, notes=result.summary)

    def _gate_plan(self, result: object, notes: str, plan_blocks: int) -> Continue | Await:
        """`gate_plan`: hand the block to the resolver, or straight to a human.

        Not a state — it is the routing half of a branch, called from the two states that
        can decide the plan stage is stuck (`start`/`rework_plan`'s `blocked`, and
        `validate`'s exhausted budget). `_`-prefixed so state discovery does not pick it up.

        There is no dead end here: a block always reaches a human eventually, either
        through the resolver or directly once `plan_blocks` is spent — never a terminal
        failure. `result` is unused once escalating straight to a human, but is threaded
        through so the resolver arm can still `Continue` it into `resolve_plan`.
        """
        if self.operator_mode in {"human", "operator"} or plan_blocks >= self.MAX_PLAN_BLOCKS:
            gate = self._escalation(notes, plan_blocks)
            return Await(
                self._context, gate.body, self.read_operator, notes=notes, plan_blocks=plan_blocks
            )
        return Continue(result, self.resolve_plan, notes=notes, plan_blocks=plan_blocks)

    def resolve_plan(self, notes: str, plan_blocks: int = 0) -> Await:
        """Investigate a plan block, then park for the operator.

        `resolve_plan` + the `await_operator` that followed it unconditionally; see the
        module docstring. The resolver never decides on the operator's behalf — it only
        investigates and writes findings into the story's `context.md`, so this always
        ends in an `Await`.
        """
        self.logger.info("resolving the plan block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # high, and unbounded: it is investigating a block, with full tool access,
            # on the highest-stakes decision in the flow.
            power="high",
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "block_kind": "plan",
                "block_notes": notes,
            },
        )
        # The resolver has already written `STATUS: AWAITING_OPERATOR` into this very
        # file, with what it tried and what the human must supply — and `Await` writes
        # its `questions` with `write_text`, so anything handed here replaces that note.
        # The composed body carries it forward verbatim, which is what makes it safe to
        # ask a question at this gate at all; passing `notes` alone would have left the
        # human reading the block summary instead of the investigation.
        gate = self._escalation(notes, plan_blocks, result)
        return Await(
            self._context,
            gate.body,
            self.read_operator,
            notes=notes,
            plan_blocks=plan_blocks + 1,
        )

    def read_operator(self, notes: str, plan_blocks: int = 0) -> Continue | Done:
        """Consume the answer and route on the scope the answerer chose.

        `await_operator`'s consume half + `decide_operator_scope`. The answer may reveal the
        whole epic premise was wrong — a target environment that does not exist — rather
        than just this story's plan, and `SCOPE: epic` in `context.md` is how that is said:
        it leaves the flow entirely so the queue level replans the epic. Anything else,
        blank included, reworks this plan.

        `plan_rework` is not threaded past here. The YAML's `await_operator` re-emitted
        `plan_rework_count` as 0, so an answered block restores the full path-validation
        budget; the reset is the transition below not carrying the counter. `plan_blocks`
        *is* carried, and that asymmetry is the point: an operator answer is a fresh licence
        to re-validate, not a fresh licence to escalate. Reset both and the path gate laps
        forever.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the fix to the epic — handing back to replan")
            return Done(DevResult(status="replan", operator_notes=answer.content))
        return Continue(
            answer,
            self.rework_plan,
            notes=notes,
            operator_context=answer.content,
            plan_blocks=plan_blocks,
        )

    def rework_plan(
        self, notes: str, operator_context: str, plan_blocks: int = 0
    ) -> Continue | Await:
        """Re-plan with the operator's answer in hand, and re-evaluate the same gate.

        A still-blocked re-plan re-gates the operator, which is what makes the loop honest:
        a resolver that did not actually resolve anything cannot wave the plan through — and
        bounded, which is what keeps honest from meaning endless.
        """
        result = self._refine(review_notes=notes, operator_context=operator_context)
        if result.status == "blocked":
            return self._gate_plan(result, result.summary, plan_blocks)
        return Continue(
            result, self.check_reuse, notes=result.summary, plan_blocks=plan_blocks
        )

    # --- the reuse gate -----------------------------------------------------

    def check_reuse(self, notes: str, reuse_rework: int = 0, plan_blocks: int = 0) -> Continue:
        """Does the approved plan propose to build something that already exists?

        `seed_reuse` + `check_code_reuse` + `decide_reuse` + `guard_reuse`. Checked against
        the existing codebase *before* any code is written, which is the whole point — this
        is the mitigation for the workflow re-implementing what it never looked for.

        Fail-open and bounded: a check that did not run takes the `ok` arm, and once the
        rework budget is spent implementation proceeds anyway, because the findings are
        advisory and review and QA re-check reuse against the real diff.
        """
        result = self.agent(
            "prompts/check-code-reuse.md",
            returns=ReuseResult,
            # high: a semantic "does this already exist?" search across the codebase is a
            # genuine reasoning and discovery task.
            power="high",
            add_dirs=self._dirs(),
            args={"story_path": self.ctx.story_path, "spec_dir": self.ctx.spec_dir},
        )
        if result.status == "needs_rework" and reuse_rework < self.max_reuse_reworks:
            return Continue(
                result,
                self.rework_reuse,
                notes=notes,
                reuse_rework=reuse_rework,
                findings=str(result.findings),
                plan_blocks=plan_blocks,
            )
        return Continue(result, self.validate_paths, notes=notes, plan_blocks=plan_blocks)

    def rework_reuse(
        self, notes: str, reuse_rework: int, findings: str, plan_blocks: int = 0
    ) -> Continue:
        """Re-plan to reuse what the check found, then re-check.

        `rework_plan_reuse` + `incr_reuse`. No operator context: this is a plan-quality
        rework, not a resolved block, and handing the refiner a stale operator answer would
        invite it to re-litigate a decision that was already made.
        """
        result = self._refine(
            review_notes=(
                "The plan re-implements functionality that already exists in the codebase. "
                "Rework it to REUSE the existing code instead of rebuilding it, or justify "
                f"per-finding why reuse is not possible. Reuse findings: {findings}"
            ),
            operator_context="",
        )
        return Continue(
            result,
            self.check_reuse,
            notes=notes,
            reuse_rework=reuse_rework + 1,
            plan_blocks=plan_blocks,
        )

    # --- the path gate ------------------------------------------------------

    def validate_paths(
        self, notes: str, plan_rework: int = 0, plan_blocks: int = 0
    ) -> Continue | Await:
        """Do the planner's declared service paths point at real services?

        `validate_plan` + `decide_validation` + `guard_validate`. A validator that cannot
        speak is not evidence of a bad plan, so a blank status takes the `valid` arm.
        Deterministic case repair happens inside the node, so what survives to a `invalid`
        verdict is genuinely unfixable by a blind refine pass — a missing marker, a
        nonexistent path, an unresolvable repo — which is why the exhausted budget escalates
        to the operator rather than proceeding.
        """
        result = self.call(validate_plan_context, self.ctx.spec_dir)
        if result.status != "invalid":
            return Continue(result, self.dispatch)
        if plan_rework >= self.MAX_VALIDATE_REWORKS:
            return self._gate_plan(result, notes, plan_blocks)
        return Continue(
            result,
            self.rework_paths,
            notes=notes,
            plan_rework=plan_rework,
            errors=str(result.errors),
            plan_blocks=plan_blocks,
        )

    def rework_paths(
        self, notes: str, plan_rework: int, errors: str, plan_blocks: int = 0
    ) -> Continue:
        """Re-plan against the validation errors, then re-validate.

        `rework_plan_paths` + `incr_plan_rework`. The counter the YAML bumped in a separate
        node — agent nodes could not also emit one — is the parameter on the way back.
        """
        result = self._refine(
            review_notes=f"Service path validation failed: {errors}", operator_context=""
        )
        return Continue(
            result,
            self.validate_paths,
            notes=result.summary or notes,
            plan_rework=plan_rework + 1,
            plan_blocks=plan_blocks,
        )

    # --- implementation -----------------------------------------------------

    def dispatch(self) -> Continue:
        """Decode the approved plan against the workspace, and branch every code repo.

        `resolve_impl_context` + `branch_code_repos`. Both are deterministic, neither is
        branched on, and the second only makes sense once the first has established which
        repos the plan touches — so they are one state. `branch_code_repos` runs here rather
        than at the top of the flow because `plan-context.json` did not exist until the plan
        did: the docs repo was branched much earlier, when it was the only thing the run
        knew about.
        """
        impl = self.call(
            resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path
        )
        self.logger.info("implementing %d service layer(s)", impl.dispatch_count)
        self.call(
            branch_code_repos, self.ctx.spec_dir, self.branch or self.story, self.docs_path
        )
        return Continue(impl, self.layer)

    def layer(self, index: int = -1) -> Continue | Done:
        """Take the next service to implement, or finish.

        `select_impl_layer` + `decide_impl_layer`. `index` is the cursor the YAML kept in
        `current_layer_index`; an exhausted dispatch list is the loop's success exit, and
        the only other way out of this flow is the operator's epic-scoped replan.
        """
        pick = self.call(select_next_layer, self.ctx.spec_dir, index)
        if not pick.has_layer:
            self.logger.info("every service layer implemented")
            return Done(DevResult())
        self.logger.info(
            "implementing %s (%d/%d)", pick.layer.label, pick.index + 1, pick.dispatch_count
        )
        return Continue(pick, self.implement, index=pick.index)

    def implement(self, index: int) -> Continue:
        """Route one service layer into the tests/code split, or the classic single turn.

        The split is the TDD contract made structural: the tests land alone, `run_red_gate`
        *observes* them fail, and only then does the code turn begin — the plan's Test
        Scenarios enforced by tooling rather than requested by prompt. Two layer shapes
        stay on the classic `implement-plan.md` turn: the `NON_TDD_TYPES` (nothing a test
        can observe red) and a plan that carries one of the two escapes — `regression_only`
        and `qa_only` — which `arm_red_gate` reads off the plan text so the decision stays
        the planner's rather than becoming a heuristic here.

        `arm_red_gate` must run *before* the tests turn — it records the worktree baseline
        the gate later diffs against, so pre-existing dirt is never charged to that turn.
        """
        layer = self._layer
        if layer.type in NON_TDD_TYPES:
            self._implement_classic()
            return Continue(None, self.lint, index=index)
        arm = self.call(
            arm_red_gate, layer.cwd, layer.service, self.ctx.spec_dir, layer.plan_file
        )
        if arm.mode in {"regression_only", "qa_only"}:
            self._implement_classic()
            return Continue(None, self.lint, index=index)
        return Continue(arm, self.implement_tests, index=index)

    def implement_tests(
        self, index: int, tests_rework: int = 0, gate_feedback: str = ""
    ) -> Continue:
        """Write the plan's Test Scenarios as failing tests — tests only, no production code.

        The first half of the split. The prompt is told the exact command the gate will run
        and, on a rework lap, why the gate rejected the previous attempt. Its own `done` is
        not branched on: the red gate downstream is the verdict. Its `blocked` *is* carried
        forward, and only as a second condition — see `red_gate`.
        """
        layer = self._layer
        arm = self.output(arm_red_gate)
        impl = self.output(resolve_impl_context)
        tests = self.agent(
            "prompts/implement-plan-tests.md",
            returns=TestsResult,
            # high: translating acceptance criteria into tests that can genuinely fail is
            # a design task, not transcription.
            power="high",
            cwd=layer.cwd,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "plan_file": layer.plan_file,
                "service_path": layer.service_path,
                "service_type": layer.type,
                "test_command": arm.test_command,
                "impl_instruction_paths": impl.impl_instruction_paths,
                "gate_feedback": gate_feedback,
            },
        )
        return Continue(
            None,
            self.red_gate,
            index=index,
            tests_rework=tests_rework,
            tests_blocked=tests.status == "blocked",
        )

    def red_gate(
        self, index: int, tests_rework: int = 0, tests_blocked: bool = False
    ) -> Continue:
        """Hold the tests turn to its contract: a pure diff, observed genuinely red.

        Deterministic, like the lint gate, and fail-open the same way: `red` and `skipped`
        (and a blank) proceed to the code turn, while `all_green`, `impure`, `no_tests` and
        `unattributed_red` loop back to the tests turn with the reason as its brief — until
        the budget is spent, at which point the layer proceeds anyway and the reviewer's
        coverage audit is what catches it.

        One rejection is not reworked: a `no_tests` over an *empty* diff from a turn that
        itself reported `blocked`. That conjunction is the turn saying "there is nothing
        here I am permitted to write", and it is right often enough — a plan whose whole
        scenario list is QA-only, a layer whose acceptance is a live browser — that
        re-asking it twice more only buys two identical refusals at high power. Both
        conditions are required: a `blocked` turn that *did* write files is a partial
        attempt worth reworking, and an empty diff from a turn claiming `done` is a turn
        that did nothing and should be asked again.
        """
        layer = self._layer
        arm = self.output(arm_red_gate)
        outcome = self.call(
            run_red_gate,
            layer.cwd,
            layer.service,
            self.ctx.spec_dir,
            arm.baseline,
            arm.test_command,
            arm.signatures,
        )
        rejected = outcome.status in {"all_green", "impure", "no_tests", "unattributed_red"}
        futile = (
            outcome.status == "no_tests" and not outcome.changed_files and tests_blocked
        )
        if futile:
            self.logger.warning(
                "tests turn reported blocked and wrote nothing — skipping the remaining "
                "rework(s) and proceeding to the code turn"
            )
        if rejected and not futile and tests_rework < self.max_tests_reworks:
            return Continue(
                outcome,
                self.implement_tests,
                index=index,
                tests_rework=tests_rework + 1,
                gate_feedback=f"[{outcome.status}] {outcome.reason}",
            )
        if rejected and not futile:
            self.logger.warning(
                "red gate still %s after %d rework(s) — proceeding fail-open",
                outcome.status,
                tests_rework,
            )
        return Continue(outcome, self.implement_code, index=index)

    def implement_code(self, index: int) -> Continue:
        """Make the observed-red tests green — the second half of the split.

        `cwd` is the service repo, which is what lets workhorse resolve a repo-specific
        flavor override and the right `CLAUDE.md`; the story, spec and plan files live in
        the docs repo, so every workspace directory is granted explicitly — a backend whose
        sandbox allows only cwd and its subdirectories cannot read the plan otherwise.

        `impl_instruction_paths`, `qa_run_plan` and `qa_stack` are passed for the reason
        the classic turn passes them: `Engine.agent` renders against `args` and nothing
        else, so a value a prompt reads has to be passed. The red observation rides along
        so the turn knows what it owes green, and its log so a reviewer can check the
        red run actually happened.
        """
        layer = self._layer
        impl = self.output(resolve_impl_context)
        outcome = self.output(run_red_gate)
        self.agent(
            "prompts/implement-plan-code.md",
            returns=ImplResult,
            # high: writes the production change, across whatever the plan touches.
            power="high",
            cwd=layer.cwd,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "plan_file": layer.plan_file,
                "service_path": layer.service_path,
                "service_type": layer.type,
                "verification": layer.verification,
                "impl_instruction_paths": impl.impl_instruction_paths,
                "qa_run_plan": impl.qa_run_plan,
                "qa_stack": impl.qa_stack,
                "red_status": outcome.status,
                "red_log_path": outcome.log_path,
                "red_failing_files": ", ".join(outcome.failing_files),
            },
        )
        return Continue(None, self.lint, index=index)

    def _implement_classic(self) -> None:
        """The original single `implement-plan.md` turn, for the layers the split skips.

        A helper rather than a state: both callers are arms of `implement`, and the fix
        lane elsewhere still runs this same prompt — see its docstring history in git for
        why the last three args are passed explicitly.
        """
        layer = self._layer
        impl = self.output(resolve_impl_context)
        self.agent(
            "prompts/implement-plan.md",
            returns=ImplResult,
            # high: writes the production change, across whatever the plan touches.
            power="high",
            cwd=layer.cwd,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "plan_file": layer.plan_file,
                "service_path": layer.service_path,
                "service_type": layer.type,
                "verification": layer.verification,
                "impl_instruction_paths": impl.impl_instruction_paths,
                "qa_run_plan": impl.qa_run_plan,
                "qa_stack": impl.qa_stack,
            },
        )

    def lint(self, index: int, lint_rework: int = 0) -> Continue:
        """Run this service's lint, and route on whether it is clean.

        `lint_layer` + `decide_lint_layer` + `guard_lint`. A deterministic backstop to the
        implement turn's own `make lint` done-criterion. `skipped` is the opt-out — a
        service adopts the gate by defining the target or an `agents.yml` override — and a
        blank status takes the YAML's `default:` arm, which is "move on to the next layer".
        """
        result = self.call(run_lint, self._layer.cwd, self._layer.service)
        if result.status == "dirty" and lint_rework < self.max_lint_reworks:
            return Continue(result, self.fix_lint, index=index, lint_rework=lint_rework)
        return Continue(result, self.layer, index=index)

    def fix_lint(self, index: int, lint_rework: int) -> Continue:
        """Satisfy the linter, then re-run it.

        `fix_lint` + `incr_lint`. The findings come off the lint node's own output rather
        than through the transition: they are what this state *consumes*, not what the
        routing decision was made on, and a lint log is exactly the sort of thing that
        should not be copied through a checkpoint.
        """
        outcome = self.output(run_lint)
        self.agent(
            "prompts/fix-lint.md",
            returns=FixLintResult,
            # medium: mechanical — satisfy the linter in one service cwd, grounded in the
            # exact findings. Not a design task.
            power="medium",
            cwd=self._layer.cwd,
            add_dirs=self._dirs(),
            args={
                "service": self._layer.service,
                "cwd": self._layer.cwd,
                "lint_command": outcome.command,
                "lint_output": outcome.output,
            },
        )
        return Continue(None, self.lint, index=index, lint_rework=lint_rework + 1)

    # --- shared -------------------------------------------------------------

    def _refine(self, *, review_notes: str, operator_context: str) -> PlanResult:
        """The `refine-plan.md` turn, shared by the three states that re-plan.

        One helper rather than three copies of the same call: what distinguished the YAML's
        three refine nodes was their `review_notes` and where they went next, and both of
        those are the caller's.
        """
        return self.agent(
            "prompts/refine-plan.md",
            returns=PlanResult,
            # high: re-plans high-stakes prod work, and must absorb an operator's answer
            # about a dangerous operation without re-raising a block that was resolved.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": review_notes,
                "operator_context": operator_context,
            },
        )

    @property
    def _layer(self):
        """The service layer currently being implemented.

        Read off `select_next_layer`'s recorded output rather than threaded through the
        implement/lint/fix states as a parameter: it is a eleven-field record that three
        states merely *consume*, and nothing between here and the next `layer` call can
        change which layer is current.
        """
        return self.output(select_next_layer).layer

    def _escalation(
        self,
        notes: str,
        plan_blocks: int,
        result: OperatorResolution | None = None,
        block_kind: str = "plan",
        where: str = "the plan stage",
        findings: Sequence[Finding] = (),
    ) -> OperatorGate:
        """The gate body for a block in this lane — see `coder.shared.escalation`.

        `block_kind` and `where` are parameters rather than the constants they were,
        because the plan stage is no longer the only thing in this flow that can block: any
        node that reports it cannot finish escalates through here, and the operator's first
        question is which one did.
        """
        return escalation(
            self,
            block_kind=block_kind,
            where=where,
            notes=notes,
            number=plan_blocks,
            result=result,
            findings=findings,
        )

    @property
    def _context(self) -> Path:
        """The file an `Await` writes its questions into: `<story-folder>/context.md`.

        Next to the story, so the operator answering is reading the story it is about.
        """
        return paths.story_context_path(self.ctx.story_path)

    def _dirs(self) -> list[str]:
        """Every directory this run's agent turns may read.

        Resolved once in `setup` and read back here, because an agent turn runs with one
        service repo as its cwd and the story, spec and plan files it works against live in
        the docs root.
        """
        return list(self.output(resolve_workspace_dirs).dirs)


__all__ = ["Dev"]
