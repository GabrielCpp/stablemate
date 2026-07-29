"""The stablemate workflows, as code.

Each workflow is a subpackage — its ``workflow.py``, its ``nodes/``, its ``prompts/``
— and registers itself in the ``workhorse.workflows`` entry-point group so
``workhorse run <name>`` finds it. Shared workflow-side helpers live in ``kit/``.

Imports point one way: a workflow's ``workflow.py`` imports its ``nodes/`` and
``flows/``; nothing under ``nodes/`` imports ``workflow.py``. The dependency on
workhorse runs the same direction — this package imports the engine, the engine knows
nothing about what is in here.
"""

from __future__ import annotations

__all__: list[str] = []
