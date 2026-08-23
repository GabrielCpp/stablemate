"""`ostler qa` — deterministic QA run bookkeeping.

See ostler/docs/QA-RUN.md for the full design rationale.

Commands:
  ostler qa start   <run-id> --story S --spec DIR [--daemon name:cmd ...]
  ostler qa step    --id I --label L --mechanism M --cmd CMD [--capture k=$.path] [--out PATH]
  ostler qa assert  --id I --label L --check TYPE [check-specific flags]
  ostler qa stop
  ostler qa report  [--spec DIR] [--out-dir LABEL] [--ledger]
  ostler qa replay  [--spec DIR]
  ostler qa run     <plan-file> [--spec DIR] [--stop-on-fail]
  ostler qa lint    <plan-file>
  ostler qa validate <plan-file>
  ostler qa sensitivity [--node SUBSTR]
  ostler qa context-show [--spec DIR] [--required] [--node SUBSTR] [--limit N]
  ostler qa compile-plan --spec DIR [--out PATH]
  ostler qa evidence-map [--spec DIR] [--status S] [--out PATH]
  ostler qa clean   --spec DIR [--yes]
"""

from ostler.qa.run import DaemonSpec, QaOutcome, cmd_assert, cmd_report, cmd_replay, cmd_run, cmd_start, cmd_step, cmd_stop, cmd_validate
from ostler.qa.compile import cmd_compile_plan, compile_plan
from ostler.qa.lint import cmd_lint
from ostler.qa.sensitivity import cmd_sensitivity
from ostler.qa.clean import cmd_clean, legacy_scratch_roots
from ostler.qa.session import QA_DIRNAME, RESERVED_LABELS, ScratchLabelError, scratch_dirname
from ostler.qa import tools
from ostler.qa.report import (
    REPORT_FILE,
    ReportError,
    build_report,
    render_report,
    report_path,
    run_id_of,
    write_report,
)
from ostler.qa.evidence_map import (
    STATUSES,
    EvidenceMapError,
    build_evidence_map,
    render_evidence_map,
)
from ostler.qa.context import (
    build_context,
    cmd_context,
    cmd_context_validate,
    render_context,
    render_obligations,
    select_obligations,
    validate_context,
    write_context,
)

__all__ = [
    "DaemonSpec",
    "QaOutcome",
    "cmd_start",
    "cmd_step",
    "cmd_assert",
    "cmd_stop",
    "cmd_report",
    "cmd_replay",
    "cmd_run",
    "cmd_lint",
    "cmd_compile_plan",
    "compile_plan",
    "cmd_sensitivity",
    "cmd_validate",
    "cmd_clean",
    "legacy_scratch_roots",
    "QA_DIRNAME",
    "RESERVED_LABELS",
    "ScratchLabelError",
    "scratch_dirname",
    "cmd_context",
    "cmd_context_validate",
    "build_context",
    "write_context",
    "render_context",
    "render_obligations",
    "select_obligations",
    "validate_context",
    "STATUSES",
    "EvidenceMapError",
    "build_evidence_map",
    "render_evidence_map",
    "REPORT_FILE",
    "ReportError",
    "build_report",
    "render_report",
    "report_path",
    "run_id_of",
    "write_report",
    "tools",
]
