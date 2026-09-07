"""The `research` gate loop as a state machine.

The loop's shape is set by one fact: **the measurement does not happen inside an agent
turn.** A turn's budget is a budget for thinking, and an experiment that runs past it is
killed with no memory of the attempt — so the longer the experiment, the less likely
anyone ever sees its result. Here a gate is designed, made runnable, *submitted* to
`workhorse.job`, and then waited on across an `Await` that a driver may die and resume
through. What comes back is two artifacts, and a deterministic state classifies them
with zero model calls.

Three personas own the three kinds of problem a gate has, because they are three
different problems and one prompt answered all of them badly:

* the **scientist** (`max`) owns the protocol, the declared resources and the
  calibration probe — and the scientific rework, where the protocol may change but the
  hypothesis and the frozen target may not;
* the **engineer** (`high`) owns runnability: the command, the `n=1` rehearsal through
  the real runner, crash repair, and mid-flight triage of a job running long;
* the **lead** (`ultra`) owns verdicts — the gate's artifact against its
  thresholds, whether a kill was sound, and where the program goes next.

And one rule holds over every arm: **no arm ends in `WorkflowFailed`.** Every budget
here caps the *resolver*, never the block — a cap that is hit escalates to an operator
`Await`, checkpointed and resumable, because the failure this rewrite exists to prevent
is a run that ended red with `waiting_on: null` and sat dead for ten hours before a
human noticed.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, ClassVar

from workhorse.cli import console_script
from workhorse.pyflow import Await, Continue, Done, Registry, Workflow
from workhorse_workflows.research.nodes import (
    append_history,
    blueprint,
    build_dossier,
    check_envelope,
    clone_repo,
    collect_job,
    dry_run,
    job_dir_for,
    kill_job,
    load_program,
    publish_results,
    record_spend,
    submit_job,
    watch_job,
)
from workhorse_workflows.research.nodes.dossier import (
    parse_frozen_target,
    render_dossier,
    resolvability,
    summarize,
)
from workhorse_workflows.research.schemas import (
    Budget,
    Build,
    Collected,
    Design,
    Dossier,
    ExtendResult,
    FailedCriterion,
    FrozenTarget,
    GateCheck,
    GateSelection,
    GoalReview,
    LeadReview,
    NewDirectionResult,
    NewTarget,
    Program,
    ProgramReview,
    RecharterResult,
    RecordResult,
    ReviveResult,
    TriageResult,
)

# ── the caps ────────────────────────────────────────────────────────────────
#
# Every one of these bounds a *resolver* — how many times the loop may try to fix
# something itself before it walks toward a person. None of them bounds the block.

#: Engineering repairs on one gate: the experiment produced no measurement. Exhausted,
#: it is no longer an engineering problem, so the lead judges the gate rather than the
#: engineer taking a fourth swing at it.
MAX_BUILD_FIXES = 3
#: Scientific reworks on one gate: the experiment measured something and missed. Two,
#: not three — a rework here may change the protocol, so the third lap is nearly always
#: a different experiment wearing the same gate's name, and that is the lead's call.
MAX_REWORKS = 2
#: Rescopes after a design asked for more than the machine has. Over-resource is not a
#: science failure and not an operator's problem; it is a protocol to shrink, twice.
MAX_RESCOPES = 2
#: Program-scoped, like `MAX_EXTENSIONS` — the guard adds `Budget`'s count to what the
#: ledger says prior runs already spent.
MAX_LEAD_REVIEWS = 4
#: Bounds program self-extension. The lead's `reached`/`banked`/`impossible` verdict is
#: the intended stop and this is only the runaway backstop, so it stays generous.
#:
#: It is only a backstop if it binds the **program**, though, and `Budget` counts one
#: run. A relaunch — a shell loop, a resumed container, an operator running the same
#: command tomorrow — used to start every counter over, so this cap could be spent an
#: unbounded number of times and a program could extend itself forever. The spend is
#: therefore persisted to the program's ledger (`nodes/program.py`) and read back into
#: `Program.extensions_spent`, and the guards below compare against the sum.
MAX_EXTENSIONS = 6
#: Program-level reviews — the lead judging the *dossier* rather than one gate. Fires
#: on every kill, every exhausted repair budget, before every revive, and periodically;
#: program-scoped through the ledger like the two above. Generous because a review is
#: how the loop stops circling, and a cap that bit early would put the circling back.
MAX_PROGRAM_REVIEWS = 8
#: Re-charters — the lead changing the frozen target (metric, eval, threshold). Twice:
#: a program whose target has been rewritten twice and is still not resolvable is a
#: program whose eval a person has to choose.
MAX_RECHARTERS = 2
#: Retries when a written target fails the in-code resolvability check. One: the lead
#: is told exactly which number was short, and a second miss means it cannot be fixed
#: with the eval the program has.
MAX_RECHARTER_FIXES = 1
#: Gates concluded (pass or kill) between periodic program reviews from `start`.
PROGRAM_REVIEW_EVERY = 3

#: The gate doc a re-charter's probe gate is written from — the scaffold's own.
GATE_TEMPLATE = Path(__file__).resolve().parent / "scaffold" / "templates" / "gate.md"

#: Where an operator finds what the loop is blocked on, repo-relative to the program.
#: One file, re-armed and appended to on every block, so a program's whole history of
#: interventions is one document rather than a directory nobody lists.
BLOCKED_NAME = "BLOCKED.md"

#: The prefix every fix reason carries when an operator, and not a classifier, is what
#: released the state. It is what tells a resumed state to go and read the gate.
OPERATOR_RELEASED = "an operator addressed"

#: Forced outcomes the bookkeeping prompt writes when the program concludes.
GOAL_REACHED = "GOAL_REACHED"
GOAL_IMPOSSIBLE = "GOAL_IMPOSSIBLE"
#: A shippable partial result, recorded as one. See `goal_review`.
GOAL_BANKED = "GOAL_BANKED"

#: What each clean goal terminal writes into the ledger's `status`. Any of the three
#: stops the *next* run at `load_program` until somebody reauthorizes it, which is what
#: makes ending clean mean something rather than being where the shell loop restarts.
GOAL_STATUS = {
    GOAL_REACHED: "reached",
    GOAL_IMPOSSIBLE: "impossible",
    GOAL_BANKED: "banked",
}

#: The gate id the goal terminals record under — the verdict is about the program, not
#: about any one gate.
GOAL = "GOAL"


class Research(Workflow):
    """One gate-loop engine, driving any research program.

    Pick the next gate from the program's README ladder; design the experiment, build
    it, submit it to the detached runner and wait; classify what came back without a
    model call; let the lead judge the artifact against the gate doc's thresholds. On a
    kill, hand off to a research lead that either revives the gate or defines a new
    direction. When the ladder is exhausted the loop does **not** terminate: a lead
    judges the program against its own North star and either declares it reached, banks
    the strongest result, declares it impossible, or extends it with a new gate.
    """

    #: The new graph runs 8–14 transitions per gate where the old one ran about four,
    #: and a long program laps it many times. The engine's default of 1000 would end a
    #: healthy run in `transition-budget-exhausted` — a give-up wearing a budget's
    #: clothes. Declared on the class so `WORKHORSE_MAX_TRANSITIONS` is still the knob.
    max_transitions: ClassVar[int] = 3000

    #: Which program to run, as a repo-relative dir. Empty → `load_program` selects it
    #: (the launch dir, `agents.yml`, the pointer file).
    program: str = ""

    #: The remote to clone, when the run has to fetch its own checkout. Empty — the usual
    #: case — means work in place on `repo_dir`, which the CLI has already resolved.
    repo_url: str = ""

    #: The branch to clone. Only read when `repo_url` is set.
    repo_branch: str = "main"

    #: Where the operator stood, which is one of the program-selection signals. Empty
    #: means the driver's own working directory.
    launch_dir: str = ""

    #: Continue a program a prior run already concluded (banked, reached or declared
    #: impossible). Off by default, and deliberately not something the loop can set
    #: for itself: a banked result is only worth banking if somebody has to look at it
    #: before the program keeps running.
    reauthorize: bool = False

    def setup(self) -> Program:
        """Get a checkout, then read the program manifest out of it.

        Both halves are run-scoped residue: every state below needs `repo_dir` and the
        program's paths, and none of them decides those values.
        """
        repo = self.call(
            clone_repo,
            repo_dir=self.repo_dir,
            repo_url=self.repo_url,
            repo_branch=self.repo_branch,
        )
        return self.call(
            load_program,
            self.program,
            repo.repo_dir,
            self.launch_dir,
            reauthorize=self.reauthorize,
        )

    def labels(self) -> dict[str, str]:
        """What the run is working on — telemetry the engine cannot know."""
        return {"program": self.ctx.program_dir}

    # --- what the states say twice ------------------------------------------
    #
    # Private, so state discovery skips them (a leading underscore is not a state).

    def _program_args(self, **extra: Any) -> dict[str, Any]:
        """The program triple a prompt opens with, plus this call's own arguments."""
        return {
            "repo_dir": self.ctx.repo_dir,
            "program_dir": self.ctx.program_dir,
            "progress_path": self.ctx.progress_path,
            **extra,
        }

    def _abs(self, rel: str) -> Path:
        """A repo-relative path as the absolute one an operator gate needs."""
        return Path(self.ctx.repo_dir) / rel

    def _blocked(self, questions: str, resume: Any, /, **params: Any) -> Await:
        """Park on the operator gate, naming the state to re-enter with what.

        This is the only way this workflow stops short of a verdict, and it is not a
        stop: the checkpoint records `waiting_on`, the run is resumable, and the answer
        the operator writes *is* the authorization the resumed state needs. Every
        caller therefore hands over a concrete target and concrete parameters — a block
        that could not say what it would do next would be a give-up with a file.
        """
        return Await(
            self._abs(f"{self.ctx.program_dir}/{BLOCKED_NAME}"), questions, resume, **params
        )

    def _released_by(self, fix_reason: str) -> str:
        """`fix_reason`, plus the gate itself when an operator is what released the state.

        The gate is the answer channel as well as the question channel, and until this
        existed nothing ever read it back: a state re-entered after a block was handed
        its *own* notes as the reason it was released, so an engineer that blocked to be
        told something was told what it had already said. It then re-read the same
        evidence, reached the same conclusion, and blocked again — a loop no budget caps,
        because an operator block spends none of them. `_blocked` promises the operator's
        answer *is* the authorization the resumed state needs; this is the half of that
        promise that delivers it.

        Verbatim, whole file, oldest first. The answers are what the state must act on,
        and its own asks above them are how it sees that it is repeating itself.
        """
        if not fix_reason.startswith(OPERATOR_RELEASED):
            return fix_reason
        gate = self._abs(f"{self.ctx.program_dir}/{BLOCKED_NAME}")
        if not gate.is_file():
            return fix_reason
        return (
            f"{fix_reason}\n\n"
            f"The operator answered on `{self.ctx.program_dir}/{BLOCKED_NAME}`, below, "
            "oldest first: your own asks and the answers to them. Do what the answers "
            "say. Where one tells you a fault is not yours and needs no change here, it "
            "is settled — do not raise it again; carry on with the work it releases you "
            "to do. The `STATUS:` header is the engine's bookkeeping, not yours.\n\n"
            f"{gate.read_text(encoding='utf-8').strip()}"
        )

    def _publish(self) -> None:
        """Commit what the last turn wrote onto the result branch.

        Every arm that produces a durable artifact publishes it there and then rather
        than leaving it to a terminal: a run that is killed, capped or resumed hours
        later must not lose the gate it already finished. Soft by contract — the node
        reports a failed push rather than raising — so this is safe anywhere.
        """
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
        )

    def _spent(self, budget: Budget) -> tuple[int, int]:
        """`(extensions, lead_reviews)` this **program** has spent, not this run."""
        return (
            self.ctx.extensions_spent + budget.extensions,
            self.ctx.lead_reviews_spent + budget.lead_reviews,
        )

    def _program_spent(self, budget: Budget) -> tuple[int, int]:
        """`(program_reviews, recharters)` this **program** has spent, not this run."""
        return (
            self.ctx.program_reviews_spent + budget.program_reviews,
            self.ctx.recharters_spent + budget.recharters,
        )

    def _persist(self, budget: Budget, *, status: str = "active") -> None:
        """Write the program's spend to its ledger, before the publish that commits it."""
        extensions, lead_reviews = self._spent(budget)
        program_reviews, recharters = self._program_spent(budget)
        self.call(
            record_spend,
            repo_dir=self.ctx.repo_dir,
            program_dir=self.ctx.program_dir,
            extensions=extensions,
            lead_reviews=lead_reviews,
            status=status,
            program_reviews=program_reviews,
            recharters=recharters,
        )

    def _dossier(self, budget: Budget) -> Dossier:
        """The program's computed evidence — numbers, dates, counts — with no model in it.

        This is what the loop never had. Every verdict below used to be made by a
        persona reading one gate's doc, by path; the dossier is what a lead who read the
        whole record would have in front of them, and it is deterministic so the tests
        can say exactly what the lead saw.
        """
        _, lead_reviews = self._spent(budget)
        program_reviews, _ = self._program_spent(budget)
        return self.call(
            build_dossier,
            repo_dir=self.ctx.repo_dir,
            program_dir=self.ctx.program_dir,
            progress_path=self.ctx.progress_path,
            code_root=self.ctx.code_root,
            lead_reviews=lead_reviews,
            program_reviews=program_reviews,
            gate_cycles=budget.gate_cycles,
            review_every=PROGRAM_REVIEW_EVERY,
        )

    def _history(
        self, event: str, gate_id: str = "", *, note: str = "", fingerprint: str = ""
    ) -> None:
        """One line into the program's `history.jsonl` — the record the dossier counts.

        Written by the loop from now on so the dossier does not depend on parsing prose;
        soft by contract, a run never stops on bookkeeping.
        """
        self.call(
            append_history,
            repo_dir=self.ctx.repo_dir,
            program_dir=self.ctx.program_dir,
            event=event,
            gate_id=gate_id,
            note=note,
            fingerprint=fingerprint,
        )

    def _check_target(self, target: NewTarget | None = None) -> str:
        """The in-code resolvability check on a (re)written frozen target.

        Empty when the target's effect can be told from seed noise on its own eval; else
        the one-line statement of why not, which is what the lead is handed to fix. The
        README is the source of truth when no explicit target was returned — the lead
        writes the table, the loop reads it back, and `why_resolvable` is never trusted.
        """
        if target is not None and target.n:
            frozen = FrozenTarget(
                metric=target.metric,
                dataset=target.dataset,
                threshold=target.threshold,
                threshold_count=target.threshold_count,
                n=target.n,
                threshold_value=target.threshold_count / target.n,
                seeds=target.seeds,
                deadline=target.deadline,
                baseline_count=target.baseline_count,
                baseline_value=target.baseline_count / target.n,
            )
        else:
            readme = self._abs(f"{self.ctx.program_dir}/README.md")
            text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
            frozen = parse_frozen_target(text)
            if not frozen.n:
                return (
                    "no `Frozen target` table with a `count/n` threshold could be read "
                    f"from {self.ctx.program_dir}/README.md"
                )
        verdict = resolvability(frozen)
        return "" if verdict.resolvable else verdict.statement

    def _record(self, gate_id: str, *, forced: str = "") -> RecordResult:
        """Write one outcome to the program's progress file."""
        args = self._program_args(gate_id=gate_id)
        if forced:
            args["gate_doc_path"] = f"{self.ctx.program_dir}/README.md"
            args["forced_outcome"] = forced
        return self.agent(
            "prompts/record-result.md",
            returns=RecordResult,
            # A gate outcome is bookkeeping — copy a verdict into the progress file.
            # A *forced* one is not: on `GOAL_BANKED` this turn writes the program's
            # product, the standalone claim a reader outside the program acts on.
            power="max" if forced else "low",
            args=args,
        )

    def _to_lead(
        self,
        gate_id: str,
        gate_doc_path: str,
        *,
        escalation: str,
        notes: str,
        budget: Budget,
        failed_criteria: list[FailedCriterion] | None = None,
    ) -> Continue:
        """Hand an exhausted repair budget to the lead, as a gate-level question.

        A repair budget that runs out is not a verdict about the science, and the loop
        must not record one: what it knows is that three engineering fixes, or two
        reworks, or two rescopes did not get this gate to a measurement. That is
        exactly the question `lead_review` answers — revive with a different scope, or
        call the direction dead — so the escalation goes there rather than to a
        terminal. Recording `FAIL_MAX_REWORKS` instead is an apparatus verdict wearing
        a science verdict's clothes.
        """
        return Continue(
            None,
            self.program_review,
            origin="escalation",
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria or [],
            notes=notes,
            escalation=escalation,
            budget=budget,
        )

    def _job_dir(self, gate_id: str, suffix: str = "") -> str:
        return job_dir_for(self.ctx.repo_dir, self.ctx.program_dir, gate_id, suffix)

    # --- the gate loop ------------------------------------------------------

    def start(self, budget: Budget = Budget()) -> Continue:
        """Pick the next gate, and route on what came back.

        An empty `gate_id` is read as "no gate" alongside the literal `"none"`: the
        resilience ladder defaults a missing key to `""`, and sending an unnamed gate
        to `design` would be the one unsafe reading.

        This is also where the per-gate counters start over, and it has to be here.
        Both a rework and a rescope route back to `design`, so clearing them there
        would reset the very budgets being spent.
        """
        dossier = self._dossier(budget)
        selection = self.agent(
            "prompts/select-next-gate.md",
            returns=GateSelection,
            # Reads the README ladder + progress and picks the next gate id — bounded
            # selection over existing docs, no deep reasoning needed.
            power="low",
            args=self._program_args(dossier_summary=summarize(dossier)),
        )
        if selection.gate_id in ("", "none"):
            # Ladder exhausted: don't terminate — let the lead judge the North star.
            return Continue(selection, self.goal_review, budget=budget)
        if selection.program_killed:
            # A pre-existing kill: let the research lead judge it, don't just die.
            return Continue(
                selection,
                self.program_review,
                origin="kill",
                gate_id=selection.gate_id,
                gate_doc_path=selection.gate_doc_path,
                failed_criteria=[],
                notes=selection.rationale,
                escalation="",
                budget=budget,
            )
        if dossier.review_due:
            # The computed triggers say the program is circling (or it has simply been
            # a while), and nothing about this gate is what settles that. The review
            # is fingerprint-deduped in the dossier, so "still circling" cannot loop
            # the review itself.
            return Continue(
                selection,
                self.program_review,
                origin="periodic",
                gate_id=selection.gate_id,
                gate_doc_path=selection.gate_doc_path,
                failed_criteria=[],
                notes=selection.rationale,
                escalation="",
                budget=budget,
            )
        self._history("gate_selected", selection.gate_id)
        return Continue(
            selection,
            self.design,
            gate_id=selection.gate_id,
            gate_doc_path=selection.gate_doc_path,
            budget=budget.fresh_gate(),
        )

    # --- the scientist ------------------------------------------------------

    def design(
        self,
        gate_id: str,
        gate_doc_path: str,
        budget: Budget = Budget(),
        rework_notes: str = "",
        failed_criteria: list[FailedCriterion] | None = None,
        rescope_reason: str = "",
    ) -> Continue:
        """Write the protocol, declare what it will cost, and time a calibration probe.

        The scientist never runs the experiment and never repairs code — what it
        produces is a protocol and three numbers, and the numbers are the load-bearing
        part. `estimate_s` sets the overrun thresholds the entire mid-flight triage is
        derived from, so it has to stand on something timed rather than on a feeling:
        the probe is mandatory and `submit` refuses a job without one.

        Re-entered three ways, and the parameters say which: a scientific rework
        (`rework_notes` + `failed_criteria`), a rescope after the design asked for more
        than the machine has (`rescope_reason`), or a fresh gate (neither).
        """
        if rework_notes:
            self._history("rework", gate_id, note=rework_notes)
        elif rescope_reason:
            self._history("rescope", gate_id, note=rescope_reason)
        design = self.agent(
            "prompts/design-experiment.md",
            returns=Design,
            # Validity is decided here — an oracle in the eval path, a control that is
            # not matched, a metric over the wrong split — and that error is not cheap
            # to hold: it burns the hours of CPU that follow, a rework lap, and, if the
            # check misses it, banks a result that is false.
            power="max",
            args=self._program_args(
                code_root=self.ctx.code_root,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rework_notes=rework_notes,
                failed_criteria=[c.model_dump(mode="json") for c in (failed_criteria or [])],
                rescope_reason=rescope_reason,
                rework_count=budget.reworks,
                rescope_count=budget.rescopes,
                envelope_ram_gb=self.ctx.envelope_ram_gb,
                envelope_cpus=self.ctx.envelope_cpus,
                envelope_gpu=self.ctx.envelope_gpu,
                envelope_disk_gb=self.ctx.envelope_disk_gb,
            ),
        )
        envelope = self.call(
            check_envelope,
            memory_mb=design.memory_mb,
            cpus=design.cpus,
            gpu=design.gpu,
            disk_gb=design.disk_gb,
            envelope_ram_gb=self.ctx.envelope_ram_gb,
            envelope_cpus=self.ctx.envelope_cpus,
            envelope_gpu=self.ctx.envelope_gpu,
            envelope_disk_gb=self.ctx.envelope_disk_gb,
        )
        if not envelope.fits:
            if budget.rescopes >= MAX_RESCOPES:
                return self._to_lead(
                    gate_id,
                    gate_doc_path,
                    escalation="max_rescopes",
                    notes=(
                        f"{MAX_RESCOPES} rescopes did not fit this gate onto the "
                        f"declared machine. Last attempt: {envelope.reason}"
                    ),
                    budget=budget,
                )
            return Continue(
                design,
                self.design,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rescope_reason=envelope.reason,
                budget=budget.rescoped(),
            )
        return Continue(
            design,
            self.build,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            design=design,
            budget=budget,
        )

    # --- the engineer -------------------------------------------------------

    def build(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        budget: Budget = Budget(),
        fix_reason: str = "",
    ) -> Continue | Await:
        """Make the protocol runnable, then rehearse it at `n=1` through the runner.

        Not in the engineer's shell. A command that works when typed and dies under the
        runner has failed the only test this state exists to run — it is the *handoff*
        that breaks: a relative path that meant something else from the agent's cwd, an
        inherited variable that is not in the job's environment, a result file written
        somewhere nobody will look. Rehearsing anywhere else rehearses the wrong thing.
        """
        if fix_reason:
            self._history("build_fix", gate_id, note=fix_reason)
        build = self.agent(
            "prompts/build-experiment.md",
            returns=Build,
            # The turn is long and tool-bound, and what it writes is the thing that has
            # to survive being handed to a detached process for hours.
            power="high",
            args=self._program_args(
                code_root=self.ctx.code_root,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                fix_reason=self._released_by(fix_reason),
                fix_count=budget.build_fixes,
                result_file="result.json",
            ),
        )
        if build.fault_locus == "tooling":
            return self._blocked(
                self._tooling_question(
                    gate_id,
                    component=build.component,
                    detail=build.notes,
                    where="building the experiment",
                ),
                self.build,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                budget=budget,
                fix_reason=f"{OPERATOR_RELEASED}: {build.notes}",
            )
        rehearsal = self.call(
            dry_run,
            job_dir=self._job_dir(gate_id, suffix="-dry"),
            command=build.dry_run_command,
            cwd=build.cwd or self.ctx.repo_dir,
            repo_dir=self.ctx.repo_dir,
            result_file=build.result_file,
            memory_mb=design.memory_mb,
            cpus=design.cpus,
        )
        if not rehearsal.ok:
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus=rehearsal.fault_locus,
                component="",
                reason=f"the n=1 rehearsal failed: {rehearsal.reason}",
                detail=rehearsal.stderr_tail,
                where="the n=1 rehearsal",
            )
        return Continue(
            build,
            self.submit,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            design=design,
            build=build,
            budget=budget,
        )

    def _tooling_question(
        self, gate_id: str, *, component: str, detail: str, where: str
    ) -> str:
        """The ask an operator answers when the fault is not in the repo.

        Workhorse, ostler, the workflow itself, the machine — none of them is something
        the engineer inside the run can repair, and a loop that keeps handing such a
        failure back to the engineer burns budget on a fix that cannot exist. Naming
        the component is the price of the escape hatch: an engineer that can route its
        own hard problems to a human by calling them "tooling" has every reason to.
        """
        named = component or "unnamed — the fault was classified from the traceback"
        return (
            f"Gate {gate_id or GOAL} is blocked on a **tooling** fault in {where}.\n\n"
            f"Component: {named}\n\n"
            f"{detail or '(no detail was reported)'}\n\n"
            "Fix the component, then answer this gate. The run resumes by rebuilding "
            "the experiment; nothing about the protocol or the gate's thresholds has "
            "changed, and no science budget was spent on this."
        )

    def _repair(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        budget: Budget,
        *,
        locus: str,
        component: str,
        reason: str,
        detail: str,
        where: str,
    ) -> Continue | Await:
        """Route one "produced no measurement" failure by **fault locus**.

        Three destinations and no fourth. A repo-code fault goes to the engineer,
        always — never to a human, because a traceback in code the run itself wrote is
        the one problem the loop is unambiguously equipped to fix. A tooling fault goes
        to an operator immediately, because no number of engineer laps repairs
        workhorse. And an exhausted engineering budget goes to the lead, because at
        that point the question has stopped being "why did it crash" and become
        "is this gate worth another shape".

        The locus itself is decided deterministically from the deepest traceback frame
        wherever there is a stack (`nodes/measure.classify_fault`); an agent only gets
        to declare one where there is nothing to read — a hang, an OOM, silently wrong
        output — and then it has to name the component.
        """
        if locus == "tooling":
            return self._blocked(
                self._tooling_question(
                    gate_id, component=component, detail=detail or reason, where=where
                ),
                self.build,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                budget=budget,
                fix_reason=f"{OPERATOR_RELEASED} a tooling fault: {reason}",
            )
        if budget.build_fixes >= MAX_BUILD_FIXES:
            return self._to_lead(
                gate_id,
                gate_doc_path,
                escalation="max_build_fixes",
                notes=(
                    f"{MAX_BUILD_FIXES} engineering repairs did not get this gate to a "
                    f"measurement. Last failure: {reason}"
                ),
                budget=budget,
            )
        return Continue(
            None,
            self.build,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            design=design,
            budget=budget.built(),
            fix_reason=f"{reason}\n\n{detail}".strip(),
        )

    # --- handing it to the runner -------------------------------------------

    def submit(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """Launch the measurement detached, and route the three ways it can refuse.

        Deterministic — no model call. `submit_job` is idempotent against a live job,
        which matters here more than anywhere else in the loop: a resume re-enters a
        state from the top, and re-entering this one must adopt the four-hour job that
        is already running rather than starting a fifth hour of it.
        """
        job = self.call(
            submit_job,
            job_dir=self._job_dir(gate_id),
            command=build.command,
            cwd=build.cwd or self.ctx.repo_dir,
            memory_mb=design.memory_mb,
            cpus=design.cpus,
            estimate_s=design.estimate_s,
            result_file=build.result_file,
            min_containment=self.ctx.min_containment,
            labels={"gate": gate_id, "program": self.ctx.program_dir},
            probe_units_timed=design.probe.units_timed,
        )
        if job.submitted:
            return Continue(
                job,
                self.await_result,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design,
                build=build,
                job_dir=job.job_dir,
                budget=budget,
            )
        if job.fault_locus == "design":
            # An estimate with no probe behind it. The scientist owns the probe, so
            # this is a design lap and not an engineering one — and it is cheap, which
            # is exactly why the refusal is here rather than after hours of CPU.
            if budget.rescopes >= MAX_RESCOPES:
                return self._to_lead(
                    gate_id,
                    gate_doc_path,
                    escalation="max_rescopes",
                    notes=f"the design kept arriving without a probe: {job.error}",
                    budget=budget,
                )
            return Continue(
                job,
                self.design,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rescope_reason=job.error,
                budget=budget.rescoped(),
            )
        return self._repair(
            gate_id,
            gate_doc_path,
            design,
            budget,
            locus=job.fault_locus,
            component="workhorse.job" if job.fault_locus == "tooling" else "",
            reason=f"the job would not launch: {job.error}",
            detail="",
            where="submitting the job",
        )

    def await_result(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        job_dir: str,
        budget: Budget = Budget(),
        seen_multiple: float = 0.0,
    ) -> Continue | Await:
        """Wait for the measurement — for hours or days, across driver deaths.

        The wait is an `Await` on the job's own `wake` file, which the supervisor
        touches on finish, on kill, and at each overrun threshold. That makes the wait
        free (no polling turn, no model call) and the run resumable: the checkpoint
        records `waiting_on`, so a driver that dies here comes back to exactly this
        state and re-reads the job rather than re-running the experiment.

        `watch_job` arms the wake file *before* it polls, which is what makes the wait
        lossless — see its docstring. `seen_multiple` is what keeps a single overrun
        threshold from triaging forever: it is the highest multiple already triaged,
        and it travels in the checkpoint.
        """
        watch = self.call(watch_job, job_dir=job_dir, seen_multiple=seen_multiple)
        common = {
            "gate_id": gate_id,
            "gate_doc_path": gate_doc_path,
            "design": design.model_dump(mode="json"),
            "build": build.model_dump(mode="json"),
            "job_dir": job_dir,
            "budget": budget,
        }
        if watch.action == "collect":
            return Continue(watch, self.collect, **common)
        if watch.action == "triage":
            return Continue(
                watch, self.triage, overrun_multiple=watch.overrun_multiple, **common
            )
        # No questions: nobody is being asked anything, and the file this parks on is
        # the supervisor's, not an operator's. `_ask` writes nothing for an empty ask,
        # and a missing file reads as unanswered — so the wait ends on the supervisor's
        # first touch and on nothing else. `on_machine` is what says that out loud: a
        # 40-hour measurement is not a human failing to answer a gate, and reporting it
        # as one costs a page and a wrong status per experiment.
        return Await.on_machine(
            Path(watch.wake_path),
            "",
            self.await_result,
            seen_multiple=seen_multiple,
            **common,
        )

    def triage(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        job_dir: str,
        overrun_multiple: float = 0.0,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """The engineer, mid-flight, on a job running far past its estimate.

        **Time is a bug signal, not a budget.** A job is never killed for running long
        — a command that overshoots is carrying information, about the code or about
        the estimate, and killing it destroys that information along with the work. So
        the overrun goes to the engineer rather than to a timeout, and the engineer
        decides: keep going, or kill it and repair.

        Keeping going is unbounded on purpose. The thresholds double, so the wakeups
        get rarer exactly as fast as the job gets less likely to be worth waiting for;
        a cap here would only convert a self-limiting series into an arbitrary one.
        """
        verdict = self.agent(
            "prompts/triage-overrun.md",
            returns=TriageResult,
            power="high",
            args=self._program_args(
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                job_dir=job_dir,
                overrun_multiple=overrun_multiple,
                estimate_s=design.estimate_s,
                probe=design.probe.model_dump(mode="json"),
                command=build.command,
                code_root=self.ctx.code_root,
            ),
        )
        if verdict.decision != "kill_and_fix":
            # Anything that is not an explicit kill keeps the measurement alive. The
            # conservative arm here is the one that does not destroy hours of work.
            return Continue(
                verdict,
                self.await_result,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design,
                build=build,
                job_dir=job_dir,
                budget=budget,
                seen_multiple=overrun_multiple,
            )
        stopped = self.call(kill_job, job_dir=job_dir, reason="overrun")
        return self._repair(
            gate_id,
            gate_doc_path,
            design,
            budget,
            locus=verdict.fault_locus or "repo",
            component=verdict.component,
            reason=(
                f"killed at {overrun_multiple:.0f}× its estimate after "
                f"{stopped.wall_s:.0f}s: {verdict.diagnosis}"
            ),
            detail=verdict.fix_hint,
            where="a job running past its estimate",
        )

    def collect(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        job_dir: str,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """Classify what came back, with **zero model calls**.

        Two artifacts make this decidable: the command wrote what it *found*, the
        supervisor wrote what it *cost*, and the command cannot fake the second one. So
        "measured and missed" and "produced no measurement" are told apart from files
        rather than from prose — which is the whole reason they can route to different
        people. One undifferentiated `needs_rework` over both is what previously sent a
        crash to a prompt forbidden from changing anything that would fix it.
        """
        collected = self.call(
            collect_job,
            job_dir=job_dir,
            repo_dir=self.ctx.repo_dir,
            cwd=build.cwd or self.ctx.repo_dir,
            result_file=build.result_file,
            memory_mb=design.memory_mb,
        )
        if collected.outcome == "over_resource":
            if budget.rescopes >= MAX_RESCOPES:
                return self._to_lead(
                    gate_id,
                    gate_doc_path,
                    escalation="max_rescopes",
                    notes=f"the experiment kept outgrowing its declared resources: "
                    f"{collected.reason}",
                    budget=budget,
                )
            return Continue(
                collected,
                self.design,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rescope_reason=collected.reason,
                budget=budget.rescoped(),
            )
        if collected.outcome in ("crash", "invalid"):
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus=collected.fault_locus,
                component="",
                reason=f"{collected.outcome}: {collected.reason}",
                detail=collected.stderr_tail,
                where="the measurement itself",
            )
        return Continue(
            collected,
            self.check,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            collected=collected.model_dump(mode="json"),
            budget=budget,
        )

    # --- the lead's verdict on one gate --------------------------------------

    def check(
        self,
        gate_id: str,
        gate_doc_path: str,
        collected: Collected,
        budget: Budget = Budget(),
    ) -> Continue:
        """Judge the artifact against the gate doc's thresholds — and **never re-run**.

        This is the state that used to run the whole measurement a second time, and
        take 76 minutes doing it, and be told that when it could not finish it should
        "run the largest subset that does and record it as a partial check". A verdict
        on a partial re-run is not a verdict; it is a second, worse experiment.

        What it gets instead is the artifact: the numbers the experiment wrote, and the
        cost the supervisor recorded beside them. Everything it needs to say approve,
        rework or kill is in those two files, and nothing it could learn by running the
        experiment again is worth the hours or the risk of a different answer.
        """
        check = self.agent(
            "prompts/gate-check.md",
            returns=GateCheck,
            # Every PASS the program ever banks comes through here. A lenient check is
            # indistinguishable from a real result — nothing downstream can recover the
            # difference — and it fires once or twice per gate, so the tier costs little
            # against what it protects.
            power="ultra",
            # Deliberately not `_program_args`: the reviewer is not shown the progress
            # file. It judges against the gate doc's criteria and the artifact, and what
            # the designer claimed is exactly what it must not be anchored on.
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
                "result": collected.model_dump(mode="json"),
            },
        )
        if check.status == "approved":
            return Continue(check, self.record_pass, gate_id=gate_id, budget=budget)
        failed = check.failed_criteria
        if check.status == "killed":
            return Continue(
                check,
                self.record_kill,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed,
                notes=check.notes,
                budget=budget,
            )
        if budget.reworks >= MAX_REWORKS:
            return self._to_lead(
                gate_id,
                gate_doc_path,
                escalation="max_reworks",
                notes=(
                    f"{MAX_REWORKS} scientific reworks measured and missed. "
                    f"Last check: {check.notes}"
                ),
                failed_criteria=failed,
                budget=budget,
            )
        return Continue(
            check,
            self.design,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            rework_notes=check.notes,
            failed_criteria=failed,
            budget=budget.reworked(),
        )

    # --- recording ----------------------------------------------------------

    def record_pass(self, gate_id: str, budget: Budget = Budget()) -> Continue:
        """Write the approved gate's outcome, publish, and take the next gate."""
        result = self._record(gate_id)
        self._history("pass", gate_id)
        self._publish()
        return Continue(result, self.start, budget=budget.cycled())

    def record_kill(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        budget: Budget = Budget(),
    ) -> Continue:
        """Write the kill, then hand off to the research lead rather than terminating.

        The lead sees the program before the gate: a kill is the moment the record is
        most likely to show circling, and the gate-level question ("was this kill
        sound?") only makes sense once the program-level one ("is this ladder still
        worth a gate?") has been answered.
        """
        self._record(gate_id)
        self._history("kill", gate_id, note=notes)
        return Continue(
            None,
            self.program_review,
            origin="kill",
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria,
            notes=notes,
            escalation="",
            budget=budget.cycled(),
        )

    # --- the research lead --------------------------------------------------

    def lead_review(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        escalation: str = "",
        budget: Budget = Budget(),
        dossier: str = "",
    ) -> Continue | Await:
        """Judge whether the gate is dead, and route the program on the verdict.

        Reached two ways, and `escalation` says which: a scientific kill (empty), or a
        repair budget that ran out (`max_build_fixes`, `max_reworks`, `max_rescopes`).
        The second is deliberately routed *here* rather than to a terminal — an
        exhausted apparatus budget is not a finding, and the lead is the only persona
        that can say whether the gate is worth a different shape.

        Kept a separate state from `goal_review` on purpose. They answer different
        questions — "was this kill sound?" against "where does the program go?" — and
        collapsing them loses the `banked` verdict, which only exists at program scope.
        """
        _, lead_reviews = self._spent(budget)
        if lead_reviews >= MAX_LEAD_REVIEWS + budget.lead_review_grants:
            return self._blocked(
                f"This program has spent {lead_reviews} research-lead reviews "
                f"(cap {MAX_LEAD_REVIEWS}), and gate {gate_id or GOAL} needs another "
                "one.\n\nThat many reviews usually means the program is looping on a "
                "question its ladder cannot settle. Look at the progress file before "
                "answering.\n\nAnswering this gate authorizes exactly one more review; "
                "the loop then continues from where it stopped. To stop the program "
                "instead, set its ledger status and do not answer.",
                self.lead_review,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                budget=budget.granted_review(),
                dossier=dossier,
            )
        if not dossier:
            dossier = render_dossier(self._dossier(budget))
        review = self.agent(
            "prompts/research-lead-review.md",
            returns=LeadReview,
            # The program's direction turns on this call — revive, redirect, or die —
            # and it fires at most a handful of times per program.
            power="ultra",
            args=self._program_args(
                goal=self.ctx.goal,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=[
                    c.model_dump(mode="json") for c in (failed_criteria or [])
                ],
                notes=notes,
                escalation=escalation,
                dossier=dossier,
            ),
        )
        self._history("lead_review", gate_id, note=review.verdict)
        if review.verdict == "revive":
            # A revival is where a circling program spends its months, so it is the
            # one verdict that goes back through the program lead before it acts.
            return Continue(
                review,
                self.program_review,
                origin="revive",
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                review=review,
                budget=budget,
            )
        if review.verdict == "new_direction":
            return Continue(
                review,
                self.new_direction,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                review=review,
                budget=budget,
            )
        # No verdict the loop can act on. That is a question for a person, not a reason
        # to stop the run: park, and re-enter this state with what the operator wrote.
        return self._blocked(
            f"The research lead returned no actionable verdict for gate "
            f"{gate_id or GOAL} (got {review.verdict!r}; expected `revive` or "
            "`new_direction`).\n\nDecide what the gate should do, write it into the "
            "gate doc, and answer this gate — the lead re-reads the doc on resume.",
            self.lead_review,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria or [],
            notes=notes,
            escalation=escalation,
            budget=budget,
            dossier=dossier,
        )

    def revive(
        self,
        gate_id: str,
        gate_doc_path: str,
        review: LeadReview,
        budget: Budget = Budget(),
    ) -> Continue:
        """Re-scope a gate that was killed for the wrong reason, then loop."""
        result = self.agent(
            "prompts/revive-gate.md",
            returns=ReviveResult,
            # Acts on the lead's verdict — a course-correcting decision, kept on the
            # same tier as the review that drove it.
            power="max",
            args=self._program_args(
                gate_id=gate_id, gate_doc_path=gate_doc_path, lead_review=review
            ),
        )
        self._history("revive", gate_id, note=result.status)
        spent = budget.reviewed()
        self._persist(spent)
        self._publish()
        return Continue(result, self.start, budget=spent)

    def new_direction(
        self,
        gate_id: str,
        gate_doc_path: str,
        review: LeadReview,
        budget: Budget = Budget(),
        dossier: str = "",
    ) -> Continue:
        """Define the direction that replaces a justifiably killed one — then check it.

        This used to be the one arm that always reached a person. It no longer does:
        the check a person was there to make — is the new ladder's frozen target one
        this program can actually resolve? — is now made in code, on the README the
        lead just wrote. A target that clears it starts at once; one that does not goes
        into the re-charter fix loop, which parks after one retry. The work is written
        and published either way, so a reader who wants to change it can.
        """
        if not dossier:
            dossier = render_dossier(self._dossier(budget))
        result = self.agent(
            "prompts/define-new-direction.md",
            returns=NewDirectionResult,
            # The most open-ended, highest-leverage call in the loop.
            power="ultra",
            args=self._program_args(
                goal=self.ctx.goal,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                lead_review=review,
                dossier=dossier,
            ),
        )
        self._history(
            "new_direction", gate_id, note=result.direction_name or result.core_question
        )
        spent = budget.reviewed()
        self._persist(spent)
        self._publish()
        failure = self._check_target()
        if not failure:
            return Continue(result, self.start, budget=spent)
        return Continue(
            result,
            self.recharter,
            review=ProgramReview(
                verdict="recharter",
                reason=(
                    f"The new direction **{result.direction_name or '(unnamed)'}** was "
                    "written, but its frozen target is not resolvable on its own eval."
                ),
                evidence=[failure],
            ),
            budget=spent,
            resolvability_failure=failure,
        )

    # --- the program lead ---------------------------------------------------

    def program_review(
        self,
        origin: str,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        escalation: str = "",
        review: LeadReview | None = None,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """Judge the *program* on its computed dossier, and route on a verdict that acts.

        Reached four ways, and `origin` says which: a kill (`kill`), an exhausted repair
        budget (`escalation`), a gate the gate-lead wants revived (`revive`), or the
        periodic check from `start` (`periodic`). The question is the one no gate-level
        state can ask — is this program still moving its frozen metric, or has it been
        reworking apparatus for two months? — and the evidence is computed rather than
        read: metric series with dates, seed spread against the required effect, kill
        and reopen counts, code churn, results still pending, the circling triggers.

        Seven verdicts, because "continue" and "stop" are the two that were never the
        problem. `probe_first` orders one cheap decisive measurement before any more
        gate work; `score_from_cache` reads a result that already exists instead of
        re-running; `recharter` changes a target the eval cannot resolve; `bank` and
        `stop_negative` are the program-scope terminals, reachable from a kill rather
        than only from an exhausted ladder; `operator` is for a fact no agent can
        produce. `continue` hands the gate-level question on to `lead_review`.
        """
        program_reviews, recharters = self._program_spent(budget)
        if program_reviews >= MAX_PROGRAM_REVIEWS + budget.program_review_grants:
            return self._blocked(
                f"This program has spent {program_reviews} program-level reviews "
                f"(cap {MAX_PROGRAM_REVIEWS}), and gate {gate_id or GOAL} needs another "
                f"one ({origin}).\n\nThat many program reviews means the lead keeps "
                "finding the program circling and keeps failing to stop it. Read the "
                "dossier the last one saw (`history.jsonl`, the progress file) before "
                "answering.\n\nAnswering this gate authorizes exactly one more review; "
                "the loop then continues from where it stopped. To stop the program "
                "instead, set its ledger status and do not answer.",
                self.program_review,
                origin=origin,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                review=review,
                budget=budget.granted_program_review(),
            )
        dossier = self._dossier(budget)
        rendered = render_dossier(dossier)
        verdict = self.agent(
            "prompts/program-review.md",
            returns=ProgramReview,
            # The program's months turn on this call, and it fires a handful of times
            # per program: every kill, every escalation, every revival, and when the
            # computed triggers say the record has stopped moving.
            power="ultra",
            args=self._program_args(
                origin=origin,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                escalation=escalation,
                goal=self.ctx.goal,
                notes=notes,
                program_reviews_spent=program_reviews,
                program_reviews_max=MAX_PROGRAM_REVIEWS,
                recharters_spent=recharters,
                recharters_max=MAX_RECHARTERS,
                dossier=rendered,
            ),
        )
        spent = budget.program_reviewed()
        self._persist(spent)
        self._history(
            "program_review",
            gate_id,
            note=f"{origin}: {verdict.verdict} — {verdict.reason}",
            fingerprint=dossier.fingerprint,
        )
        if verdict.verdict == "continue":
            if origin == "revive" and review is not None:
                return Continue(
                    verdict,
                    self.revive,
                    gate_id=gate_id,
                    gate_doc_path=gate_doc_path,
                    review=review,
                    budget=spent,
                )
            if origin == "periodic":
                self._history("gate_selected", gate_id)
                return Continue(
                    verdict,
                    self.design,
                    gate_id=gate_id,
                    gate_doc_path=gate_doc_path,
                    budget=spent.fresh_gate(),
                )
            return Continue(
                verdict,
                self.lead_review,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                budget=spent,
                dossier=rendered,
            )
        if verdict.verdict in ("probe_first", "score_from_cache", "recharter"):
            if verdict.verdict == "recharter" and recharters >= MAX_RECHARTERS:
                return self._blocked(
                    f"This program has re-chartered its frozen target {recharters} "
                    f"times (cap {MAX_RECHARTERS}), and the lead wants to again:\n\n"
                    f"{verdict.reason}\n\nProposed: {verdict.recharter.metric or '?'} "
                    f"on {verdict.recharter.dataset or '?'}, "
                    f"{verdict.recharter.threshold or '?'} (n={verdict.recharter.n}) — "
                    f"{verdict.recharter.why_resolvable or '(no resolvability case)'}"
                    "\n\nA program that cannot settle on a resolvable target is a "
                    "program whose eval a person has to choose. Write the target into "
                    "the README's `Frozen target` table and answer this gate; the loop "
                    "reads it back and continues.",
                    self.start,
                    budget=spent,
                )
            return Continue(verdict, self.recharter, review=verdict, budget=spent)
        if verdict.verdict == "bank":
            return Continue(verdict, self.record_goal, outcome=GOAL_BANKED, budget=spent)
        if verdict.verdict == "stop_negative":
            return Continue(
                verdict, self.record_goal, outcome=GOAL_IMPOSSIBLE, budget=spent
            )
        question = (
            verdict.operator_question
            if verdict.verdict == "operator" and verdict.operator_question
            else (
                f"The program lead returned no actionable verdict for gate "
                f"{gate_id or GOAL} (got {verdict.verdict!r}; expected `continue`, "
                "`probe_first`, `score_from_cache`, `recharter`, `bank`, "
                "`stop_negative` or `operator`)."
            )
        )
        return self._blocked(
            f"{question}\n\nReason: {verdict.reason or '(none given)'}\n\nWrite the "
            "answer here and answer this gate; the program lead re-reads the record on "
            "resume.",
            self.program_review,
            origin=origin,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria or [],
            notes=notes,
            escalation=escalation,
            review=review,
            budget=spent,
        )

    def recharter(
        self,
        review: ProgramReview,
        budget: Budget = Budget(),
        attempt: int = 0,
        resolvability_failure: str = "",
    ) -> Continue | Await:
        """Apply a program-level verdict to the program folder, in place, then loop.

        Three verdicts land here and one turn applies whichever fields the review set:
        a probe gate written to the top of the ladder, a score-from-cache directive on
        an existing gate doc, a rewritten frozen target. The target is the one that is
        *checked*: the lead's `why_resolvable` is prose, and the loop reads the written
        numbers back and computes whether the required effect clears seed noise. A miss
        is handed back once with the exact statement; a second miss is an eval a person
        has to choose.
        """
        result = self.agent(
            "prompts/program-recharter.md",
            returns=RecharterResult,
            # Rewrites the program's contract — target, ladder, directives — on the
            # same tier as the review that ordered it.
            power="max",
            args=self._program_args(
                review=review.model_dump(mode="json"),
                dossier=render_dossier(self._dossier(budget)),
                resolvability_failure=resolvability_failure,
                gate_template=str(GATE_TEMPLATE),
                today=date.today().isoformat(),
            ),
        )
        rechartered = review.verdict == "recharter" or bool(result.new_target.n)
        failure = ""
        if rechartered:
            failure = self._check_target(result.new_target)
        if failure and attempt < MAX_RECHARTER_FIXES:
            self._history("recharter", note=f"unresolvable, retrying: {failure}")
            self._publish()
            return Continue(
                result,
                self.recharter,
                review=review,
                budget=budget,
                attempt=attempt + 1,
                resolvability_failure=failure,
            )
        if failure:
            self._history("recharter", note=f"unresolvable, parked: {failure}")
            self._publish()
            return self._blocked(
                f"The re-chartered target is still not resolvable after "
                f"{attempt + 1} attempts:\n\n{failure}\n\nThe lead's case: "
                f"{result.new_target.why_resolvable or '(none)'}\n\nSupply a bigger "
                "eval or a different metric in the README's `Frozen target` table and "
                "answer this gate; the loop reads it back and continues.",
                self.start,
                budget=budget,
            )
        event = {
            "probe_first": "probe_ordered",
            "score_from_cache": "cache_directive",
        }.get(review.verdict, "recharter")
        spent = budget.rechartered() if rechartered else budget
        self._history(
            event,
            review.probe.gate_id or review.cache_gate_id,
            note=result.reason or review.reason,
        )
        self._persist(spent)
        self._publish()
        return Continue(result, self.start, budget=spent)

    # --- self-extension -----------------------------------------------------

    def goal_review(self, budget: Budget = Budget()) -> Continue | Await:
        """Every reachable gate passed — so judge the program against its North star.

        Four verdicts, not three. With only `reached`/`impossible`/`extend`, a program
        whose North star is genuinely ambitious has exactly one verdict available for
        years: neither the end-state capability nor a proved dead-end, so `extend` —
        again, and again. Every real result it produces along the way is reclassified
        as insufficient the moment it lands, because the only thing the loop can say
        about a partial result is "not the goal yet". `bank` is the missing verdict:
        the result is worth shipping *now*, the program stops clean, and continuing it
        costs a human decision (`reauthorize`) rather than another lap.
        """
        extensions_spent, _ = self._spent(budget)
        review = self.agent(
            "prompts/lead-goal-review.md",
            returns=GoalReview,
            # The one turn the whole program's ending rests on: it decides whether the
            # program is done, dead, shippable, or must grow.
            power="ultra",
            args=self._program_args(
                code_root=self.ctx.code_root,
                goal=self.ctx.goal,
                # The lead sees its own spend. Judging "is another gate worth it?"
                # without knowing this is the fifth extension is judging blind.
                extensions_spent=extensions_spent,
                extensions_max=MAX_EXTENSIONS,
                dossier=render_dossier(self._dossier(budget)),
            ),
        )
        if review.verdict == "reached":
            return Continue(review, self.record_goal, outcome=GOAL_REACHED, budget=budget)
        if review.verdict == "banked":
            return Continue(review, self.record_goal, outcome=GOAL_BANKED, budget=budget)
        if review.verdict == "impossible":
            return Continue(
                review, self.record_goal, outcome=GOAL_IMPOSSIBLE, budget=budget
            )
        if review.verdict == "extend":
            # The cap belongs in *this* arm and nowhere else. Guarding before the
            # verdict — as the loop used to — blocks a program that was about to
            # declare itself reached, on a budget that only ever bounded growth.
            if extensions_spent >= MAX_EXTENSIONS + budget.extension_grants:
                return self._blocked(
                    f"This program has extended itself {extensions_spent} times "
                    f"(cap {MAX_EXTENSIONS}) and the lead wants another gate:\n\n"
                    f"{review.next_gate_title or '(untitled)'} — "
                    f"{review.next_gate_question or '(no question stated)'}\n\n"
                    f"North star gap: {review.north_star_gap or '(not stated)'}\n\n"
                    "A program at this cap is usually deferring a verdict it could "
                    "give: read the ladder and decide whether the strongest result so "
                    "far is bankable. Answering authorizes exactly one more "
                    "extension.",
                    self.goal_review,
                    budget=budget.granted_extension(),
                )
            return Continue(
                review,
                self.extend,
                review=review,
                budget=budget,
            )
        return self._blocked(
            f"The goal review returned no actionable verdict (got "
            f"{review.verdict!r}; expected `reached`, `banked`, `impossible` or "
            "`extend`).\n\nThe ladder is exhausted, so the program cannot proceed "
            "without one. Record your judgement in the program README and answer this "
            "gate; the lead re-reads it on resume.",
            self.goal_review,
            budget=budget,
        )

    def extend(self, review: GoalReview, budget: Budget = Budget()) -> Continue:
        """Append the next gate to the ladder, then loop — it is now the lowest
        non-PASS gate, so `start` picks it up."""
        result = self.agent(
            "prompts/extend-program.md",
            returns=ExtendResult,
            # Writes the next gate (ladder + gate doc + progress) — new science.
            power="max",
            args=self._program_args(
                code_root=self.ctx.code_root, goal=self.ctx.goal, goal_review=review
            ),
        )
        spent = budget.extended()
        self._persist(spent)
        self._publish()
        return Continue(result, self.start, budget=spent)

    # --- the one terminal ---------------------------------------------------

    def record_goal(self, outcome: str, budget: Budget = Budget()) -> Done:
        """Record a goal verdict, conclude the program in its ledger, publish, end clean.

        The only way this workflow ends, and all three ways through it are *scientific*
        verdicts. `impossible` is a recorded negative — a real result — not an apparatus
        failure; `banked` is a positive one that is simply smaller than the North star.
        There is deliberately no apparatus terminal beside them: a loop that could stop
        itself red would, and the ten hours it then sits unnoticed are the reason this
        state has no sibling.
        """
        result = self._record(GOAL, forced=outcome)
        self._history("goal", GOAL, note=outcome)
        self._persist(budget, status=GOAL_STATUS.get(outcome, "active"))
        self._publish()
        return Done(result)


workflow = Registry("research", package=__package__).add_blueprints(blueprint).stub_agents(
    {
        # What `--dry-run` gets back, and why it is these two prompts. Every arm of
        # this machine returns to `start`, and `start` routes on whatever
        # `select-next-gate` says — so a stand-in naming a gate walks the loop
        # forever rather than further, and the only path a *static* reply can walk
        # to a terminal is the one where the ladder is exhausted and the lead judges
        # the North star. The arms it does not take are covered by the static
        # preflight pass, which reads every state's source rather than one run's
        # path. Everything else a turn returns stays a blank model.
        "select-next-gate": {"gate_id": ""},
        "lead-goal-review": {"verdict": "reached"},
        "program-review": {"verdict": "continue"},
        "program-recharter": {"status": "written"},
    }
)
main = console_script(workflow.entry_point(Research))
