"""The dev flow's models: plan, reuse, path validation, dispatch, implement, lint.

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

from typing import Any

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class PlanResult(CoderResult):
    """`prompts/plan-story.md` and `prompts/refine-plan.md` — the plan, or the blocker.

    `status` is `done` or `blocked`. A blank takes the YAML's `default:` arm, which is
    `done` — the plan gate is deliberately permissive, because depth and correctness are
    enforced downstream by implementation review and by QA, not here.
    """

    status: str = ""
    summary: str = ""


class ReuseResult(CoderResult):
    """`prompts/check-code-reuse.md` — does the plan propose to build what already exists?

    `status` is `ok` or `needs_rework`, and a blank takes `ok`: the gate is advisory and
    fail-open by design, because review and QA re-check reuse against the real diff.
    `findings` is left loosely typed — it is stringified into the refiner's review notes and
    never read field by field.
    """

    status: str = ""
    findings: list[dict[str, Any]] = []
    summary: str = ""


class ImplResult(CoderResult):
    """`prompts/implement-plan.md` — one service layer implemented, or the blocker.

    Nothing branches on it: the lint gate below and QA downstream decide whether the layer
    is done, and an agent claiming `done` is not evidence that it is.
    """

    status: str = ""
    notes: str = ""


class TestsResult(CoderResult):
    """`prompts/implement-plan-tests.md` — the failing tests written, or the blocker.

    Like `ImplResult`, nothing branches on it: the red gate downstream is the deterministic
    verdict on whether the tests turn did its job, and an agent claiming `done` is not
    evidence that it did.
    """

    status: str = ""
    notes: str = ""


class RedGateArm(CoderResult):
    """`arm_red_gate` — what the gate will hold the tests turn to, recorded before it runs.

    `mode` is `tdd`, `regression_only` or `qa_only`, and the last two both send the layer
    down the classic single-turn path. `regression_only` is the planner's escape for a
    story that changes no observable behavior; `qa_only` is for one whose every scenario
    is `Level: QA-only`, where the tests turn is told to exclude every scenario there is
    and so has nothing it may legitimately write. Neither means "no tests": the classic
    prompt still requires a test for every new behavior. They mean no enforced split and
    no gate. `baseline` is the worktree's changed paths *before* the tests
    turn, so the gate can diff what that turn alone touched; `test_command` and `signatures`
    are resolved here, once, so the tests prompt is told the exact command the gate will run
    and the gate judges purity by the same patterns every rework.
    """

    mode: str = "tdd"
    baseline: list[str] = []
    test_command: str = ""
    signatures: list[str] = []


class RedGateOutcome(CoderResult):
    """`run_red_gate` — the deterministic verdict between the tests turn and the code turn.

    `status` is one of seven: `red` (the suite failed and a reported failure names one of
    the new tests — proceed to the code turn), `all_green` (exit 0 — the tests exercise
    nothing missing, loop back), `impure` (the tests turn wrote production code, loop back),
    `no_tests` (the turn wrote no test file, loop back), `unattributed_red` (the suite
    failed, but on something other than the new tests — the red is somebody else's, loop
    back), `unreached` (the suite stopped in an earlier package and never reported on the
    new tests at all — nothing to judge, stand aside), or `skipped` (no cwd, no test
    command, or the command never returned — the gate stands aside rather than falsely
    failing, the same fail-open shape as the lint gate's `skipped`). A blank status takes
    the proceed arm, because a gate that cannot speak is not evidence against the tests.

    `unreached` is deliberately *not* rejecting. A rework cannot help: the failure that
    stopped the suite is in code this layer did not write and its agent may not touch, so
    looping back only spends turns and pressures the tests turn into narrowing its own
    command to manufacture attribution. The engine already fails open once the reworks are
    exhausted, so this reaches the same end state without paying for it.

    `changed_files` is what the tests turn touched with the harness's own state subtracted;
    `non_test_files` is the production code among it, which is what `impure` reports; and
    `failing_files` is the subset of the new test files a failure line actually named, so
    the code turn is told which reds it owes green rather than inferring it from a log.
    """

    status: str = ""
    command: str = ""
    changed_files: list[str] = []
    non_test_files: list[str] = []
    failing_files: list[str] = []
    log_path: str = ""
    reason: str = ""


class FixLintResult(CoderResult):
    """`prompts/fix-lint.md` — the lint repair turn's own report. `fixed` or `failed`.

    Nothing branches on it either; the next `run_lint` is what decides.
    """

    status: str = ""
    notes: str = ""


class OperatorResolution(CoderResult):
    """`prompts/resolve-operator.md` — the auto-operator's verdict on a block.

    `decision` is `answered` (it resolved the block and the flow retries) or `escalated`
    (only a human can). A blank matches neither, so the conservative arm — halt for the
    human — is the else. Note the field is `summary` here and `notes` in `author`'s copy of
    this model: the two prompts genuinely ask for different key names, and the port follows
    each prompt rather than unifying a name the model would then not emit.
    """

    decision: str = ""
    summary: str = ""

    #: What the resolver attempted and ruled out before it escalated, one line each. It is
    #: the diagnosis so far, and without it the human who arrives at the gate re-runs every
    #: dead end the resolver already paid for. Defaulted and never required: an older
    #: transcript, and a resolver that answered rather than escalated, both parse with it
    #: absent.
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


class DevResult(CoderResult):
    """What the dev flow hands back: `ready`, or `replan` when the epic premise was wrong.

    The YAML's `dev_done` terminal declared no outputs and the parent read two flow-level
    vars off it — `dev_status` (defaulting to `ready`) and `operator_input`. Only the
    operator's answer text ever crossed back, so that is the second field here rather than
    the whole `OperatorAnswer`.
    """

    status: str = "ready"
    operator_notes: str = ""


__all__ = [
    "BranchOutcome",
    "DevResult",
    "DispatchEntry",
    "FixLintResult",
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
    "RedGateArm",
    "RedGateOutcome",
    "ReuseResult",
    "TestsResult",
]
