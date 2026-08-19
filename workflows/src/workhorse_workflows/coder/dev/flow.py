"""Plan a story and implement it, one service layer at a time — the port of
`coder/workflow.yaml`'s `flows.dev` (35 nodes, lines 1349-1832).

It is reached from the main graph as a `type: flow` node, and standalone as
`workhorse-coder run dev`. Three loops share the same states rather than nesting::

    plan → (path gate)* → dispatch → (layer → implement → (gates → fix)* )*

Thirty-five nodes become twelve states. Six of the thirty-five are `type: branch` routers
that read a value the node directly above them had just produced, so each folds into the
`if` at the end of the state that produced it; five more are `type: call fn: seed/incr`
counter nodes, which disappear entirely, because a counter is a state parameter now. What is
left is the work: four agent turns (two of them the same prompt at three call sites), five
deterministic nodes, and the operator gate.

`implement` used to route between a classic single turn and a tests/red-gate/code split —
the TDD contract made structural, tests landing alone and observed genuinely red before the
code turn began (`shared/red_gate.py`, since deleted). It cost three high-power turns and a
deterministic gate per layer to buy a check the reviewer's coverage audit already makes, and
it is gone: every layer now runs the one `implement-plan.md` turn.

**The operator gate applies decisions; it does not make them.** `resolve_plan` below
reads a `decision` field and has two arms: `answered`, when it can quote the record, rule
or acceptance criterion that already settles the question, and everything else, which
`Await`s. The distinction is whose call it is, not how confident the resolver feels —
`shared/resolution.py` has the whole argument. `_gate_plan` decides something narrower and
unchanged: whether the resolver gets a turn at all (`plan_blocks` below
`MAX_PLAN_BLOCKS`), or the block goes straight to a human. The half of `await_operator.py`
that is not about waiting — read the answer, take its `SCOPE:`, flip `ANSWERED` to
`CONSUMED` — is `read_operator_context`, a node, and it is the consume state *both* arms
land on, because a resolver that answers writes the same file a human would have.

Divergences from the YAML, all deliberate:

* `current_layer_index` was a var; it is the `layer` state's parameter, which is the port
  rule for a loop cursor. `plan_rework_count` and the repair-lap counter go the same way,
  and their `seed`/`incr` nodes go with them.
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
  `power=RESOLVER_POWER`. `plan_blocks` is therefore threaded through the path gate
  too, not just the operator states — and it is spent on a resolver *answer* as
  well as on an escalation, so a resolver that keeps answering the same block keeps
  approaching the human arm rather than laping behind it forever.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.dev import (
    branch_code_repos,
    changed_files,
    read_operator_context,
    resolve_impl_context,
    run_lint,
    select_next_layer,
    validate_plan_context,
)
from workhorse_workflows.coder.shared.escalation import escalation
from workhorse_workflows.coder.shared.failure import from_lint
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    resolver_args,
)
from workhorse_workflows.coder.shared.story import (
    prepare_story,
    resolve_workspace_dirs,
    stamp_specs,
)
from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    DevResult,
    FixResult,
    ImplResult,
    OperatorGate,
    OperatorResolution,
    PlanResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels

#: `timeout: infinity` — the resolver stands in for a human and must not be cut off
#: mid-resolution. A finite number of seconds here caps it.
UNBOUNDED = float("inf")


class Dev(Workflow):
    """Plan a story, gate the plan, then implement and repair it service by service."""

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
    #: Repair laps a service layer gets across **all** its gates before the block goes to
    #: the operator. One budget rather than one per gate: three failing gates repaired twice
    #: each is six turns on one layer, and what the budget is protecting against is the lap,
    #: not the linter.
    max_fix_laps: int = 3
    #: How many turns the story's conversation carries before it is recycled. A conversation
    #: that has read the whole service is what makes lap two cheap, and — several layers and
    #: several laps later — it is also what makes every later turn re-read a context nobody
    #: has needed since. `changed_files` re-seeds the fresh one. 0 never recycles.
    max_session_turns: int = 8
    #: Deprecated and ignored — the two per-gate budgets `max_fix_laps` replaced. Kept as
    #: fields for one release because a checkpoint written before that change carries them,
    #: and a `Workflow` that no longer declares a param a checkpoint holds fails every
    #: in-flight run on reload with a bare pydantic `extra_forbidden`.
    max_lint_reworks: int = 2
    max_reuse_reworks: int = 2
    #: The CLI session id to resume for the story's backbone turns, threaded in from a
    #: prior stage's turn across a `handoff()` boundary. Empty starts a fresh chain.
    session_id: str = ""

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
        "fix_lap",
        "plan_blocks",
    )

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on.

        A state that does not take a given counter reports nothing for it rather than
        zero — `implement` has no opinion about the repair-lap budget.
        """
        return self.labels() | counter_labels(params, "dev", self.BUDGET_LABELS)

    def _chain(self, worklist: str) -> str:
        """The session chain a repair loop runs on, keyed per story and per worklist.

        Per story because two stories planned by one run are two different plans against
        two different diffs; per worklist because the loops that re-plan are asking for
        unrelated things. Sharing one key across them would hand the path-repair pass the
        operator's answer to a block it was never told about — stale context the arguments
        of each loop deliberately withhold.
        """
        return f"plan-{worklist}:{self.ctx.story_slug}"

    def _story_chain(self) -> str:
        """The backbone conversation this story's primary turns run on.

        An incoming session id (threaded from a prior stage across a handoff boundary) is
        resumed directly; otherwise a fresh per-story chain is named and the CLI mints one
        the first time it is used. Distinct from `_chain`: that names the narrower,
        intentionally-isolated plan-repair loops, and stays untouched by this one.

        **The implementation half of the lane shares it.** Implement and every repair turn
        for every layer run here, where each used to open its own conversation: a fixer in a
        fresh context spends its first minutes reading the code the implementer wrote
        minutes earlier, and then reports on a diff it has only just met. `max_session_turns`
        is what keeps that from growing without end.
        """
        return self.session_id or f"story:{self.ctx.story_slug}"

    def _spend_turn(self, session_turns: int) -> int:
        """Count one turn onto the story conversation, recycling it when it is full.

        Called immediately *before* the turn it counts, so the recycling lands on the turn
        that would otherwise have opened the over-long context. The count restarts at one
        rather than zero because the turn about to run is the first of the new conversation.
        """
        if self.max_session_turns and session_turns >= self.max_session_turns:
            self.logger.info(
                "the story conversation reached %d turns — starting a fresh one",
                self.max_session_turns,
            )
            self.reset_session(self._story_chain())
            return 1
        return session_turns + 1

    def _ends(self, result: DevResult) -> Done:
        """End the flow, and every chain it opened with it.

        A chain outliving its flow is what makes a re-run of the same story resume a
        conversation about a plan that has since been rewritten. The backbone chain is the
        exception: `result.session_id` is stamped with whatever id it resolved to, so the
        parent can thread it into the next stage instead of reopening a conversation.
        """
        for worklist in ("block-repair", "path-repair"):
            self.reset_session(self._chain(worklist))
        result.session_id = self._require_engine().session_id(self._story_chain())
        return Done(result)

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
            session=self._story_chain(),
            add_dirs=self._dirs(),
            args={"story_path": self.ctx.story_path, "spec_dir": self.ctx.spec_dir},
        )
        # The plan agent writes plan.md / plan-<svc>.md / executive.md as free-form
        # markdown, so the frontmatter that makes them OKF Concepts is only as reliable as
        # the model's memory. Stamp it mechanically instead of trusting the prompt.
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "blocked":
            return self._gate_plan(result, result.summary, 0)
        return Continue(result, self.validate_paths, notes=result.summary)

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

    def resolve_plan(self, notes: str, plan_blocks: int = 0) -> Continue | Await:
        """Resolve a plan block from what is already written down, or park for the operator.

        `resolve_plan` + the `await_operator` that followed it unconditionally; see the
        module docstring. It no longer follows it unconditionally: a resolver that can
        quote the record, rule or acceptance criterion deciding this question writes the
        answer into `context.md` itself and the flow goes straight to `read_operator`,
        which reads that file either way and cannot tell — nor need to — whether a human
        or the resolver wrote what is in it. See `shared.resolution` for why that is a
        narrowing of who decides rather than a widening.

        `plan_blocks` is spent on both arms. An answered block still counts, because the
        budget's job is to stop this lane laping on a question it keeps failing to settle,
        and a resolver answering the same block three times is exactly that lap — the
        third one lands on `_gate_plan`'s human arm, which is the point.
        """
        self.logger.info("resolving the plan block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # smart, and unbounded: it is investigating a block, with full tool access,
            # on the highest-stakes decision in the flow.
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args=resolver_args(
                self, block_kind="plan", notes=notes, docs_path=self.docs_path
            ),
        )
        if answered(self, result, "plan"):
            return Continue(
                result, self.read_operator, notes=notes, plan_blocks=plan_blocks + 1
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
            return self._ends(DevResult(status="replan", operator_notes=answer.content))
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
        result = self._refine(
            review_notes=notes,
            operator_context=operator_context,
            worklist="block-repair",
        )
        if result.status == "blocked":
            return self._gate_plan(result, result.summary, plan_blocks)
        # The block is resolved: the conversation that was re-planning around it describes
        # a plan this state has just replaced, and the next block is a different one.
        self.reset_session(self._chain("block-repair"))
        return Continue(
            result, self.validate_paths, notes=result.summary, plan_blocks=plan_blocks
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
            self.reset_session(self._chain("path-repair"))
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
            review_notes=f"Service path validation failed: {errors}",
            operator_context="",
            worklist="path-repair",
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

    def layer(self, index: int = -1, session_turns: int = 1) -> Continue | Done:
        """Take the next service to implement, or finish.

        `select_impl_layer` + `decide_impl_layer`. `index` is the cursor the YAML kept in
        `current_layer_index`; an exhausted dispatch list is the loop's success exit, and
        the only other way out of this flow is the operator's epic-scoped replan.
        """
        pick = self.call(select_next_layer, self.ctx.spec_dir, index)
        if not pick.has_layer:
            self.logger.info("every service layer implemented")
            return self._ends(DevResult())
        self.logger.info(
            "implementing %s (%d/%d)", pick.layer.label, pick.index + 1, pick.dispatch_count
        )
        return Continue(
            pick, self.implement, index=pick.index, session_turns=session_turns
        )

    def implement(
        self,
        index: int,
        operator_context: str = "",
        impl_blocks: int = 0,
        session_turns: int = 1,
    ) -> Continue | Await:
        """Implement one service layer with the single `implement-plan.md` turn.

        `operator_context` is an answer to a block this layer already raised, and it is
        threaded rather than read off `read_operator_context`'s output because the layer
        loop re-enters this state for *every* layer: an answer about one service must not
        silently brief the next one's turn.

        `session_turns` counts this story's backbone conversation, which the repair turns
        share — see `_spend_turn`.
        """
        turns = self._spend_turn(session_turns)
        result = self._implement_classic(operator_context)
        if result.blocked:
            return self._gate_impl(
                result, result.notes, index, "the implementation turn", impl_blocks, turns
            )
        return Continue(result, self.gates, index=index, session_turns=turns)

    def _implement_classic(self, operator_context: str = "") -> ImplResult:
        """The `implement-plan.md` turn.

        A helper rather than the state body itself because the fix lane elsewhere still
        runs this same prompt — see its docstring history in git for why the last three
        args are passed explicitly.

        The result is returned rather than discarded, which is the whole of this lane's
        root-cause bug: a turn that reported it could not implement the plan was thrown
        away here, and the layer proceeded to lint an unwritten change.
        """
        layer = self._layer
        impl = self.output(resolve_impl_context)
        return self.agent(
            "prompts/implement-plan.md",
            returns=ImplResult,
            # high: writes the production change, across whatever the plan touches.
            power="high",
            session=self._story_chain(),
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
                "operator_context": operator_context,
            },
        )

    def gates(
        self,
        index: int,
        fix_lap: int = 0,
        session_turns: int = 1,
        digest: str = "",
        impl_blocks: int = 0,
    ) -> Continue | Await:
        """Run this service's deterministic gates, and route on the first one that says no.

        Lint is the gate this state runs today; `shared.failure` is the seam the others
        arrive through, because what `fix` reads is a `FailureReport` and not a lint log.
        A gate that cannot speak — `skipped`, or a blank status — is not a failure: the
        service adopts a gate by defining it, and a service that has not is not thereby
        broken.

        `digest` is the *previous* lap's evidence fingerprint. Two laps whose reports
        digest the same mean the repair turn changed nothing the gate can see, and the
        answer to that is to spend power rather than another identical turn — which is
        what `fix` does with `stalled`.
        """
        outcome = self.call(run_lint, self._layer.cwd, self._layer.service)
        if outcome.status != "dirty":
            return Continue(outcome, self.layer, index=index, session_turns=session_turns)
        report = from_lint(outcome, self._layer.cwd, fix_lap)
        if fix_lap >= self.max_fix_laps:
            # The budget bounds the *lap*, never the story: this hands the failing gate to
            # the resolver and, failing that, to a human, exactly as a blocked implement
            # turn does. See AGENTS.md, "a workflow never gives up".
            return self._gate_impl(
                report,
                f"{self._layer.service}: `{report.command}` still fails after "
                f"{fix_lap} repair lap(s).\n\n{report.output}",
                index,
                "the lint gate",
                impl_blocks,
                session_turns,
            )
        return Continue(
            report,
            self.fix,
            index=index,
            fix_lap=fix_lap,
            session_turns=session_turns,
            stalled=bool(digest) and report.digest == digest,
            impl_blocks=impl_blocks,
        )

    def fix(
        self,
        index: int,
        fix_lap: int,
        session_turns: int = 1,
        stalled: bool = False,
        impl_blocks: int = 0,
    ) -> Continue | Await:
        """Repair whatever the gate reported, then re-run the gates.

        One repair role for every gate, on the story's own conversation: the turn that
        wrote this code is the cheapest turn to fix it, and a fixer in a fresh context
        spends its first minutes re-reading a diff it has only just met. The report is
        rebuilt here from the gate node's recorded output rather than copied through the
        transition — a gate log is exactly the sort of thing that should not go into a
        checkpoint.

        The power ladder is low, low, then high: a linter or a failing assertion is
        mechanical work grounded in exact evidence, and only a lap that has demonstrably
        changed nothing is worth a smarter turn. `stalled` brings that escalation forward.
        """
        report = from_lint(self.output(run_lint), self._layer.cwd, fix_lap)
        turns = self._spend_turn(session_turns)
        result = self.agent(
            "prompts/dev-fix.md",
            returns=FixResult,
            power="high" if stalled or fix_lap >= 2 else "low",
            cwd=self._layer.cwd,
            add_dirs=self._dirs(),
            args={
                # Dumped rather than passed as a model: everything in `args` is
                # checkpointed, and a checkpoint holds JSON.
                "report": report.model_dump(),
                "changed_files": self.call(
                    changed_files, self._layer.cwd, self.ctx.story_slug
                ).paths,
                "service": self._layer.service,
                # The prompt commits its own fix now, and these two are the trailers that
                # tie that commit back to the story it belongs to.
                "epic": self.epic,
                "story_slug": self.ctx.story_slug,
            },
            session=self._story_chain(),
        )
        if result.blocked:
            return self._gate_impl(
                result,
                result.notes or f"the repair turn could not satisfy `{report.command}`",
                index,
                "the repair turn",
                impl_blocks,
                turns,
            )
        return Continue(
            result,
            self.gates,
            index=index,
            fix_lap=fix_lap + 1,
            session_turns=turns,
            digest=report.digest,
            impl_blocks=impl_blocks,
        )

    # --- the implementation gate --------------------------------------------

    def _gate_impl(
        self,
        result: CoderResult,
        notes: str,
        index: int,
        where: str,
        impl_blocks: int,
        session_turns: int = 1,
    ) -> Continue | Await:
        """`implement` said it could not — hand that to the resolver, or to a human.

        The mirror of `_gate_plan` for the implementation half, and the reason this change
        exists: an implementation turn reporting `blocked` used to be discarded, so the
        layer went on to lint a change nobody had written and the run reported success
        several stages later. A gate whose repair budget is spent, and a repair turn that
        reports it cannot repair, arrive here too — a spent budget is a block, not a
        failure, so it parks for someone who can decide it rather than ending the run.

        There is no fix-demand arm here even when the turn carried findings. The evidence
        test in `CoderResult.actionable` decides *who* a block is routed to, and an
        implement turn's owner is itself: routing its own findings back to the same prompt
        is precisely the lap it just declared futile.
        """
        if self.operator_mode in {"human", "operator"} or impl_blocks >= self.MAX_PLAN_BLOCKS:
            gate = self._escalation(
                notes,
                impl_blocks,
                block_kind="implementation",
                where=where,
                findings=result.actionable,
            )
            return Await(
                self._context,
                gate.body,
                self.read_operator_impl,
                index=index,
                impl_blocks=impl_blocks,
                session_turns=session_turns,
            )
        return Continue(
            result,
            self.resolve_impl,
            notes=notes,
            index=index,
            where=where,
            impl_blocks=impl_blocks,
            session_turns=session_turns,
        )

    def resolve_impl(
        self,
        notes: str,
        index: int,
        where: str,
        impl_blocks: int = 0,
        session_turns: int = 1,
    ) -> Continue | Await:
        """Resolve an implementation block from the record, or park for the operator.

        The same shape as `resolve_plan`, and the same two arms for the same reason: a
        grounded answer re-enters the layer through `read_operator_impl`, an ungrounded
        one parks. `impl_blocks` is spent either way.
        """
        self.logger.info("resolving the implementation block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # smart, and unbounded: see `resolve_plan` — it is investigating a block with
            # full tool access, standing in for the person who would otherwise be woken.
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args=resolver_args(
                self, block_kind="implementation", notes=notes, docs_path=self.docs_path
            ),
        )
        if answered(self, result, "implementation"):
            return Continue(
                result,
                self.read_operator_impl,
                index=index,
                impl_blocks=impl_blocks + 1,
                session_turns=session_turns,
            )
        gate = self._escalation(
            notes, impl_blocks, result, block_kind="implementation", where=where
        )
        return Await(
            self._context,
            gate.body,
            self.read_operator_impl,
            index=index,
            impl_blocks=impl_blocks + 1,
            session_turns=session_turns,
        )

    def read_operator_impl(
        self, index: int, impl_blocks: int = 0, session_turns: int = 1
    ) -> Continue | Done:
        """Consume the answer and re-enter the layer with it in hand.

        A thin consume-the-answer state, which is what `Await` asks for: resume replays
        its target from the top, so everything but the answer is read by reference. The
        answer resumes at the escalating layer rather than the next one — the block was
        about *this* service, and `select_next_layer` is re-run by `implement` off the
        same cursor.

        `SCOPE: epic` leaves the flow exactly as it does from the plan gate: an answer can
        reveal the epic's premise was wrong, and that is the queue level's to fix.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the fix to the epic — handing back to replan")
            return self._ends(DevResult(status="replan", operator_notes=answer.content))
        return Continue(
            answer,
            self.implement,
            index=index,
            operator_context=answer.content,
            impl_blocks=impl_blocks,
            session_turns=session_turns,
        )

    # --- shared -------------------------------------------------------------

    def _refine(self, *, review_notes: str, operator_context: str, worklist: str) -> PlanResult:
        """The `refine-plan.md` turn, shared by the three states that re-plan.

        One helper rather than three copies of the same call: what distinguished the YAML's
        three refine nodes was their `review_notes` and where they went next, and both of
        those are the caller's. So is `worklist`, and for the same reason — the three loops
        lap on three unrelated things, so each resumes its own conversation and none of them
        inherits another's.
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
            session=self._chain(worklist),
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
