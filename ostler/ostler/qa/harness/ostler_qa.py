"""The QA scenario harness: what a `qa_plan.py` imports, and what runs it."""

from __future__ import annotations

import ast as ast
import gc
import json
import shutil as shutil
import subprocess as subprocess
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from types import CodeType
from typing import Any

from ostler_qa_diagnostics import (
    ADDRESS_BOOK_ENV as ADDRESS_BOOK_ENV,
)
from ostler_qa_diagnostics import (
    DRIVER_NAMES as DRIVER_NAMES,
)
from ostler_qa_diagnostics import (
    MECHANISMS as MECHANISMS,
)
from ostler_qa_diagnostics import (
    MISSING,
    CheckFailed,
    HttpError,
)
from ostler_qa_diagnostics import (
    UI_DRIVER_NAMES as UI_DRIVER_NAMES,
)
from ostler_qa_diagnostics import (
    _Recorder as _Recorder,
)
from ostler_qa_diagnostics import (
    resolve_addresses as resolve_addresses,
)
from ostler_qa_diagnostics import (
    stop_reason as stop_reason,
)
from ostler_qa_diagnostics import (
    unresolved_address_detail as unresolved_address_detail,
)
from ostler_qa_dsl import (
    REGISTRY as REGISTRY,
)
from ostler_qa_dsl import (
    Secret as Secret,
)
from ostler_qa_dsl import (
    Target as Target,
)
from ostler_qa_dsl import (
    background,
    input_file,
    plan,
    scenario,
    secret,
    target,
    tool_env,
)
from ostler_qa_elements import (
    name_pattern as name_pattern,
)
from ostler_qa_elements import (
    template_pattern as template_pattern,
)
from ostler_qa_http import (
    UNSATISFIABLE as UNSATISFIABLE,
)
from ostler_qa_http import (
    Http as Http,
)
from ostler_qa_http import (
    Response,
)
from ostler_qa_page import QaPage
from ostler_qa_refs import (
    COMPUTED as COMPUTED,
)
from ostler_qa_refs import (
    _tree,
)
from ostler_qa_refs import (
    count_checks as count_checks,
)
from ostler_qa_refs import (
    extract_check_covers as extract_check_covers,
)
from ostler_qa_refs import (
    extract_fixtures as extract_fixtures,
)
from ostler_qa_tools import (
    Maestro as Maestro,
)
from ostler_qa_tools import (
    MaestroResult as MaestroResult,
)
from ostler_qa_tools import (
    ToolResult as ToolResult,
)
from ostler_qa_verifiers import (
    VERIFIERS as VERIFIERS,
)
from ostler_qa_verifiers import (
    Tree as Tree,
)

__all__ = [
    "CheckFailed",
    "HttpError",
    "MISSING",
    "Qa",
    "Response",
    "background",
    "input_file",
    "plan",
    "scenario",
    "secret",
    "target",
    "tool_env",
]


class Qa(QaPage):
    """Everything a scenario is given."""


def _describe(module_path: Path) -> dict[str, Any]:
    source = module_path.read_text(encoding="utf-8")
    _load(module_path, compile(_tree(source), str(module_path), "exec", dont_inherit=True))
    data = REGISTRY.as_json()
    counts = count_checks(source)
    check_covers = extract_check_covers(source)
    fixtures = extract_fixtures(source)
    for declared in data["scenarios"]:
        declared["checks"] = counts.get(declared["function"], 0)
        declared["check_covers"] = check_covers.get(declared["function"], [])
        declared["fixtures"] = fixtures.get(declared["function"], [])
    return data


