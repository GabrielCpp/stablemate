"""`ostler qa` — deterministic QA run bookkeeping."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ostler.qa import addresses, devices, fixtures, tools
    from ostler.qa.clean import cmd_clean, legacy_scratch_roots
    from ostler.qa.lint import cmd_lint
    from ostler.qa.report import (
        REPORT_FILE,
        ReportError,
        build_report,
        render_report,
        report_path,
        run_id_of,
        write_report,
    )
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
    from ostler.qa.session import QA_DIRNAME, RESERVED_LABELS, ScratchLabelError, scratch_dirname

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


_SUBMODULES = {"addresses", "devices", "fixtures", "tools"}
_HOMES = {
    **dict.fromkeys(
        ("DaemonSpec", "QaOutcome", "cmd_assert", "cmd_frames", "cmd_report", "cmd_replay", "cmd_run",
         "cmd_start", "cmd_step", "cmd_stop", "cmd_validate"), "ostler.qa.run"),
    "cmd_lint": "ostler.qa.lint",
    **dict.fromkeys(("cmd_clean", "legacy_scratch_roots"), "ostler.qa.clean"),
    **dict.fromkeys(("QA_DIRNAME", "RESERVED_LABELS", "ScratchLabelError", "scratch_dirname"), "ostler.qa.session"),
    **dict.fromkeys(
        ("REPORT_FILE", "ReportError", "build_report", "render_report", "report_path", "run_id_of",
         "write_report"), "ostler.qa.report"),
}


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return import_module(f"ostler.qa.{name}")
    home = _HOMES.get(name)
    if home is None:
        raise AttributeError(f"module 'ostler.qa' has no attribute {name!r}")
    return getattr(import_module(home), name)
