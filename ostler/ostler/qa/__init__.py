"""`ostler qa` — deterministic QA run bookkeeping."""

from ostler.qa.run import (
    DaemonSpec,
    QaOutcome,
    cmd_assert,
    cmd_frames,
    cmd_report,
    cmd_replay,
    cmd_run,
    cmd_start,
    cmd_step,
    cmd_stop,
    cmd_validate,
)
from ostler.qa.lint import cmd_lint
from ostler.qa.clean import cmd_clean, legacy_scratch_roots
from ostler.qa.session import QA_DIRNAME, RESERVED_LABELS, ScratchLabelError, scratch_dirname
from ostler.qa import addresses, devices, fixtures, tools
from ostler.qa.report import (
    REPORT_FILE,
    ReportError,
    build_report,
    render_report,
    report_path,
    run_id_of,
    write_report,
)

__all__ = [
    "DaemonSpec",
    "QaOutcome",
    "cmd_start",
    "cmd_step",
    "cmd_assert",
    "cmd_stop",
    "cmd_frames",
    "cmd_report",
    "cmd_replay",
    "cmd_run",
    "cmd_lint",
    "cmd_validate",
    "cmd_clean",
    "legacy_scratch_roots",
    "QA_DIRNAME",
    "RESERVED_LABELS",
    "ScratchLabelError",
    "scratch_dirname",
    "REPORT_FILE",
    "ReportError",
    "build_report",
    "render_report",
    "report_path",
    "run_id_of",
    "write_report",
    "fixtures",
    "addresses",
    "devices",
    "tools",
]