def _load(module_path: Path, code: CodeType | None = None) -> None:
    """Import the plan module by path, with its own directory and the spec root importable, running *code* when the caller compiled it already."""
    import importlib.util

    sys.path.insert(0, str(module_path.parent.parent))
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("qa_plan", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{module_path} is not an importable Python module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["qa_plan"] = module
    if code is None:
        spec.loader.exec_module(module)
    else:
        exec(code, module.__dict__)


def _secret_values() -> list[str]:
    """Every declared secret this process can resolve, for redaction."""
    values: list[str] = []
    for declared in REGISTRY.secrets.values():
        try:
            values.append(declared.get())
        except KeyError:
            continue
    return values


def _open_browser(qa: Qa) -> Any:
    """Start Playwright for a browser target and hand the page to the scenario."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import ostler_qa_browser
    except ImportError as exc:
        if "playwright" not in str(exc):
            raise
        raise ImportError(
            f"target '{qa.target.name}' declares driver 'playwright' but {sys.executable} "
            "has no playwright; install it with "
            f"'{sys.executable} -m pip install playwright && {sys.executable} -m playwright "
            "install chromium'"
        ) from exc

    browser = ostler_qa_browser.Browser(
        qa.target,
        qa_dir=qa.dir,
        scenario_id=qa.scenario_id,
        clock=qa.offset_ms,
        emit=qa._recorder.emit,  # noqa: SLF001 - one module, split across two files
        secrets=_secret_values(),
    )
    qa.page = browser.open()
    qa.diagnostics = browser
    return browser


BROWSER_CLEAN_EXPECTED = ("no uncaught page error, no response of status 500 or higher, and every "
                          "browser dialog answered as the scenario declared, and every intercept rule altered an answer")


def _bind_browser_unclean(qa: Qa, problems: Sequence[str]) -> list[str]:
    """Record each browser problem as a failing assertion bound to the scenario's covers."""
    for problem in problems:
        qa._record(  # noqa: SLF001 - same module, the scenario-process side of the ledger
            "the browser stayed clean",
            False,
            actual=problem,
            expected=BROWSER_CLEAN_EXPECTED,
            covers=list(qa.covers),
            extra={"origin": "browser"},
        )
    return list(problems)


def _run(module_path: Path, scenario_id: str, context: dict[str, Any]) -> int:
    _load(module_path)
    declared = next((s for s in REGISTRY.scenarios if s.id == scenario_id), None)
    if declared is None or declared.func is None:
        raise SystemExit(f"no scenario {scenario_id!r} in {module_path}")
    target_decl = REGISTRY.targets[declared.target]
    recorder = _Recorder()
    qa = Qa(
        scenario_id=declared.id,
        target=target_decl,
        root=Path(context["root"]),
        spec_dir=Path(context["spec_dir"]),
        qa_dir=Path(context["qa_dir"]),
        covers=declared.covers,
        recorder=recorder,
        offset_base_ms=int(context.get("offset_ms", 0)),
        fixtures=context.get("fixtures", {}),
        tool_env=REGISTRY.tool_env,
    )
    browser = None
    status, error = "passed", None
    stop: dict[str, Any] = {}
    try:
        unresolved = unresolved_address_detail(target_decl)
        if unresolved is not None:
            qa._fault(declared.id, -1, "address", "environment", unresolved)  # noqa: SLF001 - one module
            raise RuntimeError(f"qa {declared.id!r}: {unresolved}")
        if target_decl.driver == "playwright":
            browser = _open_browser(qa)
        declared.func(qa)
    except CheckFailed:
        status = "failed"
    except BaseException as exc:  # noqa: BLE001 - the crash is the scenario's verdict
        status, error = "errored", stop_reason(exc, getattr(getattr(declared.func, "__code__", None), "co_filename", ""))
        stop = qa.stop_evidence(exc)
        print(traceback.format_exc(), file=sys.stdout)
    if browser is not None:
        unclean = _bind_browser_unclean(qa, browser.unclean())
        problems = [*unclean, *browser.close(failed=status != "passed" or bool(unclean))]
        if problems:
            status = "failed" if status == "passed" else status
            error = "; ".join([part for part in [error, *problems] if part])
    if qa.failures:
        status = "failed" if status == "passed" else status
    if status == "passed" and qa.assertions == 0 and declared.covers:
        status = "failed"
        error = (
            f"scenario {declared.id!r} claims coverage of {sorted(declared.covers)} but "
            "recorded no assertion — call qa.check() (or qa.eventually(), when the page is "
            "still arriving) on something the behaviour produced"
        )
    recorder.emit(
        {
            "type": "scenario",
            "id": declared.id,
            "status": status,
            "assertions": qa.assertions,
            "failures": qa.failures,
            "error": error,
            **({"stop": stop} if stop else {}),
        }
    )
    recorder.close()
    return 0 if status == "passed" else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: ostler_qa (describe <module> | run <module> <scenario> [<context json> | -])")
    mode, args = args[0], args[1:]
    if mode == "describe":
        gc.disable()
        json.dump(_describe(Path(args[0]).resolve()), sys.stdout)
        sys.stdout.write("\n")
        return 0
    if mode == "run":
        module_path, scenario_id = Path(args[0]).resolve(), args[1]
        raw = sys.stdin.read() if args[2:] == ["-"] else (args[2] if len(args) > 2 else "{}")
        context = json.loads(raw)
        return _run(module_path, scenario_id, context)
    raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    sys.modules.setdefault("ostler_qa", sys.modules["__main__"])
    raise SystemExit(main())
