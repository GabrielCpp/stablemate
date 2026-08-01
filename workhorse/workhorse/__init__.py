"""Workhorse — the engine that drives an agent CLI through a Python state machine.

A library, not a runner: there is no `workhorse` executable. What a workflow
distribution imports from here is the wiring for its *own* command::

    main = console_script(workflow.entry_point(Coder))

`main` is that command's body, exported for the rare caller that wants to drive it
directly; it takes the workflow and its registry as keyword arguments, because nothing
here resolves a workflow by name.
"""
from workhorse.cli import console_script, main

__all__ = ["console_script", "main"]
