"""The QA flow's models — the running verdict, and what each deterministic gate returns.

**`QaResult` is one model for what the YAML kept as one key.** Nine nodes wrote
`qa_result` — the ostler runner, the evidence gate, the sentinel gate, the regression
suite, three `mark-*` scripts and three agent turns — with three different payload shapes,
because a run-context key has no schema. Here it is a single model — `status` and `notes`,
what every one of those writers actually produced — and it is what the flow threads from
gate to gate as *the* verdict. The ostler-backed runner produces more, so it returns the
`QaPlanRun` subclass; a `QaResult`-typed field holds it without losing the payload.

**The status vocabularies stay separate.** `QaResult.status` is ostler's four-state
`passed | failed | blocked | invalid`; `QaPlanValidation.status` is the two-state
`passed | invalid` the validator computes for itself off a returncode. They looked alike as
untyped dicts and routed through different branch tables; they are different types here.

The `qa_cleared`, `stack_*`, `backlog_items_*` and `screenshots_*` keys were flat scalars
sprayed into the run context — six of them for `ensure-stack.py` alone. Each script's set
becomes one model, because the set is what the script actually returns.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding

#: What a QA run came to. Ostler's four states, and the only vocabulary the rolling verdict
#: is ever written from — every gate that hands the loop a verdict writes one of these.
QaStatus = Literal["passed", "failed", "blocked", "invalid"]

#: `qa-story.md`'s reading of a run it managed to read: whether the runner's own result can
#: be trusted for routing, and if not, which stage repairs what. See `QaAssessment`.
QaDisposition = Literal["confirmed", "repair_plan", "extend_plan", "repair_setup"]

#: The same turn's account of *why*, on the axis the flow routes on: `product` fails the
#: story deterministically, `environment` reaches setup, `plan` and `evidence` reach the
#: plan author, and `none` is the assessment of a run that failed at nothing.
QaFailureClass = Literal["none", "product", "plan", "environment", "evidence"]

#: `audit-qa.md`'s verdict on a pass that already cleared the gate, and what a refutation
#: says the pass was wrong about.
QaAuditVerdict = Literal["stands", "refuted"]
QaRefutationClass = Literal["none", "product-contradiction", "plan-defect", "evidence-defect"]

#: `triage-qa.md`'s two answers: whether the story's acceptance criteria were amended, and
#: what the remaining failure needs. The class is what the one bonus verification pass is
#: granted on, which is why `evidence` is separate from `code`, and it is what returns a
#: story to the dev lane, which is why `product` is separate from both.
QaTriageAction = Literal["rescope", "qa_fix"]
QaTriageClass = Literal["code", "product", "evidence", "environment"]

#: What the whole flow hands its parent. Not a QA verdict — a routing answer, which is why
#: it is a vocabulary of its own rather than a widening of `QaStatus`. See `QaFlowResult`.
QaFlowStatus = Literal["passed", "inconclusive", "replan", "rescope", "refix"]


class QaResult(CoderResult):
    """The story's running QA verdict — ostler's four states, plus the blank before one.

    `status` starts empty rather than at `invalid`: the flow reads it before anything has
    run (`plan_qa` is handed the previous pass's notes, and `setup_fix` can be reached
    before the runner ever executes), and an unrun gate is not a failed one. Every branch
    that routes on it names its arms explicitly and sends the blank to a `default`, which
    is what the YAML's branch tables did.

    The runner's raw payload is **not** a field here — see `QaPlanRun` below for why.
    """

    status: QaStatus | Literal[""] = Field(
        default="",
        description="The story's rolling QA verdict as the turn leaves it. `invalid` while "
        "the plan or its context is being regenerated; `blocked` when the repair itself is.",
    )
    notes: str = Field(default="", description="One line on why the verdict stands there.")


class QaPlanRun(QaResult):
    """`run_qa_plan`'s verdict, plus the ostler payload only it has.

    `ostler` is a subclass field rather than an optional field on `QaResult` because a
    model's top-level fields are the output keys an agent turn is *asked* for — a field
    here is a promise every writer of this model must keep. Three agent turns return a
    `QaResult`, and none of them has a runner payload to report, so declaring `ostler` on
    the base made every one of those turns unparseable: the reply carried `status` and
    `notes`, the driver demanded a third key, and the node spent its whole retry →
    reframe ladder before defaulting to a blank verdict. The payload belongs to the one
    script node that produces it.

    Nothing reads `ostler`; it is kept for the run record, and a `QaResult`-typed field
    holds this subclass without losing it.
    """

    ostler: dict[str, Any] = {}


class QaRunResult(CoderResult):
    """One QA verdict an agent turn was asked for — the fix lane's check, retry and recheck.

    Separate from `QaResult` because the two are produced by different things. `QaResult` is
    the *rolling* verdict Python threads from gate to gate, and it starts blank because the
    flow reads it before anything has run. This one is what a turn *reports*, so `status` is
    a required `Literal` with no default: a turn that cannot name which of the three it found
    has not reported, and the parse failure buys a retry turn where a blank bought a silent
    "not passed" arm nobody chose.

    Three values, not ostler's four: a grading turn either passed the item, failed it, or
    could not grade it at all. `invalid` is a QA *plan*'s verdict and no turn here writes one.
    """

    status: Literal["passed", "failed", "blocked"] = Field(
        description="`passed` when every acceptance criterion is verified by something you "
        "actually ran — a criterion you could not exercise is never a pass. `failed` when "
        "the defect is real, in scope and you did not finish it, including when it is hard, "
        "when you ran out of ideas, or when your fix did not verify; that sends the item "
        "round again. `blocked` only when no further attempt in this repository could "
        "succeed because what is missing is external to it: a credential or deployment you "
        "cannot perform, a product decision present in neither the story nor the plan, or "
        "work that lives in a repo you were not given. Reaching for `blocked` to get out of "
        "difficult work is the exact failure this stage exists to stop.",
    )
    notes: str = Field(
        default="",
        description="What you ran, what you observed and what remains: the files changed, "
        "the commands that exercised them, and for a non-pass the specific defect or the "
        "missing dependency. This text is handed on to the turn that follows, so it has to "
        "be enough to act on — \"blocked, cannot fix\" comes straight back to you.",
    )


class QaPlanValidation(CoderResult):
    """`ostler qa validate` — is the authored `qa_plan.py` a plan the runner can execute?

    Two states only, and `invalid` is the default for the same reason `OkfContextResult`
    uses it: the script computed the verdict from a returncode rather than reading it off
    ostler, so a missing answer is a failure to validate, not a pass.
    """

    status: Literal["passed", "invalid"] = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


class DryRunGate(CoderResult):
    """Did the repair turn actually execute the scenarios it was told to repair?

    The deterministic half of the dry-run contract in `repair-qa-plan.md`. A repair turn that
    edits a locator and returns has established nothing — the next full suite run is what
    finds out, forty minutes later, and a lap that costs a whole run to learn one assertion
    still fails is the loop this gate exists to cut. The turn has the stack up and the plan on
    disk, so it can run the failing scenario itself for the price of a shell command.

    `status` is `passed` or `failed`, on the same two-state rule as `QaPlanValidation`, and a
    failure routes back into the repair loop on the same budget rather than a new one.
    `scenarios` is what was demanded; `verified` is what the scratch evidence proved.
    """

    status: Literal["passed", "failed"] = "failed"
    notes: str = ""
    scenarios: list[str] = []
    verified: list[str] = []


class QaToolCatalog(CoderResult):
    """`ostler qa tools list` — the tools this repo opted into, resolved for this host.

    A node output rather than a value `_plan_args` reads straight off `agents.yml`,
    because it crosses the same host boundary `qa_plan_validation` does: which tools
    resolve, and whether their binaries are on `PATH`, is a fact about *this* machine,
    and a resumed run must see the catalog it was checkpointed with, not one re-derived
    against whatever the host looks like when the resume happens to run.
    """

    tools: list[dict[str, Any]] = []
    errors: list[str] = []


class QaCleared(CoderResult):
    """`clear-qa-evidence.py` — the stale `qa/` outputs and root verdict are gone.

    The script's `{"qa_cleared": "yes"}` was unconditional: it printed the same string
    whether it deleted two artifacts or found no spec dir at all. `cleared` is `False` on
    that second path, so the run record distinguishes "nothing to clear" from "cleared" —
    nothing branches on it either way, exactly as before.
    """

    cleared: bool = False


class StackStatus(CoderResult):
    """`ensure-stack.py` — the durable QA stack is up, adopted, undeclared, or broken.

    `ready` splits the empty manifest in two, because "no stack" means opposite things
    depending on what the book describes. `none` means the book *serves* something — a
    `screen` or a `server` — but declares no way to bring it up: no stack `runbook`, no
    `walkthrough: true` server. That is not a pass: it used to be spelled `skip` and
    routed exactly where `yes` did, so a repo that had never authored a runbook ran its
    QA against nothing and found out only once the runner failed for reasons no fixer
    could read. `unneeded` means the book serves nothing — a CLI's, a library's, an
    infrastructure program's — so an empty stack is its documented topology, and asking
    a fixer to author a runbook would be asking it to declare a stack for nothing;
    depot-style artifact repos looped forever on exactly that ask. `none` and `no`
    reach the setup-repair loop; `yes` and `unneeded` run QA.

    The pids are strings because `ostler.qa.stack.ensure_stack` returns them that way —
    they are recorded for a human killing a leaked stack, never arithmetic.
    """

    ready: Literal["yes", "no", "none", "unneeded"] = "no"
    app_pid: str = ""
    app_pgid: str = ""
    entry_url: str = ""
    failed_step: str = ""
    notes: str = ""


class StackTornDown(CoderResult):
    """`teardown_stack` — the run is over, so the stack it started need not outlive it.

    `torn_down` is `yes`, `no` or `skipped`; none of them fails the run. A stack is an
    expensive thing to have running and a cheap thing to have left running, so a runbook
    that declares no `stop:` recipe is honoured rather than second-guessed — that is the
    `skipped` case, and it is the leave-it-up policy the reuse doctrine already states.
    """

    torn_down: Literal["yes", "no", "skipped"] = "no"
    notes: str = ""


class BacklogDrain(CoderResult):
    """`append-backlog-item.py` — the coder→author edge, drained into `docs/backlog.md`.

    Both counts are reported and neither is routed on: the filer is best-effort by design,
    and an unwritable backlog degrades to `appended=0` with the items file kept rather than
    failing the story.
    """

    appended: int = 0
    skipped: int = 0
    notes: str = ""


class ScreenshotFlush(CoderResult):
    """`flush-root-screenshots.py` — stray root images relocated into `<spec_dir>/qa/`.

    `kept_tracked` is the count left alone because git already tracks them: a tracked root
    image is a committed asset, not QA litter.
    """

    flushed: int = 0
    kept_tracked: int = 0
    notes: str = ""


class RegressionSuite(CoderResult):
    """One service's declared regression command, resolved to where it runs."""

    #: `<repo>::<path>`, the same identity the dev lane dispatches on.
    label: str = ""
    #: Absolute path to the service directory the command runs in.
    cwd: str = ""
    #: What `agents.yml` declares under this service's `regression:` key. Never guessed.
    command: str = ""


