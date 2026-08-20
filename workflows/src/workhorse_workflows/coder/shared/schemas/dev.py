"""The dev flow's models: plan, path validation, dispatch, implement, gate, fix.

Ported from `flows.dev`'s six agent turns and seven script nodes.

Three shapes are worth naming here, because each is a deliberate divergence recorded in the
progress ledger:

* **`dispatch_list` becomes typed.** `kit.build_dispatch_list` returns a list of dicts with
  eleven fixed keys, and the YAML threaded it as `current_layer.cwd`, `current_layer.type`
  and so on — a Jinja lookup that silently yields the empty string on a typo. `DispatchEntry`
  is those eleven keys, so a typo is an `AttributeError` at the site instead of an agent turn
  run with a blank cwd.
* **`qa_source_roots_json` becomes a `list[str]`.** It was a JSON-encoded *string* for the
  same reason `fix_ci`'s `processed_repos` was: a workflow var is a string. A state
  parameter is a value, so the encoding has no job left. Nothing on disk carried the encoded
  form — `ostler qa context` is handed the decoded arguments either way.
* **`PlanResult` carries the plan's structure.** It used to carry `{status, summary}` and
  nothing else, because the services lived in a `plan-context.json` the *agent* free-typed
  into the spec dir and Python then `load_json`ed in four places, rewrote in place, and
  re-handed to later turns as a path plus "read it". An agent authoring a machine-read file
  is what produced the "exists but has no `services` array" error path and its rework lap.
  The turn now returns the structure, the checkpoint validates it, and Python writes
  `plan-context.json` as a *projection* — one way, for readers outside the producing run
  (a later QA lane, `ostler artifact vet`, a human in the spec dir).

The tri-states stay strings for the reason `schemas/ci.py` gives at length: each has three
arms whose `default:` — the one a blank takes — is a *specific* one, and every branch below
names the arm a blank falls into.
"""
from __future__ import annotations

import hashlib
from typing import Any

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding


class PlanService(CoderResult):
    """One service the plan changes: where it lives, what it is, what to read, what to do.

    A shared package (a library the dependent service's pass implements) is the same shape
    with no `plan_file` — it is a directory the plan touches, and the only thing that
    distinguishes it is which list it is in.
    """

    #: Workspace repo name. Case is repaired against the workspace rather than rejected —
    #: the planner tends to emit the human-facing brand and the key is the folder name.
    repo: str = ""
    #: Path from the repo root to the service directory; `.` for a repo-root service.
    path: str = ""
    #: The technology key *this repo's* skills and prompts gate on, not a remembered
    #: taxonomy — it is read back out of the repo's own `agents.yml`.
    type: str = ""
    #: Instruction short-names the implementer must load for this service.
    skills: list[str] = []
    #: The per-service plan file, relative to the spec dir. Blank on a shared package.
    plan_file: str = ""
    #: The directory does not exist yet and implementation will scaffold it, so the path
    #: and marker checks are skipped for this entry.
    new_service: bool = False


class PlanResult(CoderResult):
    """`prompts/plan-story.md` and `prompts/refine-plan.md` — the plan, or the blocker.

    `status` is `done` or `blocked`. A blank takes the YAML's `default:` arm, which is
    `done` — the plan gate is deliberately permissive, because depth and correctness are
    enforced downstream by implementation review and by QA, not here.

    The structural fields are the ones the turn used to hand-write into `plan-context.json`;
    see this module's header for why they moved. A malformed one is now a parse retry
    against a pydantic model rather than a workflow state.
    """

    status: str = ""
    summary: str = ""

    #: Every service this story changes, one entry each. An empty list is a legitimate
    #: single-service story: the dispatcher falls back to a repo-root layer.
    services: list[PlanService] = []
    #: Build order as `repo::path` keys — whatever defines a contract before whatever
    #: implements it, and that before whatever consumes it.
    implementation_order: list[str] = []
    #: Non-service directories (libs, shared code) the plan changes.
    shared_packages: list[PlanService] = []
    #: The story's `## Verification setup`, machine-readable: `profile`, `fixtures`,
    #: `capable_of_rendering`. Free-form by design — QA renders it, nothing branches on it.
    qa_stack: dict[str, Any] = {}


