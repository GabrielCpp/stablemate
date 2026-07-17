from __future__ import annotations
import ast
import inspect
import io
import json
import os
import runpy
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Protocol

from workhorse import logsetup
from workhorse.graph.nodes import ScriptNode
from workhorse.graph.context import WorkflowContext
from workhorse.templates import render_string

# The module name a script with a main() is executed under. Deliberately NOT
# "__main__": that would fire the script's own `if __name__ == "__main__"` guard,
# which calls main() with no arguments — so the logger could never be passed. The
# guard stays in the scripts because it keeps them runnable by hand; workhorse
# just doesn't go through it. See docs: the node entry point is main(logger).
_SCRIPT_MODULE_NAME = "workhorse_script"

# Escape hatch back to the pre-in-process behavior. A script node now shares the
# engine's process, so a hard crash (os._exit, a segfaulting C extension, an
# OOM) takes the run down with it, where a child process could only ever return
# a bad exit code. Set WORKHORSE_SCRIPT_INPROCESS=0 to isolate scripts again at
# the cost of the per-script logs/telemetry this exists to provide.
_INPROCESS = (os.environ.get("WORKHORSE_SCRIPT_INPROCESS") or "1").strip().lower() not in (
    "0", "false", "no",
)


class ScriptExitError(Exception):
    """Raised when a workflow script exits with a non-zero code.

    Carries the original exit code so callers (e.g. ``workhorse run``) can
    propagate it faithfully — e.g. ``await_operator.py`` exits with 2 to signal
    "operator input required", which is distinct from an unexpected crash (1).
    """

    def __init__(self, script: str, exit_code: int, stderr: str) -> None:
        super().__init__(
            f"Script '{script}' exited with code {exit_code}.\nstderr: {stderr.strip()}"
        )
        self.exit_code = exit_code


class ScriptRunner(Protocol):
    """Executes one script node's file and returns ``(returncode, stdout, stderr)``.

    The seam that lets the engine swap execution strategies: in-process by default
    (``InProcessScriptRunner``), as a child process when isolation is worth more
    than observability (``SubprocessScriptRunner``), or under the test harness's
    subclass — so a test can monkeypatch the ``scriptutil`` helpers a script calls
    with no PATH shims and no CLI subprocess.
    """

    def run(
        self,
        script_path: Path,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        node_id: str = "",
    ) -> tuple[int, str, str]:
        ...


class InProcessScriptRunner:
    """Default runner: import the script and call ``main(logger)`` in this process.

    Scripts used to be spawned as children, which made them the one part of a run
    that telemetry could not see: a child has no ``otel._active``, so its spans
    were inert and its logs died on a captured pipe. Running them here puts their
    log records on the engine's own root logger — same handlers, same ``run_id``,
    same collector — which is the entire reason for the change.

    It mirrors ``python <script.py> <argv>`` closely enough that a script cannot
    tell the difference: ``sys.argv``, the cwd, ``os.environ`` and ``sys.path[0]``
    (so a sibling ``from lib import ...`` resolves) are all set and restored, and
    ``SystemExit`` becomes a return code rather than ending the run. That last one
    is not a nicety — ``emit()``-style helpers across the library print JSON and
    then ``sys.exit(0)`` from inside ``main``, so SystemExit is normal control
    flow here, not an error.

    stdout is captured because it is the node's *data* channel (the JSON the
    outputs are parsed from), not a place for messages. stderr is captured to
    match what the subprocess runner did — surfaced only when the script fails.
    Logs bypass both: the console handler holds the real stderr from before this
    redirection, which is what keeps ``logger.info(...)`` on the terminal while
    ``print(...)`` still lands in the JSON payload.
    """

    # Exceptions that must escape rather than become "exit 1" — the test harness
    # signals its own timeout this way and cannot have it swallowed as a crash.
    _reraise: tuple[type[BaseException], ...] = ()

    def run(
        self,
        script_path: Path,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        node_id: str = "",
    ) -> tuple[int, str, str]:
        _reject_non_python(script_path)
        old_argv, old_cwd = sys.argv[:], os.getcwd()
        old_env, old_path = os.environ.copy(), sys.path[:]
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            sys.argv = [str(script_path), *argv]
            os.chdir(cwd)
            os.environ.clear()
            os.environ.update(env)
            # The sanctioned exception to "no sys.path surgery": CPython puts a
            # script's own dir on sys.path[0] when run as `python script.py`. Keep
            # emulating it, or a sibling import that resolved as a subprocess
            # would start failing here.
            sys.path.insert(0, str(Path(script_path).parent))
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    code = self._exec(script_path, node_id)
                except SystemExit as exc:
                    c = exc.code
                    code = 0 if c is None else (c if isinstance(c, int) else 1)
                except self._reraise:
                    raise
                except Exception as exc:  # noqa: BLE001 — a crash is exit 1, as before
                    code = 1
                    err.write(f"\n{type(exc).__name__}: {exc}\n")
                    traceback.print_exc(file=err)
        finally:
            sys.argv = old_argv
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)
            sys.path[:] = old_path
        return code, out.getvalue(), err.getvalue()

    def _exec(self, script_path: Path, node_id: str) -> int:
        """Run the script body, then its ``main`` if it declares one."""
        if not _defines_main(script_path):
            # No main() to hand a logger to, so run it exactly as before: under
            # "__main__", which is also what fires any bare guard block. runpy
            # swaps sys.modules["__main__"] out and back for us.
            runpy.run_path(str(script_path), run_name="__main__")
            return 0
        namespace = runpy.run_path(str(script_path), run_name=_SCRIPT_MODULE_NAME)
        main = namespace.get("main")
        if not callable(main):  # a `main` that isn't a function — leave it alone
            return 0
        logger = logsetup.script_logger(node_id or script_path.stem)
        result = main(logger) if _wants_logger(main) else main()
        # `sys.exit(main())` is one of the two guard shapes in the library, so an
        # int return means the same thing here as it does there.
        return result if isinstance(result, int) else 0


