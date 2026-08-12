"""The QA scenario harness: what a `qa_plan.py` imports, and what runs it.

This module is deliberately **one stdlib-only file**. It executes under the *project's*
interpreter — the venv of the repo under test — where ostler is not installed and cannot
be, so it may import nothing but the standard library and must stay copyable by putting
one directory on `PYTHONPATH`.

It has two modes, both entered by `ostler.qa.drivers.PythonDriver`:

``describe``
    Import the plan module, let its decorators register, print the declaration set as
    JSON on stdout, run nothing. This is what lets `ostler qa validate` read a plan it
    cannot itself import, and it is why **module-level code must be side-effect-free**:
    a decorator registration, never a request.

``run <scenario>``
    Execute one scenario function, streaming `step` / `assert` / `artifact` / `capture`
    records as JSONL on **fd 3**. Stdout stays the scenario's own, so a `print` in a
    scenario lands in the step log rather than corrupting the protocol.

The reason the whole format moved here from YAML is that shell fails silently and Python
does not. `data["responses"]` raises `KeyError`; `jq '.responses[]'` reads a missing
field as an empty stream and passes vacuously. Every affordance below is shaped to keep
that property: `qa.http` raises on an unexpected status, `qa.dir` is handed in already
resolved, and a scenario that records no assertion cannot pass.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import FunctionType
from typing import Any

__all__ = [
    "CheckFailed",
    "HttpError",
    "Qa",
    "Response",
    "background",
    "input_file",
    "plan",
    "scenario",
    "secret",
    "target",
]

#: The fd the record stream goes to. Not stdout: a scenario's own `print` is useful
#: output that belongs in its step log, and interleaving it with the protocol would make
#: every debugging `print` a parse error.
RECORD_FD = 3

#: Overrides `RECORD_FD`. `subprocess`'s `pass_fds` inherits a descriptor under the
#: number it already has in the parent, which is whatever `os.pipe()` handed out — so the
#: parent names the number instead of the child assuming it.
RECORD_FD_ENV = "OSTLER_QA_RECORD_FD"

MECHANISMS = ("live", "synthetic", "fixture")
DRIVERS = ("python", "playwright", "maestro")

DEFAULT_HTTP_TIMEOUT = 30.0


class HttpError(RuntimeError):
    """A response whose status the scenario did not say it expected."""


class CheckFailed(AssertionError):
    """A `qa.require` that did not hold. Recorded, then raised to end the scenario."""


# --------------------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------------------


@dataclass
class Target:
    name: str
    driver: str = "python"
    interpreter: str | None = None
    base_url: str | None = None
    app_id: str | None = None
    browser: str | None = None
    recording: dict[str, Any] | None = None
    permissions: list[str] | None = None

    def as_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"driver": self.driver}
        for key in ("interpreter", "base_url", "app_id", "browser", "permissions"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.recording is not None:
            data["recording"] = self.recording
        return data


@dataclass
class Secret:
    """A value the runner injects from its own environment and redacts from the ledger.

    Holding the *name* rather than the value is what keeps a secret out of the declaration
    JSON that `describe` prints — `describe` runs during validation, and its output is
    read by a reviewer and written to the run log.
    """

    name: str
    from_env: str

    def get(self) -> str:
        value = os.environ.get(self.name)
        if value is None:
            raise KeyError(
                f"secret {self.name!r} is not set in the scenario environment; the runner "
                f"injects it from ${self.from_env}"
            )
        return value


@dataclass
class ScenarioDecl:
    id: str
    function: str
    target: str
    mechanism: str
    covers: list[str]
    objective: str = ""
    preconditions: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    timeout: float | None = None
    line: int = 0
    func: Callable[..., None] | None = None

    def as_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "function": self.function,
            "target": self.target,
            "mechanism": self.mechanism,
            "covers": list(self.covers),
            "objective": self.objective,
            "line": self.line,
        }
        for key in ("preconditions", "checkpoints", "forbid"):
            value = getattr(self, key)
            if value:
                data[key] = list(value)
        if self.timeout is not None:
            data["timeout"] = self.timeout
        return data


@dataclass
class _Registry:
    run_id: str = ""
    story: str = ""
    targets: dict[str, Target] = field(default_factory=dict)
    secrets: dict[str, Secret] = field(default_factory=dict)
    inputs: dict[str, str] = field(default_factory=dict)
    background: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[ScenarioDecl] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "version": 3,
            "run_id": self.run_id,
            "story": self.story,
            "inputs": dict(self.inputs),
            "secrets": {name: {"from_env": s.from_env} for name, s in self.secrets.items()},
            "targets": {name: t.as_json() for name, t in self.targets.items()},
            "background": list(self.background),
            "scenarios": [s.as_json() for s in self.scenarios],
        }


REGISTRY = _Registry()


def plan(*, run_id: str, story: str) -> None:
    """Name the run and the story. Exactly one call per module."""
    if REGISTRY.run_id:
        raise ValueError("plan() was already called; a module declares one run")
    REGISTRY.run_id, REGISTRY.story = run_id, story


def target(
    name: str,
    *,
    driver: str = "python",
    interpreter: str | None = None,
    base_url: str | None = None,
    app_id: str | None = None,
    browser: str | None = None,
    recording: dict[str, Any] | None = None,
    permissions: Sequence[str] | None = None,
) -> Target:
    if driver not in DRIVERS:
        raise ValueError(f"target {name!r} has unknown driver {driver!r}; one of {DRIVERS}")
    if name in REGISTRY.targets:
        raise ValueError(f"duplicate target {name!r}")
    declared = Target(
        name=name,
        driver=driver,
        interpreter=interpreter,
        base_url=base_url,
        app_id=app_id,
        browser=browser,
        recording=recording,
        permissions=list(permissions) if permissions is not None else None,
    )
    REGISTRY.targets[name] = declared
    return declared


def secret(name: str, *, from_env: str) -> Secret:
    if name in REGISTRY.secrets:
        raise ValueError(f"duplicate secret {name!r}")
    declared = Secret(name=name, from_env=from_env)
    REGISTRY.secrets[name] = declared
    return declared


def input_file(name: str, path: str) -> str:
    """Declare a fixture the plan reads. Validation checks it exists and is in the spec dir."""
    REGISTRY.inputs[name] = path
    return path


def background(
    name: str,
    *,
    cmd: str,
    ready_url: str | None = None,
    ready_cmd: str | None = None,
    ready_contains: str = "",
    cwd: str | None = None,
    timeout: float = 30.0,
) -> None:
    """Declare a daemon the runner starts before the first scenario and stops after the last.

    Readiness is `ostler`'s to poll, not the scenario's — it is what a scenario is entitled
    to assume, and a scenario that has to wait for its own stack turns a startup failure
    into a product failure. Give it a URL that must answer 200, or a command whose stdout
    must contain `ready_contains`.
    """
    entry: dict[str, Any] = {"name": name, "cmd": cmd, "timeout": timeout}
    if ready_url:
        entry["ready_check"] = ready_url
    elif ready_cmd:
        entry["ready_check"] = {"cmd": ready_cmd, "assert_contains": ready_contains}
    if cwd:
        entry["cwd"] = cwd
    REGISTRY.background.append(entry)


def scenario(
    *,
    target: Target | str,
    mechanism: str,
    covers: Sequence[str] = (),
    id: str | None = None,  # noqa: A002 - `id` is the field name everywhere else in QA
    preconditions: Sequence[str] = (),
    checkpoints: Sequence[str] = (),
    forbid: Sequence[str] = (),
    timeout: float | None = None,
) -> Callable[[FunctionType], FunctionType]:
    """Register a scenario function.

    `covers` is the machine-checkable link to the OKF obligations and acceptance criteria
    this scenario proves; `ostler qa validate` set-diffs it against the story's obligation
    packet and fails closed on anything uncovered. It is the one declaration that cannot
    move into the body — validation happens before anything runs.
    """
    if mechanism not in MECHANISMS:
        raise ValueError(f"mechanism must be one of {MECHANISMS}, got {mechanism!r}")
    target_name = target.name if isinstance(target, Target) else target

    def decorate(func: FunctionType) -> FunctionType:
        scenario_id = id or func.__name__.replace("_", "-")
        if any(existing.id == scenario_id for existing in REGISTRY.scenarios):
            raise ValueError(f"duplicate scenario id {scenario_id!r}")
        REGISTRY.scenarios.append(
            ScenarioDecl(
                id=scenario_id,
                function=func.__name__,
                target=target_name,
                mechanism=mechanism,
                covers=list(covers),
                objective=inspect.cleandoc(func.__doc__ or ""),
                preconditions=list(preconditions),
                checkpoints=list(checkpoints),
                forbid=list(forbid),
                timeout=timeout,
                line=_definition_line(func),
                func=func,
            )
        )
        return func

    return decorate


def _definition_line(func: Callable[..., None]) -> int:
    try:
        return inspect.getsourcelines(func)[1]
    except (OSError, TypeError):
        return 0


# --------------------------------------------------------------------------------------
# The record stream
# --------------------------------------------------------------------------------------


class _Recorder:
    """Writes JSONL records to `RECORD_FD`, or nowhere when the fd is not open.

    A closed fd is the normal case under `describe` and under a scenario a developer runs
    by hand with plain `python qa_plan.py`; dropping the records is what makes that work
    without a special mode.
    """

    def __init__(self, fd: int | None = None) -> None:
        if fd is None:
            fd = int(os.environ.get(RECORD_FD_ENV, RECORD_FD))
        try:
            self._stream: Any = os.fdopen(os.dup(fd), "w", encoding="utf-8")
        except OSError:
            self._stream = None

    def emit(self, record: Mapping[str, Any]) -> None:
        if self._stream is None:
            return
        self._stream.write(json.dumps(record, default=str) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


# --------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse the body as JSON, naming the URL and a body excerpt when it is not.

        `json.JSONDecodeError`'s own message is `Expecting value: line 1 column 1`, which
        in a QA log is indistinguishable between "the server returned HTML" and "the
        server returned nothing at all".
        """
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self.url} returned {self.status} with a body that is not JSON: "
                f"{self.text[:200]!r}"
            ) from exc