class ExitConditions(CoderResult):
    """What a turn said "done" would look like, before it started doing it.

    Goal setting is only worth an agent's tokens if something checks the goal, and the
    cheapest place to check one is Python: a claim written down in a schema is falsifiable,
    where the same claim written into prose is a pep talk. So the envelope asks for this on
    the turns that decide something — plan and implement — and the deterministic gate after
    the turn compares the promise to the fact.

    Nothing here is required. A turn that promises nothing is not failed for it; it simply
    forfeits the check, and the declared gates still run. What is not allowed is promising a
    command that then fails, or a file that was never written — that is a `FailureReport`
    with `source: "goal"` into the same repair loop every other gate feeds.
    """

    #: The acceptance criteria this turn intends to satisfy, in the story's own words. Not
    #: checked mechanically — carried forward to review and QA as the thing to check first.
    criteria: list[str] = []
    #: The commands the turn expects to be green when it is finished. Run verbatim, in the
    #: service directory, minus any the declared gates have already run.
    commands: list[str] = []
    #: The files the turn expects to have touched, service-relative or repo-relative. Both
    #: are matched leniently against the diff: a false accusation costs a whole repair lap.
    files: list[str] = []


class ImplResult(CoderResult):
    """`prompts/implement-plan.md` — one service layer implemented, or the blocker.

    The optimistic half is still not branched on: the lint gate below and QA downstream
    decide whether the layer is done, and an agent claiming `done` is not evidence that it
    is. The *pessimistic* half is, and that asymmetry is the point — a turn reporting it
    could not implement the plan was discarded here for the whole of this workflow's life,
    and the layer went on to lint a change nobody had written.

    The three fields below are the same asymmetry applied to the optimistic half: rather
    than believe `done`, the lane checks the turn's own account of what done would mean.
    """

    status: str = ""
    notes: str = ""

    #: What this turn promised before it began. Checked by `check_promises` afterwards.
    exit_conditions: ExitConditions = ExitConditions()
    #: The test files this turn wrote or extended, service-relative. The `tdd` gate reads
    #: this against the diff; a repo that declares no `tdd:` key never asks for it.
    tests_added: list[str] = []
    #: Why there is no test, when there is none. An exemption is a claim the gate weighs
    #: against the service's declared type, not a flag that switches the gate off.
    no_test_reason: str = ""


