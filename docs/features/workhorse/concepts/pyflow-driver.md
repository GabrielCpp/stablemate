---
type: concept
slug: pyflow-driver
title: drive — walk a workflow written as a Python state machine
---
# drive — walk a workflow written as a Python state machine

The loop workhorse runs. There is one engine and this is it: `drive` calls a *method* on a
`Workflow` instance and follows the transition it returns, checkpointing before each one.
Control flow is ordinary Python — `if`, `for`, a counter that is just a counter — because the
graph lives in the method bodies rather than in a data file the engine interprets.
An operator `Await` is durable at the gate path: the checkpoint records `waiting_on`, the gate
file records its status and accumulated conversation, and a resumed process re-parks only when
that file is still awaiting an operator.

The retired YAML front-end advanced a cursor over a declared node graph and merged each node's
outputs into an ambient context map; what replaced it is [the three tiers of
state](#the-three-tiers-of-state-and-no-fourth) below. Everything *under* the state — the runs
directory and [`ArtifactWriter`](artifact-writer.md) layout, the [agent
backends](agent-backend.md), telemetry, and the [resilience ladder](run-agent.md) — is
unchanged by that, which is why a ported workflow's operator knobs still mean what they meant.

- code: `workhorse/workhorse/pyflow/driver.py::drive`

## Methods

### Resume
- sig: `Resume(state, params, inputs={}, ctx=None, flow=None, waiting_on=None)`
- code: `workhorse/workhorse/pyflow/driver.py::Resume`
- semantics: checkpoint values needed to re-enter a state, revive workflow context, and restore a waiting gate

### read_resume
- sig: `read_resume(checkpoint: Checkpoint) -> Resume`
- does: converts a validated pyflow checkpoint into the resume value used by the driver
- raises: `WorkflowFailed` when the checkpoint belongs to the retired YAML engine
- returns: resume state, parameters, inputs, context, flow, and waiting gate
- verify: exit_status(code=1)
- code: `workhorse/workhorse/pyflow/driver.py::read_resume`

### coerce_params
- sig: `coerce_params(bound, params: dict[str, Any], *, state: str) -> dict[str, Any]`
- does: validates checkpoint parameters against the state's annotations and defaults
- raises: `WorkflowFailed` for unknown, invalid, or missing required checkpoint parameters
- returns: parameters coerced to their annotated runtime types
- verify: exit_status(code=1)
- code: `workhorse/workhorse/pyflow/driver.py::coerce_params`

### answered
- sig: `answered(path: Path) -> bool`
- returns: `False` for a missing or explicitly awaiting operator gate, otherwise `True`
- verify: json_path(path="$.answered", equals=false)
- code: `workhorse/workhorse/pyflow/driver.py::answered`

### wait_for_answer
- sig: `wait_for_answer(path, *, interval, clock=SYSTEM_CLOCK, channel=NULL_CHANNEL, log=None, deadline=None, kind="operator") -> Request | None`
- does: polls the gate until its status is no longer `AWAITING_OPERATOR`
- does: treats a missing gate as unanswered
- does: ignores file saves that leave the status `AWAITING_OPERATOR`
- does: registers an operator gate for live `questions` requests while waiting
- does: consumes an operator `answer` request in the waiting frame
- does: leaves non-answer control requests for the caller to handle
- does: refuses an `answer` request during a machine wait without writing the wake file
- does: clears the live operator-question registration on every exit
- raises: `WorkflowFailed` when the wall-clock deadline expires while waiting
- returns: `None` after the gate is answered or a machine wake file exists
- returns: a non-answer control request that interrupted the wait
- verify: persists(subject="answered operator gate")
- verify: json_path(path="$.status", equals="ANSWERED")
- verify: unchanged(subject="gate with a draft save while STATUS remains AWAITING_OPERATOR")
- verify: count(subject="pending operator gates after the wait exits", equals=0)
- verify: unchanged(subject="machine wake file after an operator answer request")
- code: `workhorse/workhorse/pyflow/driver.py::wait_for_answer`
- tests: `workhorse/tests/test_pyflow.py::test_await_ignores_a_save_that_left_the_gate_unanswered`,
  `workhorse/tests/test_pyflow.py::test_an_answer_for_another_gate_is_refused_and_the_wait_goes_on`,
  `workhorse/tests/test_pyflow.py::test_a_hand_edit_that_beats_the_socket_answer_wins`,
  `workhorse/tests/test_pyflow.py::test_a_machine_wait_refuses_an_operator_answer`,
  `workhorse/tests/test_pyflow.py::test_a_parked_wait_lists_its_gate_for_the_questions_verb_and_clears_it_after`

### _consume_answer
- sig: `_consume_answer(request, path: Path, channel: ControlChannel, log: logging.Logger) -> None`
- does: refuses an answer naming a different gate
- does: refuses an answer when the gate is already answered
- does: creates a missing gate with an answered status when the request targets the current gate
- does: writes the answered gate content before acknowledging success
- does: appends non-empty answer text below the existing gate history
- returns: `None` after replying with success or a refusal on the control channel
- verify: persists(subject="socket answer in the current gate file")
- verify: json_path(path="$.answer_ack", equals=true)
- code: `workhorse/workhorse/pyflow/driver.py::_consume_answer`
- tests: `workhorse/tests/test_pyflow.py::test_an_answer_over_the_socket_lands_in_the_gate_file_and_resumes_the_run`,
  `workhorse/tests/test_pyflow.py::test_an_answer_for_another_gate_is_refused_and_the_wait_goes_on`

### _ask
- sig: `_ask(path: Path, questions: str, log: logging.Logger) -> None`
- does: leaves the gate file untouched when the question text is empty
- does: creates a new operator gate for non-empty plain questions
- does: re-arms an existing gate by changing its live status and appending the new question block
- does: preserves prior questions and answers when re-arming
- returns: `None` after the gate ask is written or intentionally omitted
- verify: count(subject="STATUS lines after re-arming one gate", equals=1)
- code: `workhorse/workhorse/pyflow/driver.py::_ask`
- tests: `workhorse/tests/test_pyflow.py::test_blocking_twice_on_one_gate_appends_rather_than_replacing_it`,
  `workhorse/tests/test_gates.py::test_a_second_ask_keeps_the_first_ones_questions_and_its_answers`

### _park
- sig: `_park(path: Path, env: RunEnv, *, kind: str) -> None`
- does: waits for the gate or machine wake file using the environment poll interval and deadline
- does: keeps handling an operator answer in the waiting frame until the current gate is answered
- does: raises `ReloadRequested` immediately for a reload that cuts a parked wait
- does: holds boundary reload and profile-switch requests until the wait ends
- raises: `ReloadRequested` when a cutting reload arrives while parked
- verify: exit_status(code=0)
- returns: `None` after the wait ends without a cutting reload
- code: `workhorse/workhorse/pyflow/driver.py::_park`
- tests: `workhorse/tests/test_pyflow.py::test_a_reload_cuts_a_parked_operator_wait`,
  `workhorse/tests/test_pyflow.py::test_a_reload_cut_wait_re_parks_on_resume_and_the_answer_still_lands`

## Contract

- **Input:** a `Workflow` instance (its class fields already populated from `--params`), a
  `RunEnv` (the [`ArtifactWriter`](artifact-writer.md), the workflow directory, the session-id
  path, the [`RunConfig`](config.md), and the `dry_run` / `deadline` flags), and an optional
  `Resume` read off a checkpoint.
- **Output:** whatever the terminal `Done(result)` carried. A `handoff` caller receives exactly
  this value.
- **Raises:** `WorkflowFailed` — from a state that raises it, from a state that returns something
  that is not a transition, when the transition budget is exhausted, or when a checkpoint's
  parameters will not coerce; `WorkflowFrozenError` when a state assigns to the instance;
  `RunBudgetExceeded` when `deadline` passes between states.
- consistency: workflow-state-name — A state name matching neither a live name nor a declared alias raises
  `UnknownStateError` naming the known live states and the `aliases=[…]` fix instead of falling
  back to `start`, because silently restarting a long-running workflow is the worse failure.

## Algorithm

1. **Seal the instance.** On a fresh start, call `setup()` once and pass its return to
   `_seal(ctx)`, which sets `self._ctx` and flips the freeze. On a **resume**, `setup()` is *not*
   re-run — the recorded `ctx` is revived from the checkpoint and sealed instead, because a
   `setup()` that reads the world would otherwise re-read a world that has moved.
2. **Resolve the state.** `type(wf).resolve_state(name)` uses the class's `NameIndex`, which holds
   live names and declared `aliases=[…]`.
3. **Coerce the parameters.** A resumed state's parameters arrive as JSON. Each is run through a
   pydantic `TypeAdapter` built from the state's own annotation, so a `Path` checkpointed as a
   string comes back a `Path`.
4. **Checkpoint, then act.** `write_state_checkpoint(state, params, inputs=…, ctx=…,
   waiting_on=…)` is written *before* the state body runs, so a crash inside the body resumes into
   the same state rather than past it.
5. **Dispatch on the return value.** `Done` ends the loop; `Continue` binds its keyword arguments
   against the target's signature and loops; `Await` writes the questions, checkpoints with
   `waiting_on` set, and polls. Anything else is a `WorkflowFailed` — a state that falls off the
   end returning `None` is a bug, not a terminal.
   An operator gate is re-armed by appending its new question block, never by replacing its
   prior answers. A socket answer is written to that same file before its acknowledgement, and
   the next status read is what ends the wait.
6. **Resume a parked gate before dispatch.** When a checkpoint has `waiting_on`, inspect that
   path before entering the checkpointed state. Re-park if its first status is
   `AWAITING_OPERATOR`; skip the park if the gate is answered, missing, or a machine wake file
   has no operator status. This prevents a reload or crash from entering the state that expects
   an answer before the answer is available.
7. **Budget.** Each hop burns one unit of `max_transitions` (`WORKHORSE_MAX_TRANSITIONS`,
   default 1000). Exhaustion raises `WorkflowFailed`. A workflow that declares
   `REFUEL_ON = {"<param>"}` refills that budget to full whenever the named state parameter
   takes a new value, so what the count bounds is transitions *since the last forward step* —
   a drain's backlog stops being a number the operator must have predicted, while a
   ping-pong between two states, where the parameter never moves, still dies on the same
   1000. That, plus the wall-clock
   `WORKHORSE_MAX_RUNTIME_S` deadline checked between states, is the whole runaway bound —
   there is no per-node fuel budget, because a Python `for` loop is not a cycle in a graph.

## The three tiers of state, and no fourth

| Tier | Written by | Lives for | Reached as |
|---|---|---|---|
| Inputs | the CLI (`--params`) | the whole run | `self.<field>` |
| `self.ctx` | `setup()`, once | the whole run | `self.ctx` |
| State parameters | the previous state | one hop | the state's own arguments |

The rule is **if a state writes it, it is a parameter of the next state.** Everything a resume
needs is therefore in the checkpoint by construction, which is why the instance freezes once
`setup()` returns: an assignment from inside a state would produce a value that survives in
memory but not on disk, and the run would behave differently after a reboot than before one.

`self.output(node)` is a read, not a fourth tier — it re-reads the node's recorded
`output.json` (latest invocation, re-validated into the node's declared return type) and raises
`NodeNotRunError` when the node has not run.

## Validation happens three times, on purpose

| Moment | Mechanism | Catches |
|---|---|---|
| Author time | the state's own annotations | a parameter with no type |
| Transition time | `inspect.signature(target).bind(**kw)` | `Continue(None, self.review, cont=1)` — the typo fails on the transition that made it |
| Resume time | pydantic `TypeAdapter` per parameter | a checkpoint written by an older signature |

## Resume is coarse, so states must be idempotent

There is no intra-state memo, no step key, and no per-callsite fingerprint. A resume re-enters
the checkpointed state **from the top** and re-runs everything in it. This is a deliberate trade:
fingerprinting callsites would make a state's resumability depend on the source line it sits on,
so an edit between crash and resume would silently change which work is skipped.

The contract a state body owes is therefore **idempotency, not determinism** — a state that
appends a row checks first, a state that commits is a no-op on a clean tree.

## Renaming a state without stranding a run

The checkpoint names a state, so a rename orphans every run checkpointed on the old name.
`aliases=[…]` — on `@workflow.state` and on `@blueprint.node` alike — is the pin:

- a checkpoint naming an unknown state fails loudly rather than starting over;
- declaring the old name as an alias resumes it;
- an alias colliding with a live name raises at **registration** (import), not at resume;
- `dot` and `--dry-run` render live names only, so an alias never appears as a second state.

Nodes carry aliases for the same reason at a different layer: `self.output(node)` resolves against
a run *directory* named after the node, so a renamed node would otherwise lose the output a
half-finished run already recorded.

## A checkpoint from the retired engine is refused, not misread

A checkpoint is tagged `"engine": "pyflow"`, and `read_resume` refuses anything else by name.
The YAML engine is gone, but the run directories it wrote are not: they sit in the same
`.agents/runs` tree and are eligible for the same `--resume-latest`. The failure this prevents
is not the `KeyError` — it is a `current_id` that collides with a state name by coincidence and
resumes the wrong thing. Such a run cannot be resumed; start it over.

## Related

- [the workflow format](../workflow-format.md) — the package shape this walks
- [state graph](pyflow-state-graph.md) — what `dot` and `--dry-run` derive from the same classes
- [ArtifactWriter](artifact-writer.md) — the run directory and checkpoint files it writes
- [`AgentRunner.run`](run-agent.md) — the resilience ladder `self.agent` goes through unchanged