class RegressionSuites(CoderResult):
    """`detect_regression_suites` — which committed suites, if any, this plan put at risk.

    Empty means "no service this plan touched declares a regression command", which skips
    the whole regression step. That is the opposite default from every gate in this module,
    and deliberate — this is a router, not a verdict, and it fails **open**: an unreadable
    plan context reports nothing to run rather than blocking a story.

    It replaced a `platform` field of `web`/`mobile`/`both`/`none`, which was the workflow
    holding an opinion about which stacks have journey suites. A repo that runs its journeys
    some third way could not say so, and one whose service type was not on the list was
    silently exempt from a suite it really had.
    """

    suites: list[RegressionSuite] = []


class FailureAttribution(CoderResult):
    """Which OKF node, if any, claims to verify a failing regression test.

    Diagnostic only. `classification` is `impacted` (a node this story changed verifies
    it), `outside-impact` (some other node does) or `unattributed` (the OKF
    `verificationIndex` names no owner) — and none of the three weakens the gate: a
    regression failure is the story's fix work whichever bucket it lands in.
    """

    test: str = ""
    path: str = ""
    classification: Literal["impacted", "outside-impact", "unattributed"] = "unattributed"
    nodes: list[str] = []


class RegressionRun(CoderResult):
    """`run_regression_suite` — the committed journey suites' own verdict.

    Five states, not ostler's four, because two different things used to arrive here as
    `passed`. **`skipped` is a fact**: no service declares a `regression:` command, or the
    suite it names contains no flows — a repo with no regression suite has not failed one,
    and the story proceeds. **`error` is a defect**: the declared command could not be run
    at all, because the tool it names is absent or the service directory it needs does not
    exist. Reported as a pass, that is a gate silently deleting itself — the repo believes
    it runs journeys on every story and no journey has run for weeks. So `error` blocks.

    `blocked` keeps its own meaning between them: the runner ran and the *stack under test*
    was unreachable or hung, which the shared setup-repair loop exists to fix. Only a real
    non-zero suite exit is `failed`.

    `as_qa_result()` is the mirror the `blocked → setup_fix` loop reads, which knows only
    ostler's four states — see there for how the two new ones cross that boundary.
    """

    status: Literal["passed", "failed", "blocked", "skipped", "error"] = "skipped"
    failing_tests: list[str] = []
    log_path: str = ""
    notes: str = ""
    failure_attribution: list[FailureAttribution] = []

    def as_qa_result(self) -> QaResult:
        """The story's running verdict, in the four states everything downstream routes on.

        A skip is a pass to that vocabulary and a broken runner is a block — but the word
        this model actually holds is prefixed onto the notes rather than dropped, because
        the notes are what briefs the report turn and what an operator reads at the gate.
        "regression error: `make regression` could not be run" and "the stack was not
        reachable" are the same `blocked` here and two different repairs in the repo.
        """
        mirrored: QaStatus = "passed" if self.status == "skipped" else (
            "blocked" if self.status == "error" else self.status
        )
        notes = (
            f"regression {self.status}: {self.notes}"
            if self.status in {"skipped", "error"}
            else self.notes
        )
        return QaResult(status=mirrored, notes=notes)


