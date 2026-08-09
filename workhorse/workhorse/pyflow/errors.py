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
