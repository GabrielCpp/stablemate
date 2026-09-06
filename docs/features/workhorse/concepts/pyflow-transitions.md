---
type: concept
slug: pyflow-transitions
title: pyflow transitions
---
# pyflow transitions

States return exactly `Continue`, `Done`, or `Await`; failure is raised as
`WorkflowFailed`, not represented as a fourth value. All transition targets are
positional-only, and their parameters are bound immediately so the checkpoint stores
a named dictionary. `.because()` adds an explanatory edge/log label without affecting
control flow.

- code: `workhorse/workhorse/pyflow/transitions.py::Transition`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Methods

### state_name
- sig: `state_name(target: Callable) -> str`
- raises: `TypeError` when the target has no name
- verify: exit_status(code=1)
- returns: the target's `__name__`
- code: `workhorse/workhorse/pyflow/transitions.py::state_name`

### bind_params
- sig: `bind_params(target: Callable, args: tuple, kwargs: dict) -> dict[str, Any]`
- does: binds positional and keyword transition arguments against the target signature
- raises: `TypeError` for an uninspectable target, variadic state parameters, or signature mismatch
- returns: named bound arguments for checkpointing
- verify: count(subject="named parameters produced by a valid transition binding", equals=1)
- code: `workhorse/workhorse/pyflow/transitions.py::bind_params`

### Continue
- sig: `Continue(result: object, next: Callable, /, *args, **kwargs)`
- does: carries a result and advances to the named next state with bound parameters
- returns: a transition with `kind=continue`
- verify: json_path(path="$.kind", equals="continue")
- code: `workhorse/workhorse/pyflow/transitions.py::Continue`

### Done
- sig: `Done(result: object = None)`
- does: marks the flow terminal and carries its result to the caller
- returns: a transition with no target
- verify: json_path(path="$.kind", equals="done")
- code: `workhorse/workhorse/pyflow/transitions.py::Done`

### Await
- sig: `Await(path: str | Path, questions: str, next: Callable, /, *args, **kwargs)`
- does: carries the next state and records the gate path and questions before waiting
- does: defaults `kind` to `operator`
- returns: a transition with `kind=await`
- verify: json_path(path="$.kind", equals="operator")
- code: `workhorse/workhorse/pyflow/transitions.py::Await`

### Await.on_machine
- sig: `Await.on_machine(path, questions, next, /, *args, **kwargs) -> Await`
- does: creates an await transition whose wake file is owed by a running machine
- returns: an `Await` with `kind=machine`
- verify: json_path(path="$.kind", equals="machine")
- code: `workhorse/workhorse/pyflow/transitions.py::Await.on_machine`