# ── the agent turns' replies ──────────────────────────────────────────────────────────
# Each model's *top-level field names* are the output keys the turn is asked for — that is
# what `_outputs_for` reads off it — and the field defaults are the YAML's `default:` blocks,
# which is where a turn that answered nothing lands.


class ContextRepair(CoderResult):
    """The repair half of `qa/prompts/repair-qa-context.md` — did the obligation packet heal?

    `repaired` re-runs the build; `blocked` goes to the operator gate. Two arms and no
    default: a turn that will not say which of the two it managed has not reported, and the
    parse retry that buys is a cheaper answer than the silent trip to the operator a blank
    used to take.
    """

    status: Literal["repaired", "blocked"] = Field(
        description="`repaired` when the grounding is fixed and the packet can be rebuilt. "
        "`blocked` only when the repair needs an author or product decision, or a source "
        "repository you were not given.",
    )
    notes: str = Field(
        default="", description="What you repaired — or, when blocked, what it needs."
    )

    def as_qa_result(self) -> QaResult:
        """This repair as the story's running QA verdict.

        The turn used to be asked for both — its own status *and* a `QaResult` beside it,
        the one two-key agent reply in the coder. The second key was never a second
        judgement: `repaired` means the packet is being rebuilt, which is `invalid`, and
        `blocked` means the repair is, which is `blocked`. A mapping Python can write is
        not a question worth spending an agent's attention on, and asking for it let a
        turn contradict itself.
        """
        return QaResult(
            status="invalid" if self.status == "repaired" else "blocked", notes=self.notes
        )


class QaPlanResult(CoderResult):
    """`plan-qa.md` — the authored `qa_plan.py`, as the author reports it.

    Its prose is judged by nothing: the plan itself is judged by `validate_qa_plan` reading
    the file, not by the author's word for it. Kept because the YAML declared the key and the
    run record is poorer without the author's own account of what it wrote.

    `repaired_scenarios` is the exception, and only on the repair path. The dry-run gate has
    to know which scenarios a repair *touched* — a repair that rewrote a scenario the last
    run passed is exactly as capable of breaking it, and the failing set the flow already has
    cannot name it. It is a claim, not evidence: the gate still reads the scratch run log for
    each id, so naming a scenario it did not dry-run fails the gate rather than passing it.

    `proved_scenarios` is the same mechanism pointed at the *first draft*. The draft has no
    failing set to be dispatched against, so until now it was the one plan turn that reached
    the runner on nobody's word but its own — and the cheapest defects in this lane are the
    ones a first draft makes: a locator that resolves to nothing, a fixture that is not
    seeded, a straight apostrophe where the surface renders U+2019. Each of those cost a full
    suite run and a repair lap to discover. The author now names the one or two scenarios it
    judged riskiest and dry-runs them before it answers, and the same gate reads the same
    scratch evidence for the ids it named. Empty is not an error — a plan of one trivial
    unit scenario has nothing worth proving — but a named id with no green log behind it is.
    """

    status: Literal["done", "blocked"] = Field(
        description="`done` when the plan is written. `blocked` only when no plan this "
        "stage could write would be a real test of the story: the criteria name a surface, "
        "device, service or credential that does not exist to drive, they contradict each "
        "other or the code so that no scenario can assert either reading, or the coverage "
        "lives in a repo you were not given. A plan that is merely hard to write is not "
        "blocked. Never write scenarios you know cannot run and report `done` — a plan that "
        "dry-runs green by asserting nothing is worse than no plan, because the run "
        "continues on it.",
    )
    notes: str = Field(
        default="",
        description="What you wrote, or — on a repair — each finding you closed and how, "
        "naming any you did not close and why. On `blocked`, the specific dependency and "
        "what you attempted before concluding it.",
    )
    repaired_scenarios: list[str] = Field(
        default=[],
        description="On a repair turn, the id of every scenario whose code you changed, "
        "added ones included: a scenario the last run passed can be broken by this turn and "
        "nothing else would catch it. The dry-run gate reads the scratch log for each id, so "
        "naming one you did not dry-run refuses the repair. Empty on a first draft, which "
        "repaired nothing.",
    )
    proved_scenarios: list[str] = Field(
        default=[],
        description="On a first draft, the ids you dry-ran green, riskiest first — evidence "
        "you point at rather than a claim you make, read from the same scratch logs. Empty "
        "is allowed when nothing in the plan is worth proving; a named id with no green log "
        "behind it is not.",
    )


