"""The `research` gate loop as a state machine — the Python port of
`base-library/workflows/research/workflow.yaml`.

Same science, same prompts, same model tiers. What changes is that the loop is written
in Python rather than assembled out of branch nodes, and the difference shows up almost
entirely in the **counters**. The YAML needs six scripts and nine nodes to hold three
integers:

    init_lead_counter  init_extend_counter  reset_rework     (three "set it to 0" nodes)
    guard_rework       guard_lead_review    guard_extend     (three ">= literal" branches)
    incr_rework        incr_lead_review     incr_extend      (three "+1" script nodes)

and the caps themselves cannot be written in the branches, because a branch condition
is a literal — so `vars.max_reworks: "3"` is kept in sync with `guard_rework`'s `"3"`
**by a comment asking the next editor to remember**. Here the caps are module constants
the guards read directly, a reset is a default argument, an increment is `+ 1`, and a
guard is `if`. The three counters travel as ordinary state parameters, which is also
what puts them in the checkpoint where an operator can read (and edit) them::

    {"state": "check_gate", "params": {"gate_id": "G3", "reworks": 2, ...}}

Branch nodes disappear for the same reason: `route_gate`, `check_killed_pre`,
`decide_gate`, `route_lead_verdict` and `route_goal_verdict` are `if`/`elif` inside the
state that produced the value they branch on. 30 YAML nodes become 12 states.

The four terminals stay distinguishable, because the difference is real: a goal verdict
(`reached` / `impossible`) is a scientific conclusion and ends the run clean —
`Done(...)`; a budget exhausted without a verdict is an apparatus failure and ends it
red — `raise WorkflowFailed(...)`, which is the `program_dead` node.
"""
from __future__ import annotations

from typing import NoReturn

from workhorse.pyflow import Continue, Done, Registry, Workflow, WorkflowFailed
from workhorse_workflows.research.nodes import (
    blueprint,
    clone_repo,
    load_program,
    publish_results,
)
from workhorse_workflows.research.schemas import (
    ExtendResult,
    FailedCriterion,
    GateCheck,
    GateSelection,
    GoalReview,
    ImplResult,
    LeadReview,
    NewDirectionResult,
    Program,
    RecordResult,
    ReviveResult,
)

#: The engine-level caps, `vars.max_*` in the YAML. There they were duplicated as
#: literals inside the guard branches with a comment asking the next editor to keep the
#: two copies in sync; here the guards read these names, so there is one copy.
MAX_REWORKS = 3
MAX_LEAD_REVIEWS = 4
#: Bounds program self-extension. The lead's `reached`/`impossible` verdict is the
#: intended stop and this is only the runaway backstop, so it stays generous.
MAX_EXTENSIONS = 6

#: Wall-clock for the three nodes that run the program's measurement — a multi-map,
#: multi-seed benchmark the engine's default could not fit. Surfaced to the prompt as
#: `node_timeout_min`, so the agent sizes its runs to finish: a turn killed at the
#: budget restarts the node from scratch. (The YAML's comment says "20 min" next to the
#: same `timeout: 5400`; the number is what runs, and it is 90.)
MEASUREMENT_TIMEOUT = 5400.0

#: Forced outcomes the bookkeeping prompt writes when the loop stops itself.
FAIL_MAX_REWORKS = "FAIL_MAX_REWORKS"
HALTED_LEAD_REVIEW_BUDGET = "HALTED_LEAD_REVIEW_BUDGET"
HALTED_EXTENSION_BUDGET = "HALTED_EXTENSION_BUDGET"
GOAL_REACHED = "GOAL_REACHED"
GOAL_IMPOSSIBLE = "GOAL_IMPOSSIBLE"

#: The gate id the goal terminals record under — the verdict is about the program, not
#: about any one gate.
GOAL = "GOAL"


