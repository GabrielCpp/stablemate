"""The stablemate workflows, as code.

Each workflow is a subpackage — its ``workflow.py``, its ``nodes/``, its ``prompts/``
— and declares its own console script in ``[project.scripts]``, so it is reached as
``workhorse-<name> run``. Nothing resolves a workflow by name: the script hands the
engine the ``Registry`` object directly. Shared workflow-side helpers live in ``kit/``.

Imports point one way: a workflow's ``workflow.py`` imports its ``nodes/`` and
``flows/``; nothing under ``nodes/`` imports ``workflow.py``. The dependency on
workhorse runs the same direction — this package imports the engine, the engine knows
nothing about what is in here.
"""

from __future__ import annotations

__all__: list[str] = []