class FailureReport(CoderResult):
    """A gate said no. Which gate, what it ran, what it printed — one shape for all of them.

    This is the argument for there being *one* repair role. Lint, verification and
    regression each produced their own result schema, their own prompt and their own budget,
    and the three differed in nothing a fixer acts on: a command, its output, and which lap
    this is. `source` is the only thing that varies, and it varies by a word.

    It is built in Python from whatever the gate returned (`shared.failure`), never asked of
    an agent — the gate's output is evidence, and evidence a turn paraphrased is no longer
    evidence.
    """

    #: Which gate failed: `lint`, `verify`, `regression`, `tdd`. Named rather than typed as
    #: an enum because a repo's `agents.yml` may declare gates this package has never heard
    #: of, and an unknown source is still a command with output — the generic arm handles it.
    source: str = ""
    #: The command the gate ran, verbatim, so the fixer re-runs the same thing rather than
    #: guessing at one.
    command: str = ""
    #: Where it ran. A repair turn that fixes the right file in the wrong service passes
    #: nothing.
    cwd: str = ""
    #: What the gate printed, truncated by whoever captured it.
    output: str = ""
    #: Structured findings, when the source has them (a review or QA hand-off does; a lint
    #: command's stdout does not). Typed as `Finding` so `CoderResult.actionable` applies.
    findings: list[Finding] = []
    #: Which repair lap this is, 1-based. Carried so the prompt can say it and so the log
    #: reads as a sequence rather than as a repetition.
    lap: int = 0

    @property
    def digest(self) -> str:
        """A stable fingerprint of *this failure*, for detecting a stalled loop.

        Two consecutive laps with the same digest mean the repair changed nothing the gate
        can see, and the ladder answers that by spending power rather than another identical
        turn. Whitespace is collapsed and the lap number is excluded on purpose: the lap is
        the one field guaranteed to differ between two otherwise identical failures.
        """
        material = "\n".join(
            (self.source, self.command, " ".join(self.output.split()))
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


class FixResult(CoderResult):
    """`prompts/dev-fix.md` — the repair turn's own report, whatever the gate was.

    `fixed` and `failed` are not branched on; re-running the gate is what decides, and an
    agent's claim to have fixed something is not evidence that the gate agrees. `blocked` is
    branched on, and only to stop the laps — re-asking a turn that has just said it cannot
    buys a budget and no repair.
    """

    status: str = ""
    notes: str = ""

    #: Test files this repair wrote or extended, service-relative. The `tdd` gate re-runs
    #: after the lap against the implement turn's report, which a repair turn cannot amend;
    #: without this, a lap that adds the missing test still comes back failing the gate it
    #: just satisfied. The flow merges these into the promise it re-checks.
    tests_added: list[str] = []

    #: Promised files this lap withdraws, having found the change genuinely unnecessary —
    #: a generated file whose regeneration is a no-op, a path the plan turned out not to
    #: need. The `goal` gate offers exactly two ways out ("make the change, or say why it
    #: turned out to be unnecessary") and this is the second one: without it the second
    #: half of that sentence is a lie, the gate is satisfiable only by an edit nobody
    #: wants, and a correct turn laps until it escalates to a human who can only agree.
    #: The reason belongs in `notes`, which is what the run log keeps.
    retracted_files: list[str] = []


class OperatorResolution(CoderResult):
    """`prompts/resolve-operator.md` — the resolver's report on a block.

    Note the field is `summary` here and `notes` in `author`'s copy of this model: the
    two prompts genuinely ask for different key names, and the port follows each prompt
    rather than unifying a name the model would then not emit.
    """

    #: `answered` or `escalated`, and the only field a flow branches on. It stopped being
    #: a relic when the resolver was allowed to settle a block it could ground: `answered`
    #: means the answer is already written into `context.md` and the flow continues
    #: straight to its consume state, anything else means the flow parks for a human.
    #: Defaulted to `""` — an unparseable or truncated turn escalates, which is the arm
    #: that costs a round trip rather than the one that acts.
    decision: str = ""

    summary: str = ""

    #: One line per source that determined an `answered` decision — the file, and the rule
    #: quoted from it. It is what makes an auto-resolution auditable: the operator reading
    #: the log checks the citation rather than redoing the investigation. Empty on an
    #: escalation, and empty on an `answered` turn is the resolver failing its own contract.
    grounded: list[str] = []

    #: The `docs/decisions/` slug the resolver wrote or cited — see `shared.paths.decisions_dir`.
    #: Carried for the log, not branched on.
    record: str = ""

    #: What the resolver attempted and ruled out, one line each. It is the diagnosis so
    #: far, and without it the human who arrives at the gate re-runs every dead end the
    #: resolver already paid for. Defaulted and never required: an older transcript parses
    #: with it absent.
    tried: list[str] = []


class OperatorGate(CoderResult):
    """The escalation body a flow hands to `Await` — see `coder.shared.escalation`.

    `body` is a whole context file, `STATUS:` line included, so `gates.format_operator_gate`
    passes it through untouched rather than wrapping it. `number` is the escalation's
    ordinal for this story, carried out so a caller can log it without re-deriving it.
    """

    body: str = ""
    number: int = 0


class OperatorAnswer(CoderResult):
    """What `<story-folder>/context.md` said once the operator (or the resolver) answered.

    The consume half of `scripts/await_operator.py`, which is the only half that gets
    ported: the 280 lines of ctypes inotify that made up the *wait* half are replaced by the
    driver's `Await`. `scope` is `epic` or `story`, read from the file's `SCOPE:` line, and
    only `epic` is honoured — anything else, blank included, is `story`.
    """

    answered: bool = False
    scope: str = "story"
    content: str = ""


class PlanValidation(CoderResult):
    """`record_plan` — the projection Python wrote, and whether it points at real services.

    `status` is `valid` or `invalid`, and a blank takes `valid`: the YAML's `default:` arm
    routed on to implementation, because a validator that cannot speak is not evidence of a
    bad plan. `errors` is what the refiner is handed as its brief.

    `document` is the projected plan itself — the same mapping written to `plan-context.json`
    — so the states downstream of the gate hand the *value* to the dispatch nodes instead of
    naming the file back at them. It is the producing run's copy; a lane that did not produce
    it (QA on a later run, the fix lane) passes nothing and reads the projection off disk.
    """

    status: str = ""
    errors: list[str] = []
    document: dict[str, Any] = {}


class DispatchEntry(CoderResult):
    """One service to implement: where it lives, what type it is, how to verify it.

    The eleven keys `kit.build_dispatch_list` emits, typed. `service` is the `repo::path`
    form the plan's `implementation_order` and every log line use; `label` is the *display*
    name — the repo template's `backend_layer_name`/`mobile_layer_name` when it has one, and
    the service type otherwise. The two are easy to read the wrong way round, and reading
    them the wrong way round produces a `run_gate` keyed on a display name.
    """

    service: str = ""
    repo: str = ""
    cwd: str = ""
    service_path: str = ""
    type: str = ""
    plan_file: str = ""
    skills: list[str] = []
    qa_mode: str = ""
    qa_skills: list[str] = []
    verification: str = ""
    label: str = ""


class QaRunEntry(CoderResult):
    """One service's QA brief, derived from its dispatch entry.

    Built here rather than in `qa` because the plan is what names the skills, and
    `-local` skills are dropped at this point when the run is not targeting `local`.
    """

    service: str = ""
    label: str = ""
    qa_mode: str = ""
    qa_skill: str = ""
    qa_skills: list[str] = []


class PlanSummary(CoderResult):
    """The plan's structure as prose, for a turn in a lane that did not produce it.

    `text` is rendered by Python from the projection, and it is what the review, QA, fix and
    docs prompts are handed instead of the name of a file to go and parse. A turn told to
    read a path spends a tool call, may not spend it, and may read a different copy than the
    workflow decided on; a turn handed the content reads what the workflow decided on.

    Blank when there is no projection to read — the prompts fall back to the plan artifacts,
    which is where a single-service story's scope was legible anyway.
    """

    text: str = ""


class ImplContext(CoderResult):
    """`resolve-impl-context.py` — the approved plan decoded against the workspace.

    Deterministic and side-effect-free, and deliberately degrading: a missing or garbled
    plan-context yields empty lists rather than a failure, so the implementer falls back to
    reading the plan text. `qa_stack` is copied verbatim from the plan and stays untyped —
    it is the fixture/data description a QA turn is handed as prose. `shared_packages` is
    the same: the plan's list of files more than one service reads, which the QA planner
    needs because a fixture the dev lane already resolved is exactly what it should assert
    against rather than re-derive.
    """

    impl_instruction_paths: list[str] = []
    qa_run_plan: list[QaRunEntry] = []
    qa_stack: dict[str, Any] = {}
    shared_packages: list[str] = []
    dispatch_list: list[DispatchEntry] = []
    affected_repos: list[str] = []
    affected_repo_paths: list[str] = []
    qa_source_roots: list[str] = []

    @property
    def dispatch_count(self) -> int:
        """The YAML's `dispatch_count` output — `len(dispatch_list)` stringified.

        A property rather than a field: it was never anything but the length, and a stored
        copy is a second source of truth for a number the list already carries.
        """
        return len(self.dispatch_list)


class BranchOutcome(CoderResult):
    """`branch-code-repos.py` — which code repos moved onto the story branch.

    Idempotent: a repo already on the branch lands in `already_on_branch`, and one that is
    not a git repo at all is skipped and appears in neither list.
    """

    branched: list[str] = []
    already_on_branch: list[str] = []


class LayerPick(CoderResult):
    """`select-next-layer.py` — the next service to implement, or "the list is exhausted".

    `index` is the position just taken, which the next call needs; on exhaustion it is left
    where it was, exactly as the script did.
    """

    has_layer: bool = False
    index: int = -1
    layer: DispatchEntry = DispatchEntry()
    dispatch_count: int = 0


class GateOutcome(CoderResult):
    """`run_gate` — one of a service's declared gate commands and what it said.

    `status` is `clean`, `dirty` or `skipped`, and a blank reads as "move on". `skipped` is
    the opt-out: a service adopts a gate by declaring its command in `agents.yml`, and one
    that has declared nothing is never falsely failed.

    `gate` is which gate this was — `lint`, `test`, whatever the repo declared — and it
    becomes the `FailureReport.source` the repair turn reads, which is what lets one repair
    role serve every gate and still say what broke.
    """

    gate: str = ""
    status: str = ""
    command: str = ""
    output: str = ""
    reason: str = ""


class GateList(CoderResult):
    """`declared_gates` — the commands that will run after the turn being briefed.

    Rendered into the implement turn so it knows what it is being checked against. The
    empty case is deliberately spoken aloud (`text` reads "(nothing declared)") rather than
    left blank: a repo with no gates is a real and legitimate state, and a turn told
    nothing would assume the usual ones exist.
    """

    gates: list[str] = []
    commands: list[str] = []
    text: str = ""
    #: What this service declares about tests — `required`, `encouraged` or `off`. Told to
    #: the turn for the same reason the commands are: it is the repo's rule, and a turn that
    #: is not told it either guesses or is failed by a gate it never heard of.
    tdd: str = "off"


class ChangedFiles(CoderResult):
    """What this story has already written into one service, by path.

    The re-seed a fresh conversation is handed when the story's own conversation is recycled
    at `max_session_turns`: the turn that opens next has none of the history, and the
    cheapest true thing to tell it is which files the work so far touched. Deliberately paths
    only — a diff would reintroduce, in one prompt, the context the recycling exists to drop.
    """

    paths: list[str] = []


class DevResult(CoderResult):
    """What the dev flow hands back: `ready`, or `replan` when the epic premise was wrong.

    The YAML's `dev_done` terminal declared no outputs and the parent read two flow-level
    vars off it — `dev_status` (defaulting to `ready`) and `operator_input`. Only the
    operator's answer text ever crossed back, so that is the second field here rather than
    the whole `OperatorAnswer`.
    """

    status: str = "ready"
    operator_notes: str = ""
    #: The CLI session id the story's backbone turns ended on — empty when none ran, or
    #: when a checkpoint predates this field. The parent threads it into `Review`'s
    #: successor stages so `Docs` and `Qa` resume the same conversation instead of
    #: reopening one. See `Dev._story_chain`.
    session_id: str = ""
    #: How many turns that conversation had already spent when the flow ended. The review
    #: lane's apply turns join the same conversation and keep counting from here, so the
    #: recycle threshold bounds the *conversation*, not each lane's share of it.
    session_turns: int = 0


__all__ = [
    "BranchOutcome",
    "ChangedFiles",
    "DevResult",
    "DispatchEntry",
    "ExitConditions",
    "FailureReport",
    "FixResult",
    "ImplContext",
    "ImplResult",
    "GateList",
    "GateOutcome",
    "LayerPick",
    "OperatorAnswer",
    "OperatorGate",
    "OperatorResolution",
    "PlanResult",
    "PlanValidation",
    "QaRunEntry",
]