class Research(Workflow):
    """One gate-loop engine, driving any research program.

    Pick the next gate from the program's README ladder, implement the experiment,
    gate-check it against the gate doc's exact criteria, rework on failure (bounded),
    record the outcome, and — on a kill — hand off to a research lead that either
    revives the gate or defines a new direction. When the ladder is exhausted the loop
    does **not** terminate: a lead judges the program against its own North star and
    either declares it reached, declares it impossible, or extends it with a new gate.
    """

    #: Which program to run, as a repo-relative dir. Empty → `load_program` selects it
    #: (`$RESEARCH_PROGRAM`, the launch dir, `agents.yml`, the pointer file).
    program: str = ""

    def setup(self) -> Program:
        """Get a checkout, then read the program manifest out of it.

        Both halves are run-scoped residue: every state below needs `repo_dir` and the
        program's paths, and none of them decides those values. This is `setup` +
        `load_config` in the YAML.
        """
        repo = self.call(clone_repo)
        return self.call(load_program, self.program, repo.repo_dir)

    def labels(self) -> dict[str, str]:
        """What the run is working on — telemetry the engine cannot know."""
        return {"program": self.ctx.program_dir}

    # --- the gate loop ------------------------------------------------------

    def start(self, lead_reviews: int = 0, extensions: int = 0) -> Continue:
        """Pick the next gate, and route on what came back.

        `select_gate` + `route_gate` + `check_killed_pre`. An empty `gate_id` is read
        as "no gate" alongside the literal `"none"`: the resilience ladder defaults a
        missing key to `""`, and sending an unnamed gate to `implement` would be the
        one unsafe reading.
        """
        selection = self.agent(
            "prompts/select-next-gate.md",
            returns=GateSelection,
            # haiku: reads the README ladder + progress and picks the next gate id —
            # bounded selection over existing docs, no deep reasoning needed.
            power="low",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
            },
        )
        if selection.gate_id in ("", "none"):
            # Ladder exhausted: don't terminate — let the lead judge the North star.
            return Continue(
                selection,
                self.goal_review,
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        if selection.program_killed:
            # A pre-existing kill: let the research lead judge it, don't just die.
            return Continue(
                selection,
                self.lead_review,
                gate_id=selection.gate_id,
                gate_doc_path=selection.gate_doc_path,
                failed_criteria=[],
                notes=selection.rationale,
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        return Continue(
            selection,
            self.implement,
            gate_id=selection.gate_id,
            gate_doc_path=selection.gate_doc_path,
            lead_reviews=lead_reviews,
            extensions=extensions,
        )

    def implement(
        self,
        gate_id: str,
        gate_doc_path: str,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Run the experiment the gate doc specifies.

        `reset_rework` — a whole node whose job was writing `0` into a counter — is the
        `reworks=0` default on `check_gate`.
        """
        result = self.agent(
            "prompts/implement-experiment.md",
            returns=ImplResult,
            timeout=MEASUREMENT_TIMEOUT,
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "code_root": self.ctx.code_root,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
            },
        )
        return Continue(
            result,
            self.check_gate,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            lead_reviews=lead_reviews,
            extensions=extensions,
        )

    def check_gate(
        self,
        gate_id: str,
        gate_doc_path: str,
        reworks: int = 0,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Judge the experiment against the gate's criteria, independently.

        `gate_check` + `decide_gate` + `guard_rework`. A status the ladder could not
        get an answer for is `""`, which falls through to the rework arm — the
        conservative one.
        """
        check = self.agent(
            "prompts/gate-check.md",
            returns=GateCheck,
            # The reviewer re-runs the measurement over the FULL seed set — the most
            # expensive turn in the loop — so it gets the full implement budget.
            timeout=MEASUREMENT_TIMEOUT,
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
            },
        )
        if check.status == "approved":
            return Continue(
                check,
                self.record_pass,
                gate_id=gate_id,
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        failed = [criterion.model_dump(mode="json") for criterion in check.failed_criteria]
        if check.status == "killed":
            return Continue(
                check,
                self.record_kill,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed,
                notes=check.notes,
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        if reworks >= MAX_REWORKS:
            return Continue(check, self.halt, outcome=FAIL_MAX_REWORKS, gate_id=gate_id)
        return Continue(
            check,
            self.rework,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed,
            notes=check.notes,
            reworks=reworks,
            lead_reviews=lead_reviews,
            extensions=extensions,
        )

    def rework(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        reworks: int = 0,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Fix what the gate check faulted, then re-check.

        `do_rework` + `incr_rework`. The increment is the `reworks=reworks + 1` below;
        the counter is a parameter, so the attempt number is in the checkpoint rather
        than in a node's `output.json`.
        """
        result = self.agent(
            "prompts/rework-experiment.md",
            returns=ImplResult,
            timeout=MEASUREMENT_TIMEOUT,
            args={
                "repo_dir": self.ctx.repo_dir,
                "code_root": self.ctx.code_root,
                "gate_id": gate_id,
                "failed_criteria": failed_criteria,
                "notes": notes,
                "rework_count": reworks,
            },
        )
        return Continue(
            result,
            self.check_gate,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            reworks=reworks + 1,
            lead_reviews=lead_reviews,
            extensions=extensions,
        )

    # --- recording ----------------------------------------------------------

    def record_pass(
        self, gate_id: str, lead_reviews: int = 0, extensions: int = 0
    ) -> Continue:
        """Write the approved gate's outcome, publish, and take the next gate."""
        result = self.agent(
            "prompts/record-result.md",
            returns=RecordResult,
            # haiku: writes the gate outcome to the progress file — bookkeeping.
            power="low",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "gate_id": gate_id,
            },
        )
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )
        return Continue(
            result, self.start, lead_reviews=lead_reviews, extensions=extensions
        )

    def record_kill(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Write the kill, then hand off to the research lead rather than terminating."""
        self.agent(
            "prompts/record-result.md",
            returns=RecordResult,
            power="low",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "gate_id": gate_id,
            },
        )
        return Continue(
            None,
            self.lead_review,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=[
                criterion.model_dump(mode="json") for criterion in failed_criteria
            ],
            notes=notes,
            lead_reviews=lead_reviews,
            extensions=extensions,
        )

    # --- the research lead --------------------------------------------------

    def lead_review(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Judge whether the kill was scientifically sound, and route on the verdict.

        `lead_review` + `guard_lead_review` + `route_lead_verdict`. The budget check
        runs *after* the review, exactly as the YAML ordered it: the operator gets the
        lead's reasoning on the record even on the turn that exhausts the budget.
        """
        review = self.agent(
            "prompts/research-lead-review.md",
            returns=LeadReview,
            # opus: the program's direction turns on this call, so it is worth the
            # stronger reasoning (mirrors epic-coder's opus review_plan gate).
            power="high",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "goal": self.ctx.goal,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
                "failed_criteria": failed_criteria,
                "notes": notes,
            },
        )
        if lead_reviews >= MAX_LEAD_REVIEWS:
            return Continue(
                review, self.halt, outcome=HALTED_LEAD_REVIEW_BUDGET, gate_id=gate_id
            )
        if review.verdict == "revive":
            return Continue(
                review,
                self.revive,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                review=review.model_dump(mode="json"),
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        if review.verdict == "new_direction":
            return Continue(
                review,
                self.new_direction,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                review=review.model_dump(mode="json"),
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        return Continue(
            review, self.halt, outcome=HALTED_LEAD_REVIEW_BUDGET, gate_id=gate_id
        )

    def revive(
        self,
        gate_id: str,
        gate_doc_path: str,
        review: LeadReview,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Re-scope a gate that was killed for the wrong reason, then loop."""
        result = self.agent(
            "prompts/revive-gate.md",
            returns=ReviveResult,
            # opus: acts on the lead's verdict — a course-correcting decision, kept on
            # the same tier as the review that drove it.
            power="high",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
                "lead_review": review,
            },
        )
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )
        return Continue(
            result, self.start, lead_reviews=lead_reviews + 1, extensions=extensions
        )

    def new_direction(
        self,
        gate_id: str,
        gate_doc_path: str,
        review: LeadReview,
        lead_reviews: int = 0,
        extensions: int = 0,
    ) -> Continue:
        """Define the direction that replaces a justifiably killed one, then loop."""
        result = self.agent(
            "prompts/define-new-direction.md",
            returns=NewDirectionResult,
            # opus: the most open-ended, high-leverage call in the loop.
            power="high",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "goal": self.ctx.goal,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
                "lead_review": review,
            },
        )
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )
        return Continue(
            result, self.start, lead_reviews=lead_reviews + 1, extensions=extensions
        )

    # --- self-extension -----------------------------------------------------

    def goal_review(self, lead_reviews: int = 0, extensions: int = 0) -> Continue:
        """Every reachable gate passed — so judge the program against its North star.

        `lead_goal_review` + `guard_extend` + `route_goal_verdict`.
        """
        review = self.agent(
            "prompts/lead-goal-review.md",
            returns=GoalReview,
            # opus: decides whether the program is done, dead, or must grow.
            power="high",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "code_root": self.ctx.code_root,
                "goal": self.ctx.goal,
            },
        )
        if extensions >= MAX_EXTENSIONS:
            return Continue(review, self.halt, outcome=HALTED_EXTENSION_BUDGET)
        if review.verdict == "reached":
            return Continue(review, self.record_goal, outcome=GOAL_REACHED)
        if review.verdict == "impossible":
            return Continue(review, self.record_goal, outcome=GOAL_IMPOSSIBLE)
        if review.verdict == "extend":
            return Continue(
                review,
                self.extend,
                review=review.model_dump(mode="json"),
                lead_reviews=lead_reviews,
                extensions=extensions,
            )
        return Continue(review, self.halt, outcome=HALTED_EXTENSION_BUDGET)

    def extend(
        self, review: GoalReview, lead_reviews: int = 0, extensions: int = 0
    ) -> Continue:
        """Append the next gate to the ladder, then loop — it is now the lowest
        non-PASS gate, so `start` picks it up."""
        result = self.agent(
            "prompts/extend-program.md",
            returns=ExtendResult,
            # opus: writes the next gate (ladder + gate doc + progress) — new science.
            power="high",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "code_root": self.ctx.code_root,
                "goal": self.ctx.goal,
                "goal_review": review,
            },
        )
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )
        return Continue(
            result, self.start, lead_reviews=lead_reviews, extensions=extensions + 1
        )

    # --- terminals ----------------------------------------------------------

    def record_goal(self, outcome: str) -> Done:
        """Record a goal verdict, publish, and end clean.

        `record_reached` / `record_impossible`. `impossible` is a valid scientific
        conclusion — a recorded negative — not an apparatus failure, so it terminates
        the same way `reached` does.
        """
        result = self.agent(
            "prompts/record-result.md",
            returns=RecordResult,
            power="low",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "gate_id": GOAL,
                "gate_doc_path": f"{self.ctx.program_dir}/README.md",
                "forced_outcome": outcome,
            },
        )
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )
        return Done(result)

    def halt(self, outcome: str, gate_id: str = GOAL) -> NoReturn:
        """Record a forced outcome, publish, and end red.

        `escalate`, `lead_halt` and `goal_halt` — three nodes that differ only in the
        string they force. All three reached `publish_dead` → `program_dead`, the
        `fail` terminal, which is what `WorkflowFailed` is here: the loop stopped
        itself without a scientific verdict, and that is an apparatus problem an
        operator has to see.
        """
        self.agent(
            "prompts/record-result.md",
            returns=RecordResult,
            power="low",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "progress_path": self.ctx.progress_path,
                "gate_id": gate_id,
                "gate_doc_path": f"{self.ctx.program_dir}/README.md",
                "forced_outcome": outcome,
            },
        )
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )
        raise WorkflowFailed(f"{outcome} on gate {gate_id or GOAL}")


workflow = Registry("research").add_blueprints(blueprint)
main = workflow.main(Research)
