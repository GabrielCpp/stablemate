"""Every way a Python-defined workflow can go wrong, named.

The split that matters is *when*: `WorkflowDefinitionError` is raised while the
module is being imported and the decorators run, so it costs a test rather than a
run; everything else is raised while a run is in flight.
"""
from __future__ import annotations


class PyflowError(Exception):
    """Base for every error the Python state-machine driver raises."""


class WorkflowFailed(PyflowError):
    """A state gave up. The workflow's own way of ending a run badly.

    Deliberately an exception rather than a fourth transition type: a failure needs
    a traceback, and it has to compose with the retry ladder in `runner/ladder.py`
    the same way any other exception does.

    `failure_class` and `artifacts` are optional diagnosis a raise site can attach for
    the outbox handoff (`workhorse/pyflow/run.py::_record_failure_handoff`) to surface —
    a short machine-readable code (`"transition-budget-exhausted"`, `"qa-give-up"`) and a
    `name -> path` map of whatever the site already knows is worth reading. Every raise
    site still works with neither: the handoff falls back to the exception's class name
    and the run dir's own paths, which is all a bare `WorkflowFailed(msg)` ever had.
    """

    def __init__(
        self,
        message: str,
        *,
        failure_class: str = "",
        artifacts: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.artifacts = dict(artifacts or {})


class AgentTurnFailed(PyflowError):
    """The recovery ladder is finished with an agent turn and it produced nothing.

    Raised by `self.agent` only once every rung is spent — transient retries, compaction,
    reframes — so a state that catches this is landing a verdict, not short-circuiting a
    recovery that would have worked.

    Its sibling `AgentTimeout` is deliberately NOT a subtype: the two want opposite things
    from the node. A cut turn was working and may have left a partial file worth keeping;
    this one produced *no* answer at all — an empty result from a flaky provider, a CLI
    that exited non-zero — so a state that repaired a draft here would be repairing a file
    the turn never wrote.

    It exists for the same reason `AgentTimeout` does. The ladder's verdict is a fact about
    the workflow's node, not about the transport, and the transport's own name for it
    (`BackendInvocationError`, in `workhorse.runner.failure`) is a module a workflow must
    not import — pyflow stays cheap to import because resolving a workflow *name* imports
    it. Without a name on this side of that line, a state could not say "gate on this"
    however carefully it enumerated, and the run died on a node whose own author had
    written an operator gate for exactly this case.

    Uncaught, it stops the run at a resumable checkpoint rather than stamping a terminal
    (`pyflow/run.py`): a provider that gave up is an operational stop, not the workflow's
    verdict on itself.
    """


class AgentTimeout(PyflowError):
    """An agent turn was stopped at its per-node `timeout`, with its budget spent.

    Raised by `self.agent` only once the recovery ladder has finished with the turn —
    it is the ladder's verdict, not a report of the first overrun, so a state that
    catches this is not short-circuiting a retry that would have succeeded.

    It exists so a state can *land* an overrun rather than let it end the run. The
    ladder cannot make that decision: whether anything survives a cut turn depends
    entirely on what the turn was writing. Where the deliverable is the turn's reply
    there is nothing to salvage and stopping at a resumable checkpoint is right; where
    the deliverable is a **file**, the partial draft on disk is usually worth more than
    a fresh start, and only the calling state knows which it has. Pair it with
    `retries=0` — otherwise the reframes spend the node's whole budget again before
    this is ever raised.

    The transport-level signal (`BackendInvocationError.timed_out`) lives in
    `workhorse.runner.failure`, which a workflow must not import — pyflow stays cheap
    to import because resolving a workflow *name* imports it. This is the translation;
    `AgentTurnFailed` above is the one for every other way a spent turn ends.
    """


class RunBudgetExceeded(PyflowError):
    """The run outlived `WORKHORSE_MAX_RUNTIME_S`. An operational stop, not a verdict.

    Separate from `WorkflowFailed` because the two want opposite things from the run
    dir. A workflow that fails has *decided*: it reached its fail terminal, the run is
    over, and re-entering it would re-run the state that just gave up. A run that ran out
    of clock decided nothing — it was cut between two states, mid-work, and the whole
    point of checking the budget *between* transitions rather than killing the process is
    that the checkpoint it left is good.

    So this one must not stamp a terminal. `terminal` is how `rundir.find_latest_resumable`
    and the `--auto` resolution tell "this run is over" from "this run stopped", and a
    budget stop that stamped one would be skipped by `--resume-latest` — leaving the
    driver's own advice ("Raise the budget and resume") impossible to follow through the
    flag that exists to follow it. It is recorded like an interrupt instead: an `error` on
    `run.json`, no terminal, exit 1.
    """


class WorkflowDefinitionError(PyflowError):
    """The workflow is mis-declared — raised at registration/import time.

    Alias collisions land here: an alias that shadows a live name, or that two
    names both claim, would silently route a resume to the wrong place. That is the
    one new failure mode aliases introduce, so it is caught where the decorators
    run rather than at hour 30 of an unattended run.
    """


class UnknownStateError(PyflowError):
    """A checkpoint (or transition) names a state this workflow does not have.

    A resume that finds no matching state or alias **fails loudly** — never a cache
    miss, never a silent fresh start. An undeclared rename is therefore detected,
    and `aliases=[...]` on the surviving state is the one-line fix.
    """


class UnknownNodeError(PyflowError):
    """A function was used as a node but never registered on a blueprint."""


class NodeNotRunError(PyflowError):
    """`self.output(node)` for a node that has not run in this run.

    The predecessor (`get_node_output`) returned its `default` here, making "never
    ran", "unreadable" and "legitimately empty" indistinguishable. This one raises.
    """


class WorkflowFrozenError(PyflowError):
    """Something tried to write to the workflow instance after `setup()` returned.

    A mutable field is a parameter that skipped the checkpoint: it survives a
    transition in memory and does not survive a resume, so the bug only appears
    after a crash or an `Await`.
    """