class Http:
    """A small stdlib HTTP client bound to a target's `base_url`.

    Loud by default: any status outside `expect_status` raises `HttpError` carrying the
    body. That is the `curl -fsS` behaviour every shell scenario had to remember to ask
    for, made the default — a scenario that means to assert a 404 says so, and one that
    did not mean to get a 500 finds out on the line that caused it.
    """

    def __init__(self, base_url: str | None, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.headers: dict[str, str] = {}

    def url_for(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if not self.base_url:
            raise ValueError(
                f"{path!r} is relative but the target declares no base_url; pass an "
                "absolute URL or set base_url= on the target"
            )
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        expect_status: int | Sequence[int] | None = None,
        timeout: float | None = None,
    ) -> Response:
        url = self.url_for(path)
        merged = {**self.headers, **(headers or {})}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, method=method.upper())  # noqa: S310
        for key, value in merged.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=timeout or self.timeout
            ) as raw:
                response = Response(raw.status, dict(raw.headers), raw.read(), url)
        except urllib.error.HTTPError as exc:
            response = Response(exc.code, dict(exc.headers or {}), exc.read(), url)
        except urllib.error.URLError as exc:
            raise HttpError(f"{method.upper()} {url} could not connect: {exc.reason}") from exc
        allowed = _allowed_statuses(expect_status)
        if allowed is None:
            if response.status >= 400:
                raise HttpError(
                    f"{method.upper()} {url} returned {response.status}: {response.text[:500]}"
                )
        elif response.status not in allowed:
            raise HttpError(
                f"{method.upper()} {url} returned {response.status}, expected "
                f"{sorted(allowed)}: {response.text[:500]}"
            )
        return response

    def get(self, path: str, **kwargs: Any) -> Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Response:
        return self.request("DELETE", path, **kwargs)