class QaFinding(Finding):
    """One QA finding, from any of the three gates, with the authority it falls under named.

    `target`/`issue`/`repair` come from `Finding` — this class is where that shared shape
    was first written, and it is now the contract every lane's findings are held to.

    `scope` is closed for the same reason `DocumentationFinding.kind` is, and here the
    closure is load-bearing rather than diagnostic. Every gate's brief says in prose that the
    heavyweight shared stack is `ensure_stack`'s and not the plan's, and that a finding the
    author cannot act on inside a plan file spends the repair budget for nothing — and gates
    keep issuing them anyway. Prose cannot filter prose. A named scope can.

    The scope now decides *routing*, not just filtering: `_route_findings` sends a
    `product-test` finding to the fix loop, a `plan` finding to the plan author and a `stack`
    finding to setup. Dropping the first two on the floor is what livelocked a live story for
    82 minutes — three gates kept rediscovering a missing test assertion and kept billing the
    one author who could not write it.

    `kind` is the second closed axis, and it exists because `scope` alone could not stop the
    other way this loop fails to terminate. `scope` answers *where the repair lives*; `kind`
    answers *what breaks if the plan ships as it stands*, which is decidable by naming the
    consumer that reads the thing:

    `coverage`   an AC or OKF obligation has no cited evidence that would catch it failing.
                 The runner's behaviour changes. This is the only kind that refuses a plan.
                 Since the pre-run reviewer's deletion, `ostler qa validate` catches the
                 mechanical half of it before any gate reads the file.
    `overclaim`  a checkpoint asserts more than its cited test proves. Execution is
                 unaffected, but `audit-qa` reads the plan's claims, so leaving one in place
                 seeds a refutation later — it is repaired, just not re-reviewed.
    `cosmetic`   counts, wording, ordering. No gate and no runner reads it.

    The default is `coverage` so the field is fail-closed: an omitted `kind`, a checkpoint
    written before this field existed, and the `assess`/`audit` gates that share this model
    without classifying all keep exactly the behaviour they had.

    The case that motivated it: a live story spent four `power="high"` pre-run review passes
    and then ended with *no QA verdict at all*, because after the first pass found a real
    evidence defect the next three each raised a fresh prose nit — a viewport claim the run
    does not exercise, and an objective saying "10 test cases" where the file has 9. Its own
    prose classified them correctly ("neither reflects a missing acceptance-criterion
    coverage gap") and it refused anyway; the instruction to approve what it had listed was
    prose, and prose cannot filter prose. That node is gone, and the axis it forced is what
    the surviving gates are still judged on.
    """

    id: str = Field(
        default="",
        description="Any stable handle. Reuse the same one when you restate a finding "
        "across passes.",
    )
    scope: Literal["plan", "stack", "product-test"] = Field(
        default="plan",
        description="Where the repair lives — the flow routes on this field rather than on "
        "your prose. `plan`: an edit inside `qa_plan.py` / `qa-plan.md`, sent to the plan "
        "author. `product-test`: an assertion, fixture or fix in product code or a "
        "committed test the plan only cites, sent to the fix loop, which edits the code. "
        "`stack`: the book's `runbook` node and the flow's stack step — a service, emulator, "
        "database, seed or aggregate command that must be up before the plan runs. Name it "
        "by where the repair lands, not by which gate found it: an evidence defect whose "
        "real repair is a test assertion filed as `plan` bills a replan that cannot write "
        "it, and the identical gap comes back on the next pass.",
    )
    #: `coverage` is the fail-closed default and the only blocking kind; the post-run gates
    #: report it and `_finding_line` renders it.
    kind: Literal["coverage", "overclaim", "cosmetic"] = Field(
        default="coverage",
        description="What breaks if the plan ships as it stands. `coverage`: an AC or OKF "
        "obligation has no cited evidence that would catch it failing — the only kind that "
        "refuses a plan. `overclaim`: a checkpoint asserts more than its cited test proves; "
        "execution is unaffected, but the audit reads the plan's claims. `cosmetic`: counts, "
        "wording, ordering, which no gate and no runner reads.",
    )


class QaAssessment(CoderResult):
    """`qa-story.md` — what the runner's raw verdict actually means for this story.

    Four dispositions (`confirmed`, `repair_plan`, `extend_plan`, `repair_setup`) crossed with
    a `failure_class` and an `objective_reached` flag; the flow reads all three in sequence,
    which is what the YAML's four chained branch nodes did.

    `findings` is the finer grain under that classification: the disposition says the plan did
    not carry the story, and each finding says who repairs what. Without it every non-
    `confirmed` disposition billed the plan author, including the ones whose repair was an
    assertion in a committed test file. Empty by default, so a checkpoint written before this
    field existed resumes on the prose path.

    `status` carries the one answer no disposition spells: `blocked`, for a turn that could
    not judge the run at all. It is separate because every `disposition` value classifies a
    run this turn *did* read, and each routes the story to a budget that is then spent on it.
    `assessed` is the other arm — the turn reached a reading, and the three fields below are
    it. They are `None` on a `blocked` turn and never read there, because the flow answers a
    refusal before it reads any of them; what none of them has is a *classification* default,
    since the arms a silent reply used to take (`repair_plan`, `plan`, an unreached objective)
    each spent a real repair budget on a judgement nobody made.
    """

    status: Literal["assessed", "blocked"] = Field(
        description="`assessed` when you reached a reading of the run — the three fields "
        "below are then that reading. `blocked` when you could not judge the run at all.",
    )
    disposition: QaDisposition | None = Field(
        default=None,
        description="What the run means for the story. `confirmed` carries it; each of the "
        "others says the plan did not, and names which lane repairs it.",
    )
    failure_class: QaFailureClass | None = Field(
        default=None, description="What the remaining failure needs, on a non-confirmed run."
    )
    objective_reached: bool | None = Field(
        default=None,
        description="Whether every objective the story set was observed, as a person using "
        "the running app would observe it.",
    )
    findings: list[QaFinding] = Field(
        default=[],
        description="A `confirmed` disposition returns an empty list. Any other must carry "
        "at least one finding: the disposition says the run did not carry the story, and "
        "the findings say who repairs what. This is what the repair is briefed from.",
    )
    notes: str = Field(
        default="QA run assessment produced no valid result.",
        description="A summary of the findings — routing and diagnosis, never a replacement "
        "QA verdict.",
    )


class QaAudit(CoderResult):
    """`audit-qa.md` — an adversarial second read of a pass that already cleared the gate.

    `verdict` is `stands` or `refuted`, and `refutation_class` narrows a refutation to a
    product contradiction (the story is wrong), a plan defect or an evidence defect. Neither
    has a classification default: both are `None` on the `blocked` turn that named no verdict
    — and unread there — where the arms a blank used to take (`refuted`/`plan-defect`) spent a
    plan rework on a refutation nobody wrote.

    `findings` names who repairs each gap the auditor found. `refutation_class` is the coarse
    classification and routes the product case on its own; the findings are what keep an
    evidence defect whose repair is a test assertion from being billed to the plan author,
    who cannot write it. Empty by default, so an older checkpoint resumes on the prose path.

    `status` is the auditor saying it could not audit — distinct from `refuted`, which is a
    verdict about the evidence rather than an admission there was none to judge.
    """

    status: Literal["audited", "blocked"] = Field(
        description="`audited` when you reached a verdict on the evidence. `blocked` when "
        "there was none to judge — which is not the same as refuting it.",
    )
    verdict: QaAuditVerdict | None = Field(
        default=None, description="Whether the pass survives an adversarial second read."
    )
    refutation_class: QaRefutationClass | None = Field(
        default=None,
        description="`none` only when the pass stands cleanly; otherwise what the "
        "refutation is — a product contradiction, a plan defect, or an evidence defect — "
        "with concrete scenario, assertion, obligation and artifact references.",
    )
    findings: list[QaFinding] = Field(
        default=[],
        description="A refutation — and a `stands` that still names a refutation class — "
        "carries at least one finding; a pass that stands cleanly returns an empty list. "
        "This is what the repair is briefed from.",
    )
    notes: str = Field(
        default="Independent QA audit produced no valid result.",
        description="A summary of the findings, in one or two sentences.",
    )


