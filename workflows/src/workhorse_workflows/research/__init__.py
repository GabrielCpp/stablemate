"""The research workflow: a gate-ladder experiment loop, as a Python state machine.

Ported from `base-library/workflows/research/workflow.yaml`. The YAML version is still
the one that ships in the base library; this is the same behavior expressed as states,
and it is the proof that the driver can carry a real workflow.
"""
from __future__ import annotations
