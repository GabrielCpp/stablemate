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
* **`PlanResult` has no `services` field.** Both prompts that produce a `plan_result` ask for
  one and they disagree about its shape: `plan-story.md` specifies a list of `"repo::path"`
  strings and `refine-plan.md` a list of `{repo, path, type}` objects. Nothing in the flow
  ever read it — `plan-context.json`, which the same turn writes, is what every downstream
  node decodes — so modelling it would mean picking a winner between two live formats for a
  field with no consumer. `CoderResult`'s `extra="ignore"` lets either arrive and be dropped.

The tri-states stay strings for the reason `schemas/ci.py` gives at length: each has three
arms whose `default:` — the one a blank takes — is a *specific* one, and every branch below
names the arm a blank falls into.
"""
from __future__ import annotations

import hashlib
from typing import Any

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding


class PlanResult(CoderResult):
    """`prompts/plan-story.md` and `prompts/refine-plan.md` — the plan, or the blocker.

    `status` is `done` or `blocked`. A blank takes the YAML's `default:` arm, which is
    `done` — the plan gate is deliberately permissive, because depth and correctness are
    enforced downstream by implementation review and by QA, not here.
    """

    status: str = ""
    summary: str = ""


class ImplResult(CoderResult):
    """`prompts/implement-plan.md` — one service layer implemented, or the blocker.

    The optimistic half is still not branched on: the lint gate below and QA downstream
    decide whether the layer is done, and an agent claiming `done` is not evidence that it
    is. The *pessimistic* half is, and that asymmetry is the point — a turn reporting it
    could not implement the plan was discarded here for the whole of this workflow's life,
    and the layer went on to lint a change nobody had written.
    """

    status: str = ""
    notes: str = ""


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
    """`validate-plan-context.py` — do the planner's service paths point at real services?

    `status` is `valid` or `invalid`, and a blank takes `valid`: the YAML's `default:` arm
    routed on to implementation, because a validator that cannot speak is not evidence of a
    bad plan. `errors` is what the refiner is handed as its brief.
    """

    status: str = ""
    errors: list[str] = []


class DispatchEntry(CoderResult):
    """One service to implement: where it lives, what type it is, how to verify it.

    The eleven keys `kit.build_dispatch_list` emits, typed. `service` is the `repo::path`
    form the plan's `implementation_order` and every log line use; `label` is the *display*
    name — the repo template's `backend_layer_name`/`mobile_layer_name` when it has one, and
    the service type otherwise. The two are easy to read the wrong way round, and reading
    them the wrong way round produces a `run_lint` keyed on a display name.
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


class LintOutcome(CoderResult):
    """`run-lint.py` — one service's lint command and what it said.

    `status` is `clean`, `dirty` or `skipped`, and a blank takes the YAML's `default:` arm,
    which is "move on to the next layer". `skipped` is the opt-out: a service adopts the
    gate by defining a `lint` make target or an `agents.yml` override, and one that has
    neither is never falsely failed.
    """

    status: str = ""
    command: str = ""
    output: str = ""
    reason: str = ""


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


__all__ = [
    "BranchOutcome",
    "ChangedFiles",
    "DevResult",
    "DispatchEntry",
    "FailureReport",
    "FixResult",
    "ImplContext",
    "ImplResult",
    "LayerPick",
    "LintOutcome",
    "OperatorAnswer",
    "OperatorGate",
    "OperatorResolution",
    "PlanResult",
    "PlanValidation",
    "QaRunEntry",
]