def _allowed_statuses(expect_status: int | Sequence[int] | None) -> set[int] | None:
    if expect_status is None:
        return None
    if isinstance(expect_status, int):
        return {expect_status}
    return set(expect_status)


# --------------------------------------------------------------------------------------
# The scenario-facing object
# --------------------------------------------------------------------------------------


class Qa:
    """Everything a scenario is given. One instance per scenario process.

    `dir` is the single most important attribute: the evidence directory, already
    resolved against `--out-dir`. Under YAML the same relative string meant the spec
    directory under `out:` and the repo root inside `cmd:`, and one run lost 38 of 66
    assertions to that. Here there is one spelling and it is a `Path`.
    """

    def __init__(
        self,
        *,
        scenario_id: str,
        target: Target,
        root: Path,
        spec_dir: Path,
        qa_dir: Path,
        covers: Sequence[str],
        recorder: _Recorder,
    ) -> None:
        self.scenario_id = scenario_id
        self.target = target
        self.root = root
        self.spec_dir = spec_dir
        self.dir = qa_dir
        self.covers = list(covers)
        self.http = Http(target.base_url)
        self._recorder = recorder
        self._captures: dict[str, str] = {}
        self._index = 0
        self.assertions = 0
        self.failures = 0
        self.page: Any = None

    # -- assertions --------------------------------------------------------------------

    def check(
        self,
        label: str,
        condition: Any,
        *,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> bool:
        """Record one claim about behaviour. Returns the verdict; never raises.

        Use it when the scenario can keep going and prove more after a failure — several
        independent claims about the same response, say. `require` is the one that stops.
        """
        return self._record(label, condition, actual, expected, covers)

    def require(
        self,
        label: str,
        condition: Any,
        *,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> None:
        """Record one claim and stop the scenario when it does not hold."""
        if not self._record(label, condition, actual, expected, covers):
            raise CheckFailed(label)

    def _record(
        self,
        label: str,
        condition: Any,
        actual: Any,
        expected: Any,
        covers: Sequence[str] | None,
    ) -> bool:
        passed = bool(condition)
        self._index += 1
        self.assertions += 1
        if not passed:
            self.failures += 1
        self._recorder.emit(
            {
                "type": "assert",
                "id": f"{self.scenario_id}-{self._index}",
                "label": label,
                "passed": passed,
                "actual": actual,
                "expected": expected,
                "covers": list(covers) if covers is not None else self.covers,
            }
        )
        return passed

    # -- steps -------------------------------------------------------------------------

    @contextmanager
    def step(self, label: str) -> Iterator[None]:
        """Group the work of one phase under a named step record in the ledger."""
        self._index += 1
        step_id = f"{self.scenario_id}-step-{self._index}"
        self._recorder.emit({"type": "step_start", "id": step_id, "label": label})
        try:
            yield
        except BaseException as exc:
            self._recorder.emit(
                {"type": "step_end", "id": step_id, "label": label, "failed": True, "error": repr(exc)}
            )
            raise
        self._recorder.emit({"type": "step_end", "id": step_id, "label": label, "failed": False})

    # -- evidence ----------------------------------------------------------------------

    def capture(self, key: str, value: Any) -> None:
        """Publish a value into the run ledger so a later report can name it."""
        self._captures[key] = str(value)
        self._recorder.emit({"type": "capture", "key": key, "value": str(value)})

    def get(self, key: str) -> str:
        return self._captures[key]

    def artifact(self, path: str | Path, *, kind: str) -> Path:
        """Register a file as evidence. Relative paths resolve inside `qa.dir`."""
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.dir / resolved
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._recorder.emit({"type": "artifact", "path": str(resolved), "kind": kind})
        return resolved

    def secret(self, name: str) -> str:
        declared = REGISTRY.secrets.get(name)
        if declared is None:
            raise KeyError(f"secret {name!r} is not declared in this plan")
        return declared.get()


# --------------------------------------------------------------------------------------
# describe
# --------------------------------------------------------------------------------------

#: The methods on `qa` that append an assertion record. A scenario claiming coverage and
#: calling none of them proves nothing, and unlike shell that is now statically visible.
CHECK_METHODS = frozenset({"check", "require"})


def count_checks(source: str) -> dict[str, int]:
    """How many `qa.check` / `qa.require` calls each top-level function contains.

    Static, by `ast`, and that is the point: the YAML format could only be defended by
    `_exit_sentinel`, a regex guessing whether a shell string proved anything. Here the
    question "does this scenario assert" has an actual answer before anything runs.

    Counts calls nested in loops, `with` blocks and helper branches, because the walk is
    over the whole function body — but not calls in a helper the scenario *calls*, which
    is why zero is a finding and one is not a promise.
    """
    counts: dict[str, int] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        counts[node.name] = sum(
            1
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in CHECK_METHODS
        )
    return counts


def _describe(module_path: Path) -> dict[str, Any]:
    _load(module_path)
    data = REGISTRY.as_json()
    counts = count_checks(module_path.read_text(encoding="utf-8"))
    for declared in data["scenarios"]:
        declared["checks"] = counts.get(declared["function"], 0)
    return data


def _load(module_path: Path) -> None:
    """Import the plan module by path, with its own directory importable.

    A plan sitting beside helper modules in the same spec directory should be able to
    import them; nothing else about the project's layout is assumed.
    """
    import importlib.util

    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("qa_plan", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{module_path} is not an importable Python module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["qa_plan"] = module
    spec.loader.exec_module(module)


# --------------------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------------------


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
    )
    status, error = "passed", None
    try:
        declared.func(qa)
    except CheckFailed:
        status = "failed"
    except BaseException:  # noqa: BLE001 - the traceback is the scenario's verdict
        status, error = "errored", traceback.format_exc()
        # Also to stdout, which ostler keeps as an artifact. The record carries the same
        # text, but a person debugging a red scenario opens the output file — and finding it
        # empty is what sends them to re-run the scenario by hand to see the exception.
        print(error, file=sys.stdout)
    if qa.failures:
        status = "failed" if status == "passed" else status
    # A scenario that claims coverage and recorded nothing has proved nothing. Reporting it
    # as passed is exactly the vacuity this format exists to end, so it is a failure here
    # rather than a reviewer's job four laps later.
    if status == "passed" and qa.assertions == 0 and declared.covers:
        status = "failed"
        error = (
            f"scenario {declared.id!r} claims coverage of {sorted(declared.covers)} but "
            "recorded no assertion — call qa.check() on something the behaviour produced"
        )
    recorder.emit(
        {
            "type": "scenario",
            "id": declared.id,
            "status": status,
            "assertions": qa.assertions,
            "failures": qa.failures,
            "error": error,
        }
    )
    recorder.close()
    return 0 if status == "passed" else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: ostler_qa (describe <module> | run <module> <scenario>)")
    mode, args = args[0], args[1:]
    if mode == "describe":
        json.dump(_describe(Path(args[0]).resolve()), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if mode == "run":
        module_path, scenario_id = Path(args[0]).resolve(), args[1]
        context = json.loads(args[2]) if len(args) > 2 else {}
        return _run(module_path, scenario_id, context)
    raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    # `python -m ostler_qa` binds this file to `__main__`, so a plan's own
    # `from ostler_qa import scenario` would import a *second* copy — with a second,
    # empty REGISTRY, and a describe that reports no scenarios at all. Alias the name to
    # the running module before any plan is imported.
    sys.modules.setdefault("ostler_qa", sys.modules["__main__"])
    raise SystemExit(main())