def _defines_main(script_path: Path) -> bool:
    """Whether the script declares a top-level ``main`` — decided from the source.

    Read statically, before executing anything, because the answer picks the
    ``run_name`` and that has to be chosen up front: exec under "__main__" and a
    script's guard calls ``main()`` itself with no logger; exec under anything
    else and a script whose only entry point IS the guard would silently do
    nothing. Parsing tells us which of those two a script is without running it
    twice.
    """
    try:
        tree = ast.parse(script_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False  # let the real exec below raise a truthful error
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main"
        for n in tree.body
    )


def _wants_logger(main: Any) -> bool:
    """Whether ``main`` takes the logger — i.e. has a first positional parameter.

    Signature-detected rather than assumed, because ``main(logger)`` is a new
    contract and the scripts that predate it (every one in the library at the
    time of writing, plus any in a private overlay this repo cannot see) declare
    ``def main() -> None``. Calling those with an argument would break every one
    of them at once; this lets both shapes coexist so migration is per-script.
    """
    try:
        params = inspect.signature(main).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
        for p in params
    )


class SubprocessScriptRunner:
    """Spawn the script as a child process — the pre-in-process behavior.

    Kept as the escape hatch behind ``WORKHORSE_SCRIPT_INPROCESS=0``: it is the
    only way to stop a script that crashes the interpreter from taking the run
    with it, and the only way to run a script whose imports would pollute or
    conflict with the engine's own. It buys that with the blindness this change
    set out to remove — no logs, no telemetry, and (still) no timeout.
    """

    def run(
        self,
        script_path: Path,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        node_id: str = "",
    ) -> tuple[int, str, str]:
        cmd = _interpreter_cmd(script_path) + argv
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr


def default_script_runner() -> ScriptRunner:
    """The runner a run uses unless something injects one.

    The single place this is decided. It used to be picked independently by
    ``RunConfig.get_script_runner`` and by ``run_script``, which meant the engine
    always got the config's answer and ``run_script``'s was dead code that only
    tests (which inject a runner) could ever reach — a default nothing exercised.
    """
    return InProcessScriptRunner() if _INPROCESS else SubprocessScriptRunner()


def _reject_non_python(script_path: Path) -> None:
    """Shell scripts are rejected at load (graph/nodes.py); this is the
    defense-in-depth for a dynamically-constructed path reaching a runner that,
    unlike a subprocess, has no shebang line to honor."""
    suffix = script_path.suffix.lower()
    if suffix and suffix != ".py":
        raise ScriptExitError(
            str(script_path),
            1,
            f"in-process script nodes must be Python (.py), got '{suffix}'; port it "
            "to a Python script using workhorse.scriptutil, or set "
            "WORKHORSE_SCRIPT_INPROCESS=0 to run it as a child process",
        )


def _interpreter_cmd(script_path: Path) -> list[str]:
    """Prefix the interpreter so scripts don't need the executable bit. Only Python
    is supported; shell scripts are rejected at load (graph/nodes.py) and here as
    defense-in-depth against a dynamically-constructed ``.sh`` path."""
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(script_path)]
    if suffix in (".sh", ".bash"):
        raise ScriptExitError(
            str(script_path),
            1,
            "shell scripts are not supported; port to a Python script using "
            "workhorse.scriptutil",
        )
    return [str(script_path)]


def run_script(
    node: ScriptNode,
    context: WorkflowContext,
    workflow_dir: Path,
    graph_env: dict[str, str] | None = None,
    *,
    runner: ScriptRunner | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Render script args via Jinja2, run the script, parse stdout as JSON.

    Returns (command_str, extracted_outputs_dict).
    """
    ctx = context.as_dict()

    script_path = workflow_dir / node.script
    rendered_args = [render_string(arg, ctx) for arg in node.args]

    # Render per-node working directory; fall back to WORKHORSE_DEFAULT_SCRIPT_CWD
    # (injected by the test harness) or workflow_dir when unset.
    resolved_cwd = render_string(node.cwd, ctx).strip() if node.cwd else ""
    effective_cwd = resolved_cwd or os.environ.get("WORKHORSE_DEFAULT_SCRIPT_CWD") or str(workflow_dir)

    cmd_str = " ".join(_interpreter_cmd(script_path) + rendered_args)

    env = {**os.environ}
    if graph_env:
        env.update({k: render_string(v, ctx) for k, v in graph_env.items()})
    if node.env:
        env.update({k: render_string(v, ctx) for k, v in node.env.items()})

    runner = runner or default_script_runner()
    returncode, stdout, stderr = runner.run(
        script_path, rendered_args, effective_cwd, env, node.id
    )

    if returncode != 0:
        raise ScriptExitError(node.script, returncode, stderr)

    outputs = _extract_outputs(stdout, node)
    return cmd_str, outputs


def _extract_outputs(stdout: str, node: ScriptNode) -> dict[str, Any]:
    if not node.outputs:
        return {}

    try:
        parsed = json.loads(stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Script '{node.script}' stdout is not valid JSON: {e}\n"
            f"stdout: {stdout[:500]}"
        ) from e

    result: dict[str, Any] = {}
    for spec in node.outputs:
        if spec.key not in parsed:
            raise RuntimeError(
                f"Node '{node.id}': expected output key '{spec.key}' not found in script JSON"
            )
        result[spec.key] = parsed[spec.key]
    return result