class QaTriage(CoderResult):
    """`triage-qa.md` — are the findings in-AC fixes, or a scope the author must re-derive?

    The YAML declared these as two bare scalar outputs rather than one object; here they are
    two fields of one model, which produces the same two keys. Neither carries a classification
    default: the two safe arms it used to take (`qa_fix`, `code`) are judgements, and taking
    one on a turn that could not read the findings bills a loop for a decision nobody made.
    They are `None` on that turn instead, and the flow answers its refusal before reading
    either.

    `status` is the triager refusing to sort at all, which is what the vocabulary above
    cannot spell, and `triaged` is the turn that did.
    """

    status: Literal["triaged", "blocked"] = Field(
        description="`triaged` when you sorted the findings. `blocked` when you could not "
        "sort them at all."
    )
    triage_action: QaTriageAction | None = Field(
        default=None,
        description="`rescope` only if you amended the acceptance criteria and have rescope "
        "budget left; otherwise `qa_fix`, which is also the answer when every finding is "
        "purely in-AC.",
    )
    qa_failure_class: QaTriageClass | None = Field(
        default=None,
        description="What the remaining failure needs. `code`: a QA-side code or test change "
        "to satisfy an AC — the scenario, its fixtures, or a driver the QA lane owns. "
        "`product`: the product itself does not meet an AC that stands, which returns the "
        "story to the dev lane rather than patching it from inside QA. `evidence`: the "
        "product code is already correct and every gate is green, and what remains is only "
        "evidence work — capturing or refreshing screenshots, widening sweep coverage, "
        "re-running a driver to completion, fixing an artifact's shape. Be strict: if any "
        "finding needs a code change the class is `code`. `environment`: the stack, fixtures "
        "or emulator must be repaired or seeded before any verdict is possible. The flow "
        "grants one extra verification-only pass when an exhausted budget leaves only "
        "`evidence` work, so classify honestly: a wrong `evidence` wastes that pass, and "
        "a wrong `code` sends a finished story to manual review.",
    )
    #: Only read on a refusal, and that is why it exists at all: a triage that sorted the
    #: findings said everything it had to say in the two fields above, but one that could
    #: not sort them has said nothing anywhere else — and the escalation it raises would
    #: otherwise reach the operator as "the QA triage reported it cannot proceed", with no
    #: sentence naming what stopped it.
    notes: str = Field(
        default="",
        description="Read on a refusal: what stopped you from sorting the findings. A "
        "triage that reached a verdict has said everything it needs to in the fields above.",
    )


class QaReport(CoderResult):
    """`report-qa-dev(-pass).md` — the findings written out to the tracker, in `dev` runs.

    One model for both prompts: they emit the same key and differ only in whether the story
    passed. Nothing branches on it — the report is the terminal act of a `dev` run — but
    `blocked` is still worth saying rather than reporting a comment that was never written,
    because the run record is the only place that absence would otherwise show up.
    """

    status: Literal["reported", "blocked"] = Field(
        description="`reported` once the comment file exists. `blocked` in the one case "
        "where it cannot: the evidence you were pointed at is not there to read, or the "
        "output path cannot be written. Never invent the comment's content from the story "
        "alone — a tracker comment describing a QA run nobody performed is worse than no "
        "comment, because it is read as a record.",
    )
    notes: str = Field(
        default="",
        description="The output path, and what the comment says. On `blocked`, what was "
        "missing.",
    )


class RegressionFix(CoderResult):
    """`fix-regression.md` — the attempt to make the committed journey suites green again.

    A claim of success is still not read: the suite is simply re-run, and
    `run_regression_suite` is the only thing that decides whether the fix worked. `status`
    exists for the opposite claim — a fixer saying it *cannot* get there, which the re-run
    can only translate into another red suite and another identical lap. So `attempted` is
    not a claim of success: it is the turn saying it did work and the suite may judge it.
    """

    status: Literal["attempted", "blocked"] = Field(
        description="`attempted` on any turn that did the work, whatever you think it "
        "achieved — the next suite run judges that, not this field. `blocked` only when "
        "nothing in this repository would let you attempt the fixes at all, because what is "
        "missing is external to it: a credential or deployment you cannot perform, a product "
        "decision present in neither the story nor the plan, or work in another repo. A fix "
        "you doubt is still `attempted`.",
    )
    notes: str = Field(
        default="",
        description="Per failure — and every failure, not just the first: what was wrong, "
        "what you changed in app code or spec, and how you verified it locally. Name any "
        "failure you could not fix and why. On `blocked`, the specific dependency and what "
        "you attempted before concluding it.",
    )


class SetupResult(CoderResult):
    """`setup-fix.md` — the repair attempt on a stack manifest that would not come up.

    `unfixable` escalates to the operator gate, and it was the YAML's default for a bounded
    loop's sake: a fixer that said nothing must not be read as "ready" and sent back to
    `ensure_stack` to fail again. It is a required arm now instead, which answers the same
    worry earlier — an unparsed reply buys a retry turn rather than ending the repair loop on
    a verdict the fixer never gave.
    """

    status: Literal["ready", "unfixable"] = Field(
        description="`ready` when the environment is QA-capable now — services up and "
        "verified, tools installed — and also when you conclude the blocker is not an "
        "environment problem at all (the feature is genuinely broken or missing), so QA "
        "re-runs and routes it to the code-fix loop. `unfixable` only for a true wall that "
        "needs a human: a real credential or secret that cannot be generated locally, a "
        "deployed or preview environment, or hardware. Prefer `ready` whenever you made the "
        "stack runnable.",
    )
    notes: str = Field(
        default="",
        description="What was blocking QA, what you changed or started to fix it, and the "
        "readiness proof — or, when unfixable, exactly which human-only resource is needed.",
    )


# ── what the flow threads, and what it returns ────────────────────────────────────────


class AssessmentRecord(CoderResult):
    """What the loop remembers of the last execution-assessment turn.

    Three fields that are one statement in two forms — the diagnostics the next `plan_qa`
    turn is briefed from, and the same reading as the two closed vocabularies a span
    dimension can hold — so they are written together, cleared together, and read together.
    Flat on the loop they were three names a caller had to keep in step by hand, and a
    `cleared()` that blanked the notes and left the disposition behind would have let a span
    claim `repair_plan` for a finding already forgotten.

    **Nothing branches on the verdicts.** Each gate branches on its own fresh result; a
    stale disposition deciding a later transition is the bug `qa.flow._finding` describes.
    They are recorded because the counters alone are a cost and not a diagnosis: "four
    plan-QA attempts" says a story was expensive, "four attempts, every one ending
    `repair_plan`" says which gate made it so.

    Blank means the gate has not run yet, which is distinct from a gate that ran and found
    nothing wrong.
    """

    #: What the turn found, kept only when it failed — see `qa.flow._finding`.
    notes: str = ""
    disposition: QaDisposition | Literal[""] = ""
    failure_class: QaFailureClass | Literal[""] = ""

    def dimensions(self) -> dict[str, str]:
        """The two verdicts under the flat names the telemetry store classifies by suffix.

        `groom`'s profiler decides a span attribute is a verdict dimension by its suffix
        (`_disposition`, `_failure_class`), so grouping these onto a sub-model must not
        rename them on the way out — `qa.assessment.disposition` ends in neither and would
        be silently classified as nothing.
        """
        return {
            "assessment_disposition": self.disposition,
            "assessment_failure_class": self.failure_class,
        }


