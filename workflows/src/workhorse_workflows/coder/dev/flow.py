"""Plan a story and implement it, one service layer at a time.

Reached from the main graph as a `type: flow` node, and standalone as
`workhorse-coder run dev`. Three loops share the same states rather than nesting::

    plan → (path gate)* → dispatch → (layer → implement → (gates → fix)* )*

The plan is authored, its service paths are checked against the workspace, and then every
service the plan dispatches is implemented by one agent turn and repaired against the
target repo's own gates until they pass.

**An operator gate applies decisions; it does not make them.** `resolve_plan` and
`resolve_impl` have two arms each: `answered`, when the resolver can quote the record,
rule or acceptance criterion that already settles the question, and everything else,
which `Await`s. The distinction is whose call it is, not how confident the resolver feels
— `shared/resolution.py` has the whole argument. `nodes.gate_plan` decides something
narrower: whether the resolver gets a turn at all (`plan_blocks` below
`MAX_PLAN_BLOCKS`), or the block goes straight to a human. Neither ever fails the run:
a plan blocked forever keeps coming back to that gate forever, across as many resumes as
it takes (AGENTS.md, "a workflow never gives up — it can only be blocked").

`read_operator` and `read_operator_impl` are the consume states *both* arms land on,
because a resolver that answers writes the same `context.md` a human would have, and
neither state can tell — nor needs to — which of them wrote it. An answer scoped `epic`
leaves the flow entirely, so the queue level replans the epic.

The budgets, the conversation keys and every turn with more than one call site are in
`nodes.py`; what is left here is the graph.
"""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.coder.dev import nodes
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.conversation import backbone
from workhorse_workflows.coder.shared.escalation import context_path
from workhorse_workflows.coder.shared.dev import (
    GATE_ORDER,
    branch_code_repos,
    changed_files,
    check_story_status,
    declared_markers,
    read_operator_context,
    record_plan,
    resolve_impl_context,
    run_gate,
    select_next_layer,
)
from workhorse_workflows.coder.shared.failure import from_findings, from_gate
from workhorse_workflows.coder.shared.resolution import answered
from workhorse_workflows.coder.shared.story import (
    guard_story_file,
    prepare_story,
    resolve_workspace_dirs,
    scrub_plan_mutations,
    snapshot_worktrees,
    stamp_specs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    DevResult,
    FailureReport,
    FixResult,
    GateOutcome,
    Lap,
    PlanResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels


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
    branch: str = ""

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories.

        Neither is decided on by any state below — every one of them reads the same paths
        and hands the same directory list to its agent turn — so both are `setup`. The
        workspace list is read back with `self.output` rather than returned, because
        `self.ctx` is one value and the paths are what nearly every state wants.

        `prepare_story` is also the authored-story gate: a story ostler knows and reports
        unauthored fails the run here rather than being planned against. `guard_story_file`
        is the other half of it — the slug resolved, but to a file that is not there.

        Nothing seeds the backbone chain: its key is derived from the story slug, and the
        chain file lives in the run directory, so this lane simply opens the conversation
        the later lanes will name.
        """
        self.call(resolve_workspace_dirs, self.docs_path)
        story = self.call(prepare_story, self.docs_path, self.story, self.epic)
        guard_story_file(story)
        return story

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    #: The three bounded budgets, each already a parameter of the state that guards it.
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("plan_rework", "fix_lap", "plan_blocks")

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on.

        A state that does not take a given counter reports nothing for it rather than
        zero — `implement` has no opinion about the repair-lap budget.
        """
        return self.labels() | counter_labels(params, "dev", self.BUDGET_LABELS)

    def start(self) -> Continue | Await:
        """Author the plan, stamp what it wrote, and route on whether it is blocked.

        Only a genuine `blocked` — a dangerous or undecidable prod operation the planner
        could not resolve — reaches the operator. Depth and correctness are enforced
        downstream by implementation review and by QA, not by a second plan-reviewing
        agent; one was tried and caught nothing actionable.
        """
        self.logger.info("planning %s", self.ctx.story_slug, extra={"activity": True})
        snapshot = self.call(snapshot_worktrees, self.docs_path)
        turn = roles.turn(self, "plan-story", returns=PlanResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            # high: authors the plan, including high-stakes prod operations (deploys,
            # security-group / egress changes) — worth the stronger reasoning.
            power="high",
            session=backbone(self),
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                # What this workspace says marks a service directory. The prompt used to
                # carry a list of four instead, which is a guess about the deployment.
                "markers": self.call(declared_markers).text,
            },
        )
        # Planning reads code; it does not write it. The prompt no longer says so — this
        # gate is what enforces it: anything the turn left in a code repo's working tree
        # is reverted (docs repo exempt, its artifacts land there; pre-snapshot dirt kept).
        self.call(scrub_plan_mutations, snapshot.status)
        # The plan agent writes plan.md / plan-<svc>.md as free-form markdown, so the
        # frontmatter that makes them OKF Concepts is only as reliable as the model's
        # memory. Stamp it mechanically instead of trusting the prompt.
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "blocked":
            return nodes.gate_plan(self, result, result.summary, 0)
        return Continue(
            result,
            self.validate_paths,
            notes=result.summary,
            plan=nodes.plan_arg(result),
        )

    def resolve_plan(self, notes: str, plan_blocks: int = 0) -> Continue | Await:
        """Resolve a plan block from what is already written down, or park for the operator.

        `plan_blocks` is spent on both arms. An answered block still counts, because the
        budget's job is to stop this lane lapping on a question it keeps failing to
        settle, and a resolver answering the same block three times is exactly that lap —
        the third lands on `gate_plan`'s human arm, which is the point.
        """
        result = nodes.resolver_turn(self, "plan", notes)
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
        gate = nodes.escalate(self, notes, plan_blocks, result)
        return Await(
            context_path(self),
            gate.body,
            self.read_operator,
            notes=notes,
            plan_blocks=plan_blocks + 1,
        )

    def read_operator(self, notes: str, plan_blocks: int = 0) -> Continue | Done:
        """Consume the answer and route on the scope the answerer chose.

        The answer may reveal the whole epic premise was wrong — a target environment that
        does not exist — rather than just this story's plan, and `SCOPE: epic` in
        `context.md` is how that is said. Anything else, blank included, reworks this plan.

        `plan_rework` is not threaded past here, so an answered block restores the full
        path-validation budget. `plan_blocks` *is* carried, and that asymmetry is the
        point: an operator answer is a fresh licence to re-validate, not a fresh licence
        to escalate. Reset both and the path gate laps forever.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the fix to the epic — handing back to replan")
            return nodes.ends(self, DevResult(status="replan", operator_notes=answer.content))
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
        result = nodes.refine(
            self,
            "replan-with-answer",
            review_notes=notes,
            operator_context=operator_context,
            worklist="block-repair",
        )
        if result.status == "blocked":
            return nodes.gate_plan(self, result, result.summary, plan_blocks)
        # The block is resolved: the conversation that was re-planning around it describes
        # a plan this state has just replaced, and the next block is a different one.
        self.reset_session(nodes.repair_chain(self, "block-repair"))
        return Continue(
            result,
            self.validate_paths,
            notes=result.summary,
            plan=nodes.plan_arg(result),
            plan_blocks=plan_blocks,
        )

    def validate_paths(
        self,
        notes: str,
        plan: dict | None = None,
        plan_rework: int = 0,
        plan_blocks: int = 0,
    ) -> Continue | Await:
        """Write the plan projection, and answer whether its service paths are real.

        The rework turn is inlined because the two were never independently reachable:
        every `invalid` verdict routed to it and it routed nothing back but here. One
        state re-planning against its own errors is the loop the counter was always
        describing, and `plan` is the refined structure going back into the same gate
        rather than a file the next state re-reads.

        A validator that cannot speak is not evidence of a bad plan, so a blank status
        takes the `valid` arm. What survives to an `invalid` verdict is unfixable by a
        blind refine pass — a missing marker, a nonexistent path, an unresolvable repo —
        which is why the exhausted budget escalates to the operator rather than proceeding.
        """
        result = self.call(record_plan, plan, self.ctx.spec_dir)
        if result.status != "invalid":
            self.reset_session(nodes.repair_chain(self, "path-repair"))
            return Continue(result, self.dispatch)
        if plan_rework >= nodes.MAX_VALIDATE_REWORKS:
            return nodes.gate_plan(self, result, notes, plan_blocks)
        refined = nodes.refine(
            self,
            "repair-plan-paths",
            review_notes=f"Service path validation failed: {result.errors}",
            worklist="path-repair",
            # low: the design already passed the gate; what failed is a path, a repo name or
            # a marker in the machine-readable reply. Billing that as a high-power re-plan is
            # what made one of these laps cost 203 s (`shared/dev.py:106`).
            power="low",
        )
        return Continue(
            refined,
            self.validate_paths,
            notes=refined.summary or notes,
            plan=nodes.plan_arg(refined),
            plan_rework=plan_rework + 1,
            plan_blocks=plan_blocks,
        )

    def dispatch(self) -> Continue:
        """Decode the approved plan against the workspace, and branch every code repo.

        Both steps are deterministic, neither is branched on, and the second only makes
        sense once the first has established which repos the plan touches — so they are
        one state. `branch_code_repos` runs here rather than at the top of the flow because
        `plan-context.json` did not exist until the plan did: the docs repo was branched
        much earlier, when it was the only thing the run knew about.
        """
        plan = self.output(record_plan).document
        impl = self.call(
            resolve_impl_context,
            self.ctx.spec_dir,
            self.target_env,
            self.docs_path,
            plan=plan,
        )
        self.logger.info("implementing %d service layer(s)", impl.dispatch_count)
        self.call(
            branch_code_repos,
            self.ctx.spec_dir,
            self.branch or self.story,
            self.docs_path,
            plan=plan,
        )
        return Continue(impl, self.layer)

    def layer(self, index: int = -1, lap: Lap = Lap()) -> Continue | Done:
        """Take the next service to implement, or finish.

        `index` is the loop cursor; an exhausted dispatch list is the loop's success exit,
        and the only other way out of this flow is the operator's epic-scoped replan.
        """
        pick = self.call(
            select_next_layer,
            self.ctx.spec_dir,
            index,
            plan=self.output(record_plan).document,
        )
        if not pick.has_layer:
            self.logger.info("every service layer implemented")
            return nodes.ends(self, DevResult(), lap.session_turns)
        self.logger.info(
            "implementing %s (%d/%d)", pick.layer.label, pick.index + 1, pick.dispatch_count
        )
        return Continue(pick, self.implement, index=pick.index, lap=lap)

    def implement(
        self,
        index: int,
        operator_context: str = "",
        impl_blocks: int = 0,
        lap: Lap = Lap(),
    ) -> Continue | Await:
        """Implement one service layer with the single `implement-plan.md` turn.

        `operator_context` is an answer to a block this layer already raised, and it is
        threaded rather than read off `read_operator_context`'s output because the layer
        loop re-enters this state for *every* layer: an answer about one service must not
        silently brief the next one's turn.

        Each layer's first implementation turn opens a *fresh* backbone rather than
        inheriting the conversation before it: the implementer is called once per plan on
        a fresh context, with the plan and its standards inlined into the prompt, while
        the planning (or previous layer's) history it would inherit is long enough to trip
        the assistant's auto-compaction before any code is written. Repair turns and an
        operator-answer re-entry still join that layer's implementation conversation —
        only the entry boundary is cut.
        """
        if not impl_blocks and not operator_context:
            self.reset_session(backbone(self))
            lap = lap.model_copy(update={"session_turns": 0})
        lap = nodes.spend(self, lap)
        result = nodes.implement_layer(self, operator_context)
        if result.blocked:
            return nodes.gate_impl(
                self, result, result.notes, index, "the implementation turn", impl_blocks, lap
            )
        # A fresh implementation turn earns a fresh repair budget: the laps bound one
        # implement → gates → fix cycle, and an operator answer starts another one.
        return Continue(
            result, self.gates, index=index, lap=lap.model_copy(update={"fix_lap": 0, "digest": ""})
        )

    def gates(
        self, index: int, impl_blocks: int = 0, lap: Lap = Lap()
    ) -> Continue | Await:
        """Run this service's deterministic gates, and route on the first one that says no.

        Which gates exist is the repo's answer, not this package's: `agents.yml` names the
        command for each of `GATE_ORDER` under the service it belongs to, and
        `shared.failure` is the seam every one of them arrives through, because what `fix`
        reads is a `FailureReport` and not a tool's log. A gate that cannot speak —
        `skipped`, or a blank status — is not a failure: the service adopts a gate by
        declaring it, and a service that has not is not thereby broken. Nothing here
        guesses a command, so a stack stablemate has never seen gets gates the moment its
        repo writes them down.

        The story's Status line is gated here too, and first, because it is the one shape a
        turn can break that no command in `agents.yml` reads: story selection parses it, so
        a turn that stamps the story finished takes it out of the queue before QA has seen
        it. It runs on every lap, so the repair turn is held to the rule as well.
        """
        layer = nodes.current_layer(self)
        stamped = self.call(
            check_story_status,
            self.docs_path,
            self.ctx.story_slug,
            epic=self.ctx.story_epic,
            story_path=self.ctx.story_path,
        )
        if stamped.status == "dirty":
            return nodes.repair_or_escalate(
                self,
                from_findings(
                    "story status",
                    [
                        Finding(
                            target=self.ctx.story_path,
                            issue=(
                                f"the story's Status reads '{stamped.written}', which marks "
                                "it finished — story selection reads that line, so the story "
                                "is now invisible to every later loop and to QA"
                            ),
                            repair=(
                                "put the Status line back to the value it held before this "
                                "story's work — `git diff` on the story file shows it — and "
                                "record what was run as prose under `## Implementation "
                                "Status` instead. The workflow stamps the outcome itself, "
                                "and only from a QA run it performed"
                            ),
                        )
                    ],
                    layer.cwd,
                    lap.fix_lap,
                ),
                f"the story's Status was set to '{stamped.written}' before QA ran.",
                "the story status gate",
                index,
                impl_blocks,
                lap,
            )
        outcome = GateOutcome()
        for gate in GATE_ORDER:
            outcome = self.call(
                run_gate, layer.cwd, layer.service, gate, service_type=layer.type
            )
            if outcome.status == "dirty":
                break
        if outcome.status != "dirty":
            return Continue(outcome, self.layer, index=index, lap=lap)
        report = from_gate(outcome, layer.cwd, lap.fix_lap)
        failing = f"`{report.command}`" if report.command else f"the {outcome.gate} gate"
        return nodes.repair_or_escalate(
            self,
            report,
            f"{layer.service}: {failing} still fails after "
            f"{lap.fix_lap} repair lap(s).\n\n{report.output}",
            f"the {outcome.gate} gate",
            index,
            impl_blocks,
            lap,
        )

    def fix(
        self,
        index: int,
        lap: Lap,
        report: FailureReport = FailureReport(),
        impl_blocks: int = 0,
    ) -> Continue | Await:
        """Repair whatever the gate reported, then re-run the gates.

        One repair role for every gate, on the story's own conversation: the turn that
        wrote this code is the cheapest turn to fix it, and a fixer in a fresh context
        spends its first minutes re-reading a diff it has only just met.

        The report is threaded in rather than read back off a node's output, because not
        every gate in this lane is a node with one: the status check builds its findings in
        Python, and `gates` is the single place that decides which failure this lap is for.
        `lap.digest` is the *previous* lap's fingerprint: two laps whose reports digest the
        same mean the repair changed nothing the gate can see, and the answer to that is to
        spend power rather than another identical turn. The ladder is low, low, then high —
        a linter or a failing assertion is mechanical work grounded in exact evidence — and
        a stalled lap brings that escalation forward.
        """
        layer = nodes.current_layer(self)
        stalled = bool(lap.digest) and report.digest == lap.digest
        lap = nodes.spend(self, lap)
        turn = roles.turn(self, "dev-fix", returns=FixResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high" if stalled or lap.fix_lap >= 2 else "low",
            cwd=layer.cwd,
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                # Dumped rather than passed as a model: everything in `args` is
                # checkpointed, and a checkpoint holds JSON.
                "report": report.model_dump(),
                "changed_files": self.call(
                    changed_files, layer.cwd, self.ctx.story_slug, self.ctx.story_id
                ).paths,
                "service": layer.service,
                # The prompt commits its own fix now, and these two are the trailers that
                # tie that commit back to the story it belongs to.
                "epic": self.epic,
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
            },
            session=backbone(self),
        )
        if result.blocked:
            return nodes.gate_impl(
                self,
                result,
                result.notes
                or "the repair turn could not satisfy "
                + (f"`{report.command}`" if report.command else f"the {report.source} gate"),
                index,
                "the repair turn",
                impl_blocks,
                lap,
            )
        return Continue(
            result,
            self.gates,
            index=index,
            impl_blocks=impl_blocks,
            lap=lap.model_copy(
                update={"fix_lap": lap.fix_lap + 1, "digest": report.digest}
            ),
        )

    def resolve_impl(
        self, notes: str, index: int, where: str, impl_blocks: int = 0, lap: Lap = Lap()
    ) -> Continue | Await:
        """Resolve an implementation block from the record, or park for the operator.

        The same shape as `resolve_plan`, and the same two arms for the same reason: a
        grounded answer re-enters the layer through `read_operator_impl`, an ungrounded
        one parks. `impl_blocks` is spent either way.
        """
        result = nodes.resolver_turn(self, "implementation", notes)
        if answered(self, result, "implementation"):
            return Continue(
                result,
                self.read_operator_impl,
                index=index,
                impl_blocks=impl_blocks + 1,
                lap=lap,
            )
        gate = nodes.escalate(
            self, notes, impl_blocks, result, block_kind="implementation", where=where
        )
        return Await(
            context_path(self),
            gate.body,
            self.read_operator_impl,
            index=index,
            impl_blocks=impl_blocks + 1,
            lap=lap,
        )

    def read_operator_impl(
        self, index: int, impl_blocks: int = 0, lap: Lap = Lap()
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
            return nodes.ends(self, DevResult(status="replan", operator_notes=answer.content))
        return Continue(
            answer,
            self.implement,
            index=index,
            operator_context=answer.content,
            impl_blocks=impl_blocks,
            lap=lap,
        )


__all__ = ["Dev"]
