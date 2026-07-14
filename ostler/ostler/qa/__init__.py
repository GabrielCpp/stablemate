"""`ostler qa` — deterministic QA run bookkeeping.

See ostler/docs/QA-RUN.md for the full design rationale.

Commands:
  ostler qa start   <run-id> --story S --spec DIR [--daemon name:cmd ...]
  ostler qa step    --id I --label L --mechanism M --cmd CMD [--capture k=$.path] [--out PATH]
  ostler qa assert  --id I --label L --check TYPE [check-specific flags]
  ostler qa stop
  ostler qa report  [--spec DIR]
  ostler qa replay  [--spec DIR]
  ostler qa run     <plan-file> [--spec DIR] [--stop-on-fail]
  ostler qa validate <plan-file>
"""

from .run import (
    QaOutcome,
    cmd_assert,
    cmd_report,
    cmd_replay,
    cmd_run,
    cmd_start,
    cmd_step,
    cmd_stop,
    cmd_validate,
)
from .context import build_context, render_context, validate_context, write_context

__all__ = [
    "QaOutcome",
    "cmd_start",
    "cmd_step",
    "cmd_assert",
    "cmd_stop",
    "cmd_report",
    "cmd_replay",
    "cmd_run",
    "cmd_validate",
    "build_context",
    "write_context",
    "render_context",
    "validate_context",
]