class AuditRecord(CoderResult):
    """The same three fields for the independent audit — see `AssessmentRecord`."""

    notes: str = ""
    verdict: QaAuditVerdict | Literal[""] = ""
    refutation_class: QaRefutationClass | Literal[""] = ""

    def dimensions(self) -> dict[str, str]:
        """The audit's two verdicts under their flat, suffix-classified names."""
        return {
            "audit_verdict": self.verdict,
            "audit_refutation_class": self.refutation_class,
        }


class FixWorklist(CoderResult):
    """The per-scenario fix worklist, and where in it the flow is.

    `apply_fixes` seeds `items` from `qa.flow._failed_scenarios` and `fix_item` pops the head
    as each one is proved green, so a checkpoint taken mid-worklist resumes at the item that
    was in flight rather than at the whole batch again. Empty `items` means there is no
    per-scenario pass running.

    The split is the point: a whole-report fix turn re-reads every finding on every lap and
    proves nothing until a full scored suite run at the end, so one wrong guess costs a
    rerun of everything. One scenario, dry-run green before the next one starts, costs one
    scenario.

    The two counters belong to the *head*, which is why they travel with it: every pop
    reseats all three at once, and three flat fields let a pop reset two of them and carry
    the third onto an item that never earned it.
    """

    items: tuple[str, ...] = ()
    #: How many turns the head has already had. Zero on each pop, because the budget is per
    #: item — a worklist of six scenarios is not six times harder than one, and a shared
    #: counter would starve whatever came last.
    rework: int = 0
    #: The dry-run refusals the head has already produced, in order. A second *identical*
    #: refusal is the same signal `QaLoop.repaired_failures` carries one loop out: the fixer
    #: ran, and the gate refused it for exactly the same reason, so the next lap has no new
    #: information to work from and the item escalates instead.
    problems: tuple[str, ...] = ()

    def popped(self) -> FixWorklist:
        """The worklist with the head proved green — the rest of it, on a clean slate."""
        return FixWorklist(items=self.items[1:])


class LaneClock(CoderResult):
    """What this lane has spent: wall-clock seconds, and how long the current chain is.

    `qa.flow.QA_LANE_BUDGET_S` and `PLAN_LANE_BUDGET_S` are the advisory numbers the two
    clocks are reported against — they are logged when crossed and decide nothing.

    **Accumulated as deltas, never derived from a start timestamp.** A lane that stored when
    it began and subtracted `now` would come back from a resume — or from a run parked
    overnight at the operator gate — already over budget, and would report an hour of effort
    it never spent. What is being measured is effort, and a charged delta is the only form
    of it that survives a checkpoint honestly.

    Deliberately not blanked by `QaLoop.cleared()`, unlike the gate diagnostics: a re-planned
    story has no findings against it yet, but the hour it already spent is still gone.
    `ensure_stack` is charged to neither clock — it is `INFRA_NODES` and can legitimately
    wait forty minutes for a stack to boot, which is not effort this flow can spend less of.
    """

    #: Seconds spent inside agent turns, and how much of that the plan lane (`plan`,
    #: `repair_plan`) took. The plan lane is a slice of the lane, not a sibling of it.
    seconds: float = 0.0
    plan_seconds: float = 0.0

    #: Consecutive repair laps that have run on the story's QA-plan session chain, so
    #: `repair_plan` can end a conversation that has grown longer than it is worth. Reset to
    #: 0 whenever the chain is, which is what makes it *consecutive* rather than a total —
    #: every rejoin through `build_context` ends the chain, because the diff the plan answers
    #: has changed. It lives on the loop because it must survive a resume: a counter kept
    #: anywhere else would restart at 0 mid-loop and give a stale chain a fresh budget.
    chain_laps: int = 0

    #: How many plan-lane turns were cut at their wall-clock cap. The flow keeps what such a
    #: turn wrote and validates it, which is the right call on a file that is the deliverable
    #: — but a turn that overruns is the loudest fact about a story's cost, and validating its
    #: half-written plan is indistinguishable from validating a finished one once the log has
    #: scrolled. Counted here so a checkpoint and a span say whether the lane was cut once or
    #: is being cut every lap. Nothing branches on it; the lap ceilings bound the loop.
    overruns: int = 0

    def charged(self, seconds: float, *, plan: bool, overran: bool = False) -> LaneClock:
        """The same clock with one turn's wall-clock added to the lane it was spent in."""
        return self.model_copy(
            update={
                "seconds": self.seconds + seconds,
                "plan_seconds": self.plan_seconds + (seconds if plan else 0.0),
                "overruns": self.overruns + (1 if overran else 0),
            }
        )


