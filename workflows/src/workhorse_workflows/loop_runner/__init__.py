"""`loop-runner` — hand a plan to one agent turn and let the target CLI's own
turn-internal tool-call loop carry it to completion.

Exists because none of the five backends workhorse already drives (claude, codex,
copilot, cline, opencode) expose an autonomous "work to a goal" mode distinct from
what a normal turn already is — `codex exec --json`, `opencode run --format json`
and the rest already run their own loop of tool calls *inside* one invocation. So
"use the target CLI's own loop mechanism" does not mean a second, different
subprocess to shell out to; it means calling the backend exactly once per run and
staying out of its way, while workhorse's own turn-level machinery — cap-wait,
transient-error retry, telemetry, groom visibility — keeps applying unchanged.

Deliberately absent, on purpose, all of it: a `continue`-until-done loop, a
per-story/per-epic backlog like `coder`'s, a completion-status field parsed out of
the reply, a workflow-owned turn or time budget. One `run_turn`. It finishes clean
or it raises — see `docs/plans/groom-dispatch-queue-and-loop-runner.md` §2.
"""
from __future__ import annotations