class QaLoop(CoderResult):
    """Everything the QA flow carries from gate to gate — one state parameter, not eighteen.

    The YAML kept all of this in flow vars: the running `qa_result`, five rework counters, the
    parent-owned rescope budget, three string flags used as booleans, the triager's failure
    class, and the six gate diagnostics `plan_qa` renders into its next brief. A driver state
    has parameters instead, and QA's graph is dense enough that threading eighteen of them
    through twenty-five states would be the whole file. So they travel as one model, which is
    legal without any driver change — a pydantic model round-trips through a checkpoint, as
    `author` settled — and a resume rebuilds the loop exactly.

    The three `"yes"`/`"no"` flags are real booleans here. They were compared against string
    literals in branch tables and never rendered into a prompt, so nothing observes the
    spelling.

    The diagnostics are what makes the loop converge: each failed gate hands the next
    `plan_qa` turn what it found, which is why `cleared()` exists — see the flow.
    """

    #: The story's running verdict, as whichever gate last wrote it left it.
    qa: QaResult = QaResult()

    #: `validate_qa_okf_context`'s verdict on the obligation packet, and its reasons. These
    #: two deliberately survive `cleared()`: `clear-qa-gate-state.py` never blanked them.
    context_status: Literal["", "passed", "invalid"] = ""
    context_notes: str = ""

    #: The first of the three gate diagnostics `clear-qa-gate-state.py` blanked before each
    #: plan turn; the other two travel on the records below.
    plan_validation_notes: str = ""

    #: What the last execution-assessment and independent-audit turns found, each with the
    #: verdicts that summarise it. See `AssessmentRecord`.
    assessment: AssessmentRecord = AssessmentRecord()
    audit: AuditRecord = AuditRecord()

    #: The triager's class, which is what the one-shot bonus pass is granted on. Blank until
    #: a triage turn runs — the YAML never declared this var, so an untriaged loop reads it
    #: as unset and earns no bonus.
    failure_class: QaTriageClass | Literal[""] = ""

    #: The bounded budgets. Each was a `{value: 0}` var with a `seed`/`incr` node pair, except
    #: `plan_validation_rework` — see the flow's `_guard_plan_validation`.
    context_rework: int = 0
    plan_rework: int = 0
    plan_validation_rework: int = 0
    qa_rework: int = 0
    setup_rework: int = 0
    regression_fix: int = 0
    #: How many times the audit has refuted a pass with findings only the plan author can
    #: close. Not a spend counter like the rest — nothing is charged to it and no repair is
    #: skipped because of it. It exists because the audit is the *last* gate, so a fresh
    #: plan finding it raises on its third pass has nothing downstream to catch what it
    #: waives; see `qa.flow.MAX_BLOCKING_AUDITS`.
    audit_rework: int = 0

    #: The runtime requirements the *latest* blocked QA run named, sorted — the runner's own
    #: `problems` list, which is a machine-readable statement of what was missing rather than
    #: the prose the fixer is briefed with. Written only by `run` (and blanked by it on any
    #: other status), so it always describes the run the flow is currently reacting to.
    blocked_problems: tuple[str, ...] = ()

    #: The same list as the last `setup_fix` turn was asked to repair. The pair is a
    #: repeat detector: a fixer that ran and left the runner naming exactly what it named
    #: before has demonstrated it cannot fix this from inside the run, and a live story spent
    #: three `power="high"` 40-minute laps installing Playwright, proving the install worked,
    #: and getting the identical bundle back — because the copy it repaired was not the
    #: interpreter the QA stage imports ostler into. Neither budget catches that: every lap
    #: is legal, and the flow only stops once `MAX_SETUP_REWORKS` is gone. So the *sameness*
    #: is the signal, and it goes to the operator rather than round again.
    setup_problems: tuple[str, ...] = ()

    #: The per-scenario fix pass, when one is running. See `FixWorklist`.
    fix: FixWorklist = FixWorklist()

    #: The rejections the *plan lane* has already been sent back on, in order — one entry
    #: per pre-run refusal, carrying which gate raised it and what it said.
    #:
    #: `repaired_failures` is the same signal for the post-run half, and it cannot serve this
    #: one: it fingerprints a *suite run*, and no run happens between a repair and the schema
    #: or dry-run refusal that sends it round again. So those laps had a count bounding them
    #: and nothing else, and a plan repair that answered a refusal with the identical file
    #: could spend the whole budget re-earning the identical refusal — the observed 33-lap
    #: `repair-qa-plan` story is mostly that.
    #:
    #: A second *identical* entry is a repair turn that ran with the gate's reason in hand and
    #: produced nothing the gate reads differently, which is no new information to work from.
    #: It goes to the operator gate rather than round again — an `Await`, never an end: the
    #: operator can always send it back, and the worklist is on the loop so a resume continues.
    #:
    #: Not blanked by `cleared()` — every plan lap clears the gate notes on its way in, so a
    #: field that cleared with them could never hold two laps at once. Zeroed at the
    #: `build_context` rejoin instead, where the diff the plan answers has changed and a
    #: rejection of the old plan says nothing about the new one.
    plan_rejections: tuple[str, ...] = ()
    #: The same fingerprint as the last repair lap — a code fix or a plan repair — was
    #: dispatched against.
    #:
    #: `setup_problems` is the same idea one loop over, and for the same reason: a repair
    #: that ran and left the runner failing at *exactly* the same assertions, the same number
    #: of steps in, has demonstrated that whatever is wrong is not reachable from where it is
    #: repairing. No budget catches that — every lap is legal, so the flow only stops once
    #: `MAX_QA_REWORKS` or `MAX_PLAN_REWORKS` is gone, and each of those laps is a `power`
    #: agent turn plus a full re-run of the suite. A live story burned repairs two through
    #: four that way against a failure that reproduced only under the QA runner's own driver
    #: and never under a second one, which is not a defect any in-repo fix can reach.
    #:
    #: So the *sameness* is the signal, and it goes to the operator rather than round again.
    #: The counts are part of the fingerprint deliberately: a repair that gets the scenario
    #: three steps further before failing has moved, and has earned its next lap.
    repaired_failures: tuple[str, ...] = ()
    #: Which repair loop stamped `repaired_failures` — `"code fix"` or `"QA-plan repair"`.
    #:
    #: The two loops share one fingerprint field but are not one loop, and without this the
    #: sameness test reads across them. A plan repair stamps the fingerprint; the repaired
    #: plan is reviewed, approved, and its findings routed to the *fix* loop — all without a
    #: second run, because a plan repair does not re-run the suite. The fix loop's first
    #: visit then compares the untouched fingerprint against itself and reports "the last
    #: code fix left the QA run failing identically" about a code fix that never happened.
    #: A live story escalated to the operator that way with zero code laps spent.
    repaired_lap: str = ""
    #: Every repair class this story has actually dispatched a lap against — the values
    #: `repaired_lap` has taken, unioned.
    #:
    #: `repaired_lap` names the *latest* one and so cannot answer "has the other hypothesis
    #: ever been tried", which is the question a stall has to ask before ending the story.
    tried_laps: tuple[str, ...] = ()
    #: Whether this story has already taken the one hypothesis-class switch it is allowed.
    #:
    #: A repair that moved nothing refutes the *hypothesis*, not the story: "the plan repair
    #: changed nothing" is evidence the failure is not in the plan, which argues for trying
    #: the product rather than for giving up. A live story was abandoned on exactly that
    #: inference having never spent a code lap, and the five assertions it died on were races
    #: in the plan. So the first stall switches class instead of escalating.
    #:
    #: The whole termination argument rests on this being monotone and written in exactly one
    #: place (`Qa._switched`): one switch per story, only toward a class that has never run,
    #: and the second stall — whichever class raises it — falls through to the operator gate
    #: as before.
    class_switched: bool = False

    #: How many times this story has been handed to the operator gate, counting the one it
    #: is being handed to now. `dev` and `review` already keep this as `plan_blocks` /
    #: `review_blocks`; QA had no equivalent because nothing branched on it, and nothing
    #: branches on it here either — it is what the escalation body puts at the top so a
    #: reader can tell "this story blocked once" from "this story has blocked three times
    #: and each answer bounced". Deliberately not a budget: see `coder.shared.escalation`.
    escalations: int = 0

    #: The parent-owned rescope budget, threaded in and crossed back out on a rescope.
    triage_scope: int = 0

    #: Regression bookkeeping: a fix was applied since the last primary QA, and primary QA
    #: owes a re-run because of it.
    regression_fix_applied: bool = False
    regression_reqa_pending: bool = False

    #: Whether the one verification-only bonus pass past `MAX_QA_REWORKS` has been spent.
    bonus_used: bool = False

    #: A post-documentation mutation may have changed the as-built truth. True is the
    #: fail-closed default for checkpoints written before this field existed; `Qa.start`
    #: explicitly establishes False for a fresh, known-clean QA pass.
    docs_recheck_required: bool = True

    #: What this lane has spent, and how long its current QA-plan session chain is.
    #: See `LaneClock`.
    clock: LaneClock = LaneClock()

    @property
    def plan_rework_total(self) -> int:
        """Repairs spent across validation, review, and post-run plan gates.

        Derived from the durable stage counters so old checkpoints retain what they
        already spent and no duplicated total can drift from its components.

        This is the flow's *outermost* plan ceiling (`Qa.MAX_TOTAL_PLAN_LAPS`), and the only
        thing that reads it. It does not replace the per-stage budgets and is not a smaller
        version of them — see `plan_judgement_rework` for why one shared ceiling of four was
        the wrong shape. What it bounds is their **product**: the stage budgets are checked
        independently, so a story could legally spend three schema repairs, four judgement
        repairs and keep alternating between the two, which is how `plan-qa` reached thirteen
        laps when no single budget permits more than four.
        """
        return self.plan_rework + self.plan_validation_rework

    @property
    def plan_judgement_rework(self) -> int:
        """Repairs spent on the two gates that exercise *judgement* about the plan.

        `validate_qa_plan` is a schema check: `ostler qa validate` imports `qa_plan.py`
        and says whether it is well-formed. Failing it means the plan turn mistyped a
        field — cheap to fix, deterministic, and worth nothing as evidence about whether
        the plan tests the story. The post-run plan gates are the opposite: an agent judging
        coverage against evidence that exists, which is the work the budget exists to bound.

        They shared one ceiling of four until a story spent three repairs on schema typos
        and reached the judging gate with a single revision left, then gave up "after 4 total
        QA-plan repair" — a give-up a human reads as an intractable plan when the plan had
        in fact been read critically exactly once. Mechanical failures now spend their own
        budget (`MAX_PLAN_VALIDATION_REWORKS`) and cannot starve this one.
        """
        return self.plan_rework

    def update(self, **changes: object) -> QaLoop:
        """The same loop with some fields replaced — the port of an `incr`/`emit-kv` node."""
        return self.model_copy(update=changes)

    def with_qa(self, qa: QaResult) -> QaLoop:
        """The same loop carrying a new running verdict."""
        return self.model_copy(update={"qa": qa})

    def with_lap(self, lap: str, **changes: object) -> QaLoop:
        """The same loop dispatching a repair lap of class `lap`, with the class remembered.

        `repaired_lap` is overwritten every lap, so on its own it cannot say whether the
        *other* hypothesis has ever been tried — which is what `Qa._switched` has to know
        before a stall is allowed to end the story. `tried_laps` is the union, and it is
        bounded at three entries by there being three classes.
        """
        return self.model_copy(
            update={
                **changes,
                "repaired_lap": lap,
                "tried_laps": self.tried_laps
                if lap in self.tried_laps
                else (*self.tried_laps, lap),
            }
        )

    def charged(self, seconds: float, *, plan: bool = False, overran: bool = False) -> QaLoop:
        """The same loop with one turn's wall-clock added to the lane it was spent in.

        `plan` charges the plan lane as well as the whole one — the plan lane is a slice of
        the lane, not a sibling of it, so a plan turn is spent twice over by design.
        `overran` records that this is one of the turns the cap cut short.
        """
        return self.model_copy(
            update={"clock": self.clock.charged(seconds, plan=plan, overran=overran)}
        )

    def require_docs_recheck(self) -> QaLoop:
        """Mark a possible as-built mutation; this taint is monotonic within the flow."""
        return self.model_copy(update={"docs_recheck_required": True})

    def cleared(self) -> QaLoop:
        """`clear-qa-gate-state.py`: forget every gate's findings before re-running them.

        The script replaced five keys wholesale, so the running verdict is blanked too — a
        re-planned story has not failed QA yet. The two *context* fields are not in that set
        and stay, which is the script's behaviour and not an oversight of the port.

        The recorded verdicts blank with the notes they summarise. They are the same
        statement in two forms, so leaving one behind would let a span claim `revise` for a
        gate whose finding had already been forgotten.
        """
        return self.model_copy(
            update={
                "qa": QaResult(),
                "plan_validation_notes": "",
                "assessment": AssessmentRecord(),
                "audit": AuditRecord(),
            }
        )

    @property
    def block_notes(self) -> str:
        """The composed brief the operator gate and the setup fixer are both handed.

        `"{{ qa_result.notes }} | Assessment: {{ qa_assessment.notes }}"`, rendered once here
        because four YAML nodes rendered it identically.
        """
        return f"{self.qa.notes} | Assessment: {self.assessment.notes}"


class QaFlowResult(CoderResult):
    """What the QA flow hands back — the YAML's five `qa_phase` output keys, as one value.

    `status` is the `qa_status` the four `emit-kv.py` terminals wrote (`passed`,
    `inconclusive`, `replan`, `rescope`), plus `refix` — a product-class failure handed back
    to the dev lane, which owns product code, rather than patched by a QA fixer briefed on a
    QA report. It differs from `rescope` in what moved: a `rescope` means triage amended the
    story's acceptance criteria, a `refix` means they stand and the product does not meet
    them. `inconclusive` is the default for the same reason
    the YAML's `qa_phase` output declared it: a flow that produced nothing has not passed.
    Every budget the flow can exhaust now routes to the operator gate instead — `Qa` never
    returns `inconclusive` on its own; only `target_env="dev"`'s `report_dev` does, because
    that mode does not own the code and reporting the findings *is* the terminal action.

    `triage_scope` crosses the flow boundary in both directions — the parent seeds it and
    reads the bumped value back — which is the one piece of state the isolated flow does not
    own.
    """

    status: QaFlowStatus = "inconclusive"
    qa: QaResult = QaResult()
    qa_rework: int = 0
    triage_scope: int = 0
    operator_notes: str = ""
    #: Whether the parent must document again before committing. Missing old results recheck.
    docs_recheck_required: bool = True


__all__ = [
    "BacklogDrain",
    "ContextRepair",
    "FailureAttribution",
    "QaAssessment",
    "QaAudit",
    "QaAuditVerdict",
    "QaCleared",
    "QaDisposition",
    "QaFailureClass",
    "QaFlowResult",
    "QaFlowStatus",
    "QaLoop",
    "QaPlanResult",
    "QaPlanRun",
    "QaPlanValidation",
    "QaRefutationClass",
    "QaReport",
    "QaResult",
    "QaRunResult",
    "QaStatus",
    "QaToolCatalog",
    "QaTriage",
    "QaTriageAction",
    "QaTriageClass",
    "RegressionFix",
    "RegressionRun",
    "RegressionSuite",
    "RegressionSuites",
    "ScreenshotFlush",
    "SetupResult",
    "StackStatus",
]
