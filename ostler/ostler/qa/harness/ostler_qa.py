"""The QA scenario harness: what a `qa_plan.py` imports, and what runs it."""

from __future__ import annotations

import ast
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import FunctionType
from typing import Any

__all__ = [
    "MISSING",
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
    "tool_env",
]

RECORD_FD = 3

RECORD_FD_ENV = "OSTLER_QA_RECORD_FD"

RECORD_PATH_ENV = "OSTLER_QA_RECORD_PATH"

_SHELL = shutil.which("bash") or "/bin/sh"

_NODE_REF = re.compile(r"(?<![\w.])@([a-zA-Z0-9][a-zA-Z0-9_-]*)\.([a-zA-Z0-9][a-zA-Z0-9_-]*)")
_CAPTURE_REF = re.compile(r"(?<![\w.])\$([a-zA-Z0-9][a-zA-Z0-9_-]*)")

MECHANISMS = ("live", "fixture")


@dataclass(frozen=True)
class DriverSpec:
    """A driver's declared observation channels — a capability, not a bare name."""
    name: str
    observes: frozenset[str]


DRIVERS = (
    DriverSpec("python", frozenset({"response", "body", "subject"})),
    DriverSpec("playwright", frozenset({"page", "response", "body", "keyboard"})),
    DriverSpec("maestro", frozenset({"page", "subject"})),
)
DRIVER_NAMES = tuple(driver.name for driver in DRIVERS)

UI_DRIVERS = tuple(driver for driver in DRIVERS if driver.name in ("playwright", "maestro"))
UI_DRIVER_NAMES = tuple(driver.name for driver in UI_DRIVERS)

DEVICE_LAYOUT_SCHEMA = "device-layout/1"

DEFAULT_HTTP_TIMEOUT = 30.0

DEFAULT_EVENTUALLY_TIMEOUT = 5.0
EVENTUALLY_INTERVAL = 0.1

_PROCESS_START = time.monotonic()


class HttpError(RuntimeError):
    """A response whose status the scenario did not say it expected."""


class CheckFailed(AssertionError):
    """A `qa.require` that did not hold."""




@dataclass
class Target:
    name: str
    driver: str = "python"
    interpreter: str | None = None
    base_url: str | None = None
    app_id: str | None = None
    browser: str | None = None
    viewport: dict[str, int] | None = None
    recording: dict[str, Any] | None = None
    permissions: list[str] | None = None

    def as_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"driver": self.driver}
        for key in ("interpreter", "base_url", "app_id", "browser", "viewport", "permissions"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.recording is not None:
            data["recording"] = self.recording
        return data


@dataclass
class Secret:
    """A value the runner injects from its own side and redacts from the ledger."""

    name: str
    from_env: str | None = None
    from_file: str | None = None

    @property
    def source(self) -> str:
        if self.from_env is not None:
            return f"${self.from_env}"
        return f"file {self.from_file}"

    def as_json(self) -> dict[str, str]:
        if self.from_env is not None:
            return {"from_env": self.from_env}
        return {"from_file": str(self.from_file)}

    def get(self) -> str:
        value = os.environ.get(self.name)
        if value is None:
            raise KeyError(
                f"secret {self.name!r} is not set in the scenario environment; the runner "
                f"injects it from {self.source}"
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
    restart: list[str] = field(default_factory=list)
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
        for key in ("preconditions", "checkpoints", "forbid", "restart"):
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
    book: str = ""
    targets: dict[str, Target] = field(default_factory=dict)
    secrets: dict[str, Secret] = field(default_factory=dict)
    inputs: dict[str, str] = field(default_factory=dict)
    background: list[dict[str, Any]] = field(default_factory=list)
    tool_env: list[str] = field(default_factory=list)
    scenarios: list[ScenarioDecl] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "version": 3,
            "run_id": self.run_id,
            "story": self.story,
            "book": self.book,
            "inputs": dict(self.inputs),
            "secrets": {name: s.as_json() for name, s in self.secrets.items()},
            "targets": {name: t.as_json() for name, t in self.targets.items()},
            "background": list(self.background),
            "tool_env": list(self.tool_env),
            "scenarios": [s.as_json() for s in self.scenarios],
        }


REGISTRY = _Registry()


def plan(*, run_id: str, story: str, book: str = "") -> None:
    """Name the run and the story."""
    if REGISTRY.run_id:
        raise ValueError("plan() was already called; a module declares one run")
    REGISTRY.run_id, REGISTRY.story, REGISTRY.book = run_id, story, book


def target(
    name: str,
    *,
    driver: str = "python",
    interpreter: str | None = None,
    base_url: str | None = None,
    app_id: str | None = None,
    browser: str | None = None,
    viewport: Mapping[str, int] | None = None,
    recording: dict[str, Any] | None = None,
    permissions: Sequence[str] | None = None,
) -> Target:
    if driver not in DRIVER_NAMES:
        raise ValueError(f"target {name!r} has unknown driver {driver!r}; one of {DRIVER_NAMES}")
    if name in REGISTRY.targets:
        raise ValueError(f"duplicate target {name!r}")
    declared = Target(
        name=name,
        driver=driver,
        interpreter=interpreter,
        base_url=base_url,
        app_id=app_id,
        browser=browser,
        viewport=dict(viewport) if viewport is not None else None,
        recording=recording,
        permissions=list(permissions) if permissions is not None else None,
    )
    REGISTRY.targets[name] = declared
    return declared


def secret(name: str, *, from_env: str | None = None, from_file: str | None = None) -> Secret:
    """Declare a secret by its source — exactly one of `from_env` or `from_file`."""
    if name in REGISTRY.secrets:
        raise ValueError(f"duplicate secret {name!r}")
    if (from_env is None) == (from_file is None):
        raise ValueError(f"secret {name!r} needs exactly one of from_env= or from_file=")
    declared = Secret(name=name, from_env=from_env, from_file=from_file)
    REGISTRY.secrets[name] = declared
    return declared


_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def tool_env(*names: str) -> None:
    """Declare the environment variable names a scenario may set on a `qa.tool(...).run`."""
    for name in names:
        if not isinstance(name, str) or not _ENV_NAME.match(name):
            raise ValueError(f"tool_env name {name!r} must match [A-Z_][A-Z0-9_]*")
        if name in REGISTRY.tool_env:
            raise ValueError(f"duplicate tool_env name {name!r}")
        REGISTRY.tool_env.append(name)


def input_file(name: str, path: str) -> str:
    """Declare a fixture the plan reads."""
    REGISTRY.inputs[name] = path
    return path


def background(
    name: str,
    *,
    argv: Sequence[str],
    reset_paths: Sequence[str] = (),
    ready_url: str | None = None,
    ready_method: str = "GET",
    ready_status: int = 200,
    cwd: str | None = None,
    timeout: float = 30.0,
) -> None:
    """Declare a daemon the runner starts before the first scenario and stops after the last."""
    entry: dict[str, Any] = {
        "name": name,
        "argv": list(argv),
        "reset_paths": list(reset_paths),
        "timeout": timeout,
    }
    if ready_url:
        entry["ready_check"] = (
            ready_url
            if ready_method == "GET" and ready_status == 200
            else {"url": ready_url, "method": ready_method, "status": ready_status}
        )
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
    restart: Sequence[str] = (),
    timeout: float | None = None,
) -> Callable[[FunctionType], FunctionType]:
    """Register a scenario function."""
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
                restart=list(restart),
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




class _Recorder:
    """Writes JSONL records to a path, to `RECORD_FD`, or nowhere."""

    def __init__(self, fd: int | None = None) -> None:
        self._stream: Any = None
        path = os.environ.get(RECORD_PATH_ENV)
        if fd is None and path:
            try:
                self._stream = open(path, "a", encoding="utf-8")  # noqa: SIM115
            except OSError:
                self._stream = None
            return
        if fd is None:
            fd = int(os.environ.get(RECORD_FD_ENV, RECORD_FD))
        try:
            self._stream = os.fdopen(os.dup(fd), "w", encoding="utf-8")
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
        """Parse the body as JSON, naming the URL and a body excerpt when it is not."""
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self.url} returned {self.status} with a body that is not JSON: "
                f"{self.text[:200]!r}"
            ) from exc


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turns a 3xx response into an `HTTPError` instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


class Http:
    """A small stdlib HTTP client bound to a target's `base_url`."""

    def __init__(
        self,
        base_url: str | None,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
        on_unexpected_status: Callable[[str, str, int, Sequence[int]], None] | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.headers: dict[str, str] = {}
        self._on_unexpected_status = on_unexpected_status

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
        follow_redirects: bool = True,
    ) -> Response:
        url = self.url_for(path)
        merged = {**self.headers, **(headers or {})}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, method=method.upper())  # noqa: S310
        for key, value in merged.items():
            request.add_header(key, value)
        opener_open = _NO_REDIRECT_OPENER.open if not follow_redirects else urllib.request.urlopen
        try:
            with opener_open(  # noqa: S310
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
            if self._on_unexpected_status is not None:
                self._on_unexpected_status(method.upper(), url, response.status, sorted(allowed))
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




def _not_yet(exc: BaseException) -> bool:
    """Does this exception mean "the page has not got there yet", or "the plan is wrong"?"""
    if isinstance(exc, CheckFailed):
        return False
    return isinstance(exc, (TimeoutError, AssertionError)) or type(exc).__module__.split(".")[
        0
    ] == "playwright"


def _sampled(actual: Any) -> Any:
    """Read an `actual=` that may be a callable, after the poll loop has settled."""
    if not callable(actual):
        return actual
    try:
        return actual()
    except BaseException as exc:  # noqa: BLE001 — evidence, not a verdict
        return repr(exc)



_MISSING = object()


def _observed_status(observed: Any) -> tuple[int, Any]:
    """The status code and parsed body of whatever a scenario handed over as a response."""
    if isinstance(observed, int) and not isinstance(observed, bool):
        return observed, None
    status = getattr(observed, "status", getattr(observed, "status_code", None))
    if not isinstance(status, int):
        raise TypeError(
            "http_status observes a response — pass the object qa.http returned (or its "
            f"integer status), not {type(observed).__name__}"
        )
    body: Any = None
    reader = getattr(observed, "json", None)
    if callable(reader):
        try:
            body = reader()
        except Exception:  # noqa: BLE001 — a non-JSON body is not a scenario defect
            body = None
    return status, body


def _pair(observed: Any, check: str) -> tuple[Any, Any]:
    """The before/after a differential check needs, insisted on rather than inferred."""
    if isinstance(observed, (tuple, list)) and len(observed) == 2:
        return observed[0], observed[1]
    raise TypeError(
        f"{check} observes a change — pass `(before, after)`, the two reads it compares, "
        f"not {type(observed).__name__}"
    )


def _paths(value: Any, prefix: str = "") -> dict[str, Any]:
    """Every leaf of a JSON-ish value, keyed by its dotted path."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_paths(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        out = {}
        for index, item in enumerate(value):
            out.update(_paths(item, f"{prefix}[{index}]"))
        return out
    return {prefix: value}


class _Wild:
    """The `[*]` segment: every element of a list, every value of an object."""

    def __repr__(self) -> str:
        return "[*]"


WILD = _Wild()


@dataclass(frozen=True)
class Filter:
    """The `[?(@.key==value)]` segment: the elements whose `key` holds `value`."""

    key: str
    value: Any

    def __repr__(self) -> str:
        return f"[?(@.{self.key}=={json.dumps(self.value)})]"


PathStep = str | int | _Wild | Filter

_FILTER = re.compile(
    r"\[\?\(@\.(?P<key>[^=\s)]+)\s*==\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?|true|false|null)\s*\)\]"
)


def path_steps(path: str) -> list[PathStep]:
    """The segments of a path, in the one grammar every reader of a document path shares."""
    steps: list[PathStep] = []
    text = path.strip()
    if text.startswith("$"):
        text = text[1:]
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == ".":
            pos += 1
            continue
        if char == "[":
            if text.startswith("[*]", pos):
                steps.append(WILD)
                pos += 3
                continue
            hit = _FILTER.match(text, pos)
            if hit is not None:
                steps.append(Filter(hit.group("key"), json.loads(hit.group("value").replace("'", '"'))))
                pos = hit.end()
                continue
            close = text.find("]", pos)
            if close == -1:
                raise ValueError(f"json path {path!r}: '[' at {pos} is never closed")
            inner = text[pos + 1 : close]
            steps.append(int(inner) if inner.isdigit() else inner)
            pos = close + 1
            continue
        nxt = len(text)
        for stop in (".", "["):
            found = text.find(stop, pos)
            if found != -1:
                nxt = min(nxt, found)
        steps.append(text[pos:nxt])
        pos = nxt
    return steps


def _step_into(current: Any, step: str | int) -> tuple[bool, Any]:
    if isinstance(current, Mapping):
        key = str(step) if isinstance(step, int) else step
        return (True, current[key]) if key in current else (False, None)
    if isinstance(current, (list, tuple)):
        if isinstance(step, int):
            index = step
        elif step.isdigit():
            index = int(step)
        else:
            return False, None
        return (True, current[index]) if index < len(current) else (False, None)
    return False, None


def _selected(current: Any, step: _Wild | Filter) -> list[Any]:
    if isinstance(current, Mapping):
        candidates = list(current.values())
    elif isinstance(current, (list, tuple)):
        candidates = list(current)
    else:
        return []
    if isinstance(step, _Wild):
        return candidates
    chosen = []
    for item in candidates:
        ok, held = resolve_path(item, step.key)
        if ok and _scalar_equal(held, step.value):
            chosen.append(item)
    return chosen


def resolve_path(document: Any, path: str) -> tuple[bool, Any]:
    """Walk `path` into `document`: whether it resolved, and to what."""
    steps = path_steps(path)
    current: Any = document
    projected = False
    for step in steps:
        if isinstance(step, (_Wild, Filter)):
            if projected:
                current = [item for element in current for item in _selected(element, step)]
            else:
                current = _selected(current, step)
                projected = True
            continue
        if projected:
            kept = []
            for element in current:
                ok, value = _step_into(element, step)
                if ok:
                    kept.append(value)
            current = kept
            continue
        ok, current = _step_into(current, step)
        if not ok:
            return False, None
    if projected:
        return bool(current), current
    return True, current


def _resolve_path(document: Any, path: str) -> tuple[bool, Any]:
    """`resolve_path`, under the name the verifiers grew up calling it."""
    return resolve_path(document, path)


def _is_projection(path: str) -> bool:
    return any(isinstance(step, (_Wild, Filter)) for step in path_steps(path))


def _verify_http_status(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    status, body = _observed_status(observed)
    expected: Any = {"code": args["code"]}
    actual: Any = {"code": status}
    passed = status == args["code"]
    if "title" in args:
        found = body.get("title") if isinstance(body, dict) else None
        expected["title"], actual["title"] = args["title"], found
        passed = passed and found == args["title"]
    if "path" in args:
        url = getattr(observed, "url", None)
        if not isinstance(url, str):
            raise TypeError(
                "http_status(path=…) observes which request answered — pass the object "
                f"qa.http returned, not {type(observed).__name__}"
            )
        route = urllib.parse.urlsplit(url).path
        expected["path"], actual["path"] = args["path"], route
        passed = passed and route == args["path"]
    return passed, actual, expected


def _scalar_equal(observed: Any, expected: Any) -> bool:
    """`json_path(equals=)` against what the document holds, typed the way JSON types it."""
    if isinstance(expected, bool) or isinstance(observed, bool):
        return isinstance(observed, bool) and isinstance(expected, bool) and observed is expected
    if isinstance(expected, (int, float)):
        return isinstance(observed, (int, float)) and observed == expected
    if isinstance(expected, str):
        return isinstance(observed, str) and observed == expected
    return False


def _matchable(value: Any) -> str:
    """*value* rendered the way a `json_path(matches=...)` pattern is written against."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _verify_json_path(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    resolved, value = _resolve_path(observed, args["path"])
    if "absent" in args:
        want_absent = bool(args["absent"])
        return resolved is not want_absent, {"present": resolved}, {"present": not want_absent}
    if not resolved:
        return False, {"present": False}, {"path": args["path"]}
    if _is_projection(args["path"]):
        if len(value) != 1:
            return False, {"selected": value}, {"selected": "exactly one"}
        value = value[0]
    if "equals" in args:
        return _scalar_equal(value, args["equals"]), value, args["equals"]
    if "matches" in args:
        return (re.search(args["matches"], _matchable(value)) is not None, value,
                f"~ {args['matches']}")
    return False, value, "equals=, matches= or absent=true — presence asserts nothing"


def _verify_unchanged(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    before, after = _pair(observed, "unchanged")
    allowed = set(args.get("except_fields", []))
    before_paths, after_paths = _paths(before), _paths(after)
    changed = sorted(
        {
            path
            for path in before_paths.keys() | after_paths.keys()
            if before_paths.get(path, _MISSING) != after_paths.get(path, _MISSING)
        }
        - allowed
    )
    return not changed, {"changed": changed}, {"changed": []}


def _verify_keys_unchanged(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    before, after = _pair(observed, "keys_unchanged")
    gone = sorted(_paths(before).keys() - _paths(after).keys())
    added = sorted(_paths(after).keys() - _paths(before).keys())
    return not gone and not added, {"removed": gone, "added": added}, {"removed": [], "added": []}


def _verify_count(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """How many of `subject` there are — the subject resolved, not taken on trust."""
    document: Any = observed
    reader = getattr(document, "json", None)
    if callable(reader):
        document = reader()
    if isinstance(document, Mapping):
        resolved, document = _resolve_path(document, args["subject"])
        if not resolved:
            return False, {"subject": args["subject"], "present": False}, args["equals"]
    if isinstance(document, bool):
        return False, {"subject": args["subject"], "countable": False}, args["equals"]
    found = document if isinstance(document, int) else len(document)
    return found == args["equals"], found, args["equals"]


def _empty(value: Any) -> bool:
    """Nothing there: `None`, or a sized thing with nothing in it."""
    return value is None or (hasattr(value, "__len__") and len(value) == 0)


def _verify_absent(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    return _empty(observed), observed, "absent"


def _verify_created(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Absent before the action, present after — both halves, or it proves nothing."""
    before, after = _pair(observed, "created")
    was_absent, is_present = _empty(before), not _empty(after)
    return (
        was_absent and is_present,
        {"before": before, "after": after},
        {"before": "absent", "after": "present"},
    )


def _verify_removed(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Present before the action, absent after — the mirror of `created`, and for the mirror reason: absence afterwards alone passes on a subject that was never there."""
    before, after = _pair(observed, "removed")
    return (
        not _empty(before) and _empty(after),
        {"before": before, "after": after},
        {"before": "present", "after": "absent"},
    )


def _readings(observed: Any) -> list[str]:
    """Every spelling of an element's text the page can offer, rendered first."""
    readings: list[str] = []
    for reader in ("inner_text", "text_content"):
        read = getattr(observed, reader, None)
        if read is None:
            continue
        value = read()
        if value is not None and str(value) not in readings:
            readings.append(str(value))
    return readings


def _verify_visible(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    if hasattr(observed, "is_visible"):
        shown = bool(observed.is_visible())
        readings = _readings(observed) if shown and "text" in args else []
    else:
        shown = bool(observed)
        readings = [str(observed)] if "text" in args and observed is not None else []
    if "text" not in args:
        return shown, {"visible": shown}, {"visible": True}
    text = readings[0] if readings else None
    contains = shown and any(args["text"] in reading for reading in readings)
    return contains, {"visible": shown, "text": text}, {"visible": True, "text": args["text"]}


def _enabled(observed: Any, check: str) -> bool:
    """Whether the product will let a user act on this control."""
    if not hasattr(observed, "is_enabled"):
        raise TypeError(
            f"{check} observes whether a control accepts the action — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    return bool(observed.is_enabled())


def _verify_actionable(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    usable = _enabled(observed, "actionable")
    return usable, {"actionable": usable}, {"actionable": True}


def _verify_inert(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    usable = _enabled(observed, "inert")
    return not usable, {"actionable": usable}, {"actionable": False}


def _verify_focusable(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Reachable by a real keypress, and — when `activates` names one — responsive to it."""
    if not hasattr(observed, "focus"):
        raise TypeError(
            f"focusable observes a control through real keyboard focus — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    observed.focus()
    focused = bool(observed.evaluate("el => el === document.activeElement"))
    if "activates" not in args:
        return focused, {"focused": focused}, {"focused": True}
    if not focused:
        return False, {"focused": False, "activated": False}, {"focused": True, "activated": True}
    observed.evaluate(
        "el => { el.__ostlerActivated = false; "
        "el.addEventListener('click', () => { el.__ostlerActivated = true; }, {once: true}); }"
    )
    observed.page.keyboard.press(args["activates"])
    activated = bool(observed.evaluate("el => el.__ostlerActivated === true"))
    return (
        activated,
        {"focused": True, "activated": activated},
        {"focused": True, "activated": True},
    )


def _verify_persists(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    written, reread = _pair(observed, "persists")
    return reread is not None and reread == written, reread, written


def _verify_emitted(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    found = len(observed)
    if "count" in args:
        return found == args["count"], found, args["count"]
    return found > 0, found, "at least one"


def _verify_omits(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """What the subject must not carry — the one assertion the rest of the vocabulary cannot make."""
    document = observed
    reader = getattr(document, "json", None)
    if callable(reader):
        try:
            document = reader()
        except Exception:  # noqa: BLE001 — a non-JSON body is still searchable as text
            document = getattr(observed, "text", observed)
    if isinstance(document, Mapping):
        resolved, value = _resolve_path(document, args["subject"])
        if resolved:
            document = value
    haystack = document if isinstance(document, str) else _rendered(document)
    found: list[str] = []
    if "text" in args and args["text"] in haystack:
        found.append(args["text"])
    if "matches" in args:
        hit = re.search(args["matches"], haystack)
        if hit is not None:
            found.append(hit.group(0))
    return not found, {"found": found}, {"found": []}


def _rendered(document: Any) -> str:
    """Everything the subject carries, as one string to search."""
    try:
        return json.dumps(document, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(document)


def _verify_exit_status(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """The process ended the way the book says it does."""
    code = getattr(observed, "exit_code", None)
    if isinstance(code, bool) or not isinstance(code, int):
        raise TypeError(
            "exit_status observes a tool or maestro result (something with an exit_code), "
            f"got {type(observed).__name__}"
        )
    return code == args["code"], code, args["code"]


def _verify_conflict_on_stale(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    status, _ = _observed_status(observed)
    return 400 <= status < 500, status, "a refusal (4xx)"


VERIFIERS: dict[str, Callable[[Any, Mapping[str, Any]], tuple[bool, Any, Any]]] = {
    "http_status": _verify_http_status,
    "json_path": _verify_json_path,
    "unchanged": _verify_unchanged,
    "keys_unchanged": _verify_keys_unchanged,
    "count": _verify_count,
    "absent": _verify_absent,
    "created": _verify_created,
    "removed": _verify_removed,
    "visible": _verify_visible,
    "actionable": _verify_actionable,
    "inert": _verify_inert,
    "focusable": _verify_focusable,
    "persists": _verify_persists,
    "emitted": _verify_emitted,
    "omits": _verify_omits,
    "exit_status": _verify_exit_status,
    "conflict_on_stale": _verify_conflict_on_stale,
}


class _Missing:
    """The value `qa.field` yields for something the product did not put there."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def __contains__(self, item: Any) -> bool:
        return False

    def __getitem__(self, key: Any) -> "_Missing":
        return self

    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("<missing>")

    def __lt__(self, other: object) -> bool:
        return False

    def __le__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False

    def __ge__(self, other: object) -> bool:
        return False


MISSING = _Missing()


@dataclass
class FixtureFault:
    """One book-fixture step that could not prove its state, classified per Q38."""

    fixture: str
    step_index: int
    step_kind: str
    fault_class: str
    detail: str


class Qa:
    """Everything a scenario is given."""

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
        offset_base_ms: int = 0,
        tools: Mapping[str, str] | None = None,
        fixtures: Mapping[str, Mapping[str, Any]] | None = None,
        book_fixtures: Mapping[str, Mapping[str, Any]] | None = None,
        tool_env: Sequence[str] = (),
    ) -> None:
        self.scenario_id = scenario_id
        self.target = target
        self.root = root
        self.spec_dir = spec_dir
        self.dir = qa_dir
        self.covers = list(covers)
        self._tool_commands = dict(tools or {})
        self._fixtures = {name: dict(spec) for name, spec in (fixtures or {}).items()}
        self._book_fixtures = {name: dict(spec) for name, spec in (book_fixtures or {}).items()}
        self._book_fixture_memo: dict[tuple[str, tuple[tuple[str, str], ...]], ToolResult] = {}
        self._node_facts: dict[str, dict[str, str]] = {}
        self._tool_env_allowed = frozenset(tool_env)
        self._recorder = recorder
        self._captures: dict[str, str] = {}
        self.http = Http(target.base_url, on_unexpected_status=self._status_mismatch)
        self._index = 0
        self.assertions = 0
        self.failures = 0
        self.vets = 0
        self.offset_base_ms = offset_base_ms
        self.page: Any = None
        self.diagnostics: Any = None
        self.maestro = Maestro(self)
        self.tesseract = Tesseract(self)
        self.convert = Convert(self)

    def tool(self, name: str) -> "Tool":
        """A user- or machine-declared external command, opted into via `agents.yml`."""
        command = self._tool_commands.get(name)
        if command is None:
            raise RuntimeError(
                f"qa tool {name!r} is not available — opt into it via this repo's "
                f"agents.yml `qa: {{tools: [{name!r}]}}`, and if it is not a built-in, "
                f"define it in ~/.config/stablemate/config.toml's [qa_tools.{name}]"
            )
        return Tool(self, name, command)

    def fixture(self, name: str, *args: str) -> "ToolResult":
        """Put the product into a state this repo declared, and write down that it happened."""
        if name in self._book_fixtures:
            return self._exec_book_fixture(name, self._parse_fixture_args(args))
        spec = self._fixtures.get(name)
        if spec is None:
            declared = ", ".join(sorted(self._fixtures)) or "(none declared)"
            raise RuntimeError(
                f"qa fixture {name!r} is not declared — add it to this repo's agents.yml "
                f"under `qa: {{fixtures: {{{name}: ...}}}}`. Declared here: {declared}"
            )
        argv = [*spec.get("args", []), *args]
        result = self.tool(str(spec["tool"])).run(*argv, timeout=float(spec.get("timeout", 120.0)))
        self._recorder.emit(
            {
                "kind": "fixture",
                "scenario": self.scenario_id,
                "name": name,
                "provides": spec.get("provides", ""),
                "command": result.command,
                "exit_code": result.exit_code,
                "ok": result.ok,
            }
        )
        if not result.ok:
            raise RuntimeError(
                f"qa fixture {name!r} failed (exit {result.exit_code}) and the state it "
                f"promises — {spec.get('provides', '')!r} — is not there: "
                f"{(result.stderr or result.stdout).strip()[:500]}"
            )
        return result


    @staticmethod
    def _parse_fixture_args(args: Sequence[str]) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for tok in args:
            key, _, value = tok.partition("=")
            parsed[key] = value
        return parsed

    def _resolve_ref(self, owner: str, value: str) -> str:
        """*value*, with every embedded `@node.key` and `$name` reference substituted."""
        failures: list[str] = []
        spans: list[tuple[int, int, str]] = []
        for match in _NODE_REF.finditer(value):
            node, key = match.group(1), match.group(2)
            facts = self._node_facts.get(node)
            if facts is None or key not in facts:
                detail = (
                    f"reference @{node}.{key} has no resolved value — "
                    f"{node!r} has not run (or does not provide {key!r})"
                )
                self._fault(owner, -1, "reference", "defect", detail)
                failures.append(detail)
                continue
            spans.append((match.start(), match.end(), facts[key]))
        for match in _CAPTURE_REF.finditer(value):
            captured = match.group(1)
            if captured not in self._captures:
                detail = f"reference ${captured} has no resolved value — nothing has captured it"
                self._fault(owner, -1, "reference", "defect", detail)
                failures.append(detail)
                continue
            spans.append((match.start(), match.end(), self._captures[captured]))
        if failures:
            raise RuntimeError(f"qa {owner!r}: " + "; ".join(failures))
        spans.sort(key=lambda span: span[0])
        out: list[str] = []
        cursor = 0
        for start, end, replacement in spans:
            out.append(value[cursor:start])
            out.append(replacement)
            cursor = end
        out.append(value[cursor:])
        return "".join(out)

    def resolve(self, value: str) -> str:
        """A scenario's own value, with every embedded `@node.key`/`$name` substituted."""
        return self._resolve_ref(self.scenario_id, value)

    def _resolve_value(self, value: Any) -> Any:
        """`resolve()`, recursively, for a JSON-shaped dict/list body."""
        if isinstance(value, str):
            return self.resolve(value)
        if isinstance(value, dict):
            return {key: self._resolve_value(v) for key, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v) for v in value]
        return value

    def capture_field(self, key: str, data: Any, path: str) -> Any:
        """Capture a JSON-path read from observed data — a defect if the path finds nothing."""
        value = self.field(data, path)
        if value is MISSING:
            detail = f"capture {key!r} from {path!r} found nothing in the observed data"
            self._fault(self.scenario_id, -1, "capture", "defect", detail)
            raise RuntimeError(f"qa {self.scenario_id!r}: {detail}")
        self.capture(key, value)
        return value

    def _fault(self, fixture: str, step_index: int, step_kind: str, fault_class: str, detail: str) -> None:
        fault = FixtureFault(
            fixture=fixture, step_index=step_index, step_kind=step_kind,
            fault_class=fault_class, detail=detail,
        )
        self._recorder.emit({"type": "fixture_fault", **asdict(fault)})

    @property
    def scenario_dir(self) -> Path:
        """This scenario's own directory under `self.dir`, created on demand."""
        resolved = (self.dir.resolve() / self.scenario_id).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def _run_book_step(
        self, fixture: str, index: int, step: Mapping[str, Any], env: Mapping[str, str],
    ) -> "ToolResult":
        kind = str(step.get("kind", ""))
        command = str(step.get("command", ""))
        cwd = str(self.scenario_dir) if step.get("cwd-frame") == "scenario" else str(step.get("cwd") or self.root)
        timeout = float(step["timeout"])
        if not Path(cwd).is_dir():
            self._fault(fixture, index, kind, "environment", f"cwd {cwd!r} does not exist")
            raise RuntimeError(f"qa fixture {fixture!r} step {index} ({kind}): cwd {cwd!r} does not exist")
        argv = [_SHELL, "-c", command]
        overlay = {**os.environ, **env}
        try:
            done = subprocess.run(  # noqa: S603 - fixed shell invocation of a book-declared recipe
                argv, cwd=cwd, env=overlay, capture_output=True, text=True, timeout=timeout, check=False,
            )
        except OSError as exc:
            self._fault(fixture, index, kind, "environment", str(exc))
            raise RuntimeError(
                f"qa fixture {fixture!r} step {index} ({kind}) could not start: {exc}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            self._fault(fixture, index, kind, "defect", f"timed out after {timeout}s")
            raise RuntimeError(
                f"qa fixture {fixture!r} step {index} ({kind}) timed out after {timeout}s"
            ) from exc
        result = ToolResult(command=argv, stdout=done.stdout, stderr=done.stderr, exit_code=done.returncode)
        if not result.ok:
            body = (result.stderr or result.stdout).strip()[:500]
            prefix = (
                f"command not found (exit {result.exit_code})"
                if result.exit_code in (126, 127)
                else f"exit {result.exit_code}"
            )
            detail = f"{prefix}: {body}"
            self._fault(fixture, index, kind, "defect", detail)
            raise RuntimeError(f"qa fixture {fixture!r} step {index} ({kind}) failed ({detail})")
        return result

    def _extract_provides(
        self,
        fixture: str,
        declared: Sequence[Mapping[str, str]],
        step_results: Mapping[str, "ToolResult"],
        last_index: int,
    ) -> dict[str, str]:
        """Bind each declared `provides:` fact the way its own entry says the fact comes to be."""
        facts: dict[str, str] = {}
        for entry in declared:
            key = entry["key"]
            step_id = entry.get("from") or ""
            asserted = entry.get("is") or ""
            if asserted and step_id:
                detail = (f"declares provides {key!r} both `from:` step {step_id!r} and `is:` "
                          f"{asserted!r} — a fact is observed or asserted, not both")
                self._fault(fixture, last_index, "provides", "defect", detail)
                raise RuntimeError(f"qa fixture {fixture!r} {detail}")
            if asserted:
                facts[key] = asserted
                continue
            if not step_id:
                detail = (f"declares provides {key!r} with neither `from:` nor `is:` — the book "
                          f"does not say whether this fact is observed from a step or asserted "
                          f"by the fixture's own construction")
                self._fault(fixture, last_index, "provides", "defect", detail)
                raise RuntimeError(f"qa fixture {fixture!r} {detail}")
            if step_id not in step_results:
                detail = f"declares provides {key!r} from step {step_id!r}, which is not one of its own steps"
                self._fault(fixture, last_index, "provides", "defect", detail)
                raise RuntimeError(f"qa fixture {fixture!r} {detail}")
            stdout = step_results[step_id].stdout
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError as exc:
                detail = f"declares provides {key!r} but its source step's stdout is not JSON"
                self._fault(fixture, last_index, "provides", "defect", detail)
                raise RuntimeError(f"qa fixture {fixture!r} {detail}") from exc
            path = entry.get("read") or key
            resolved, value = resolve_path(payload, path)
            if not resolved:
                self._fault(fixture, last_index, "provides", "defect", f"declared provides {key!r} absent")
                raise RuntimeError(f"qa fixture {fixture!r} does not provide {key!r} at {path!r}")
            facts[key] = str(value)
        return facts

    def _exec_book_fixture(self, name: str, args: Mapping[str, str]) -> "ToolResult":
        """Run one book `fixture` node's steps, memoized on `(name, frozen args)` per scenario."""
        memo_key = (name, tuple(sorted(args.items())))
        cached = self._book_fixture_memo.get(memo_key)
        if cached is not None:
            return cached
        spec = self._book_fixtures[name]
        env: dict[str, str] = {}
        secrets = spec.get("secrets", [])
        for need in spec.get("needs", []):
            if need.get("fixture") is None:
                detail = f"needs a fixture link that does not resolve ({need.get('unresolved')!r})"
                self._fault(name, -1, "needs", "defect", detail)
                raise RuntimeError(f"qa fixture {name!r} {detail}")
            self._exec_book_fixture(str(need["fixture"]), {})
            for key, value in need.get("args", {}).items():
                env[key] = self._resolve_ref(name, value)
        for secret_name in secrets:
            value = os.environ.get(secret_name)
            if value is None:
                self._fault(name, -1, "secret", "environment",
                            f"secret {secret_name!r} is not set in the harness's own environment")
                raise RuntimeError(
                    f"qa fixture {name!r} needs secret {secret_name!r}, which is not set — the "
                    "harness resolves secret values from its own environment, never the book"
                )
            env[secret_name] = value
        for arg_name in spec.get("args", []):
            if arg_name in args:
                if arg_name in secrets:
                    detail = f"arg {arg_name!r} collides with a declared secret name of the same name"
                    self._fault(name, -1, "args", "defect", detail)
                    raise RuntimeError(f"qa fixture {name!r} {detail}")
                env[arg_name] = args[arg_name]
        steps = spec.get("steps", [])
        result: ToolResult | None = None
        step_results: dict[str, ToolResult] = {}
        for index, step in enumerate(steps):
            if step.get("missing_run"):
                detail = "step has no `run:` command"
                self._fault(name, index, str(step.get("kind", "")), "defect", detail)
                raise RuntimeError(f"qa fixture {name!r} step {index}: {detail}")
            result = self._run_book_step(name, index, step, env)
            step_id = step.get("id")
            if step_id:
                step_results[step_id] = result
        self._node_facts[name] = self._extract_provides(
            name, spec.get("provides", []), step_results, len(steps) - 1
        )
        if result is None:
            result = ToolResult(command=[], stdout="", stderr="", exit_code=0)
        self._book_fixture_memo[memo_key] = result
        self._recorder.emit(
            {
                "kind": "fixture",
                "scenario": self.scenario_id,
                "name": name,
                "provides": ",".join(entry["key"] for entry in spec.get("provides", [])),
                "command": result.command,
                "exit_code": result.exit_code,
                "ok": result.ok,
            }
        )
        return result

    def instance(self, obligation: str, bindings: dict[str, object]) -> None:
        """Declare which concrete member of a repeated family this scenario exercises."""
        self._recorder.emit(
            {
                "type": "instance",
                "scenario": self.scenario_id,
                "obligation": str(obligation),
                "bindings": {str(key): str(value) for key, value in bindings.items()},
            }
        )


    def _status_mismatch(
        self, method: str, url: str, status: int, allowed: Sequence[int]
    ) -> None:
        """Write down an `expect_status` the product did not meet, before it raises."""
        self._record(
            f"{method} {url} answers {list(allowed)}",
            False,
            status,
            list(allowed),
            self.covers,
        )

    def field(self, data: Any, path: str, default: Any = MISSING) -> Any:
        """Read one value out of observed product data without ever raising."""
        try:
            resolved, value = resolve_path(data, path)
        except ValueError:
            return default
        if not resolved:
            return default
        if _is_projection(path) and len(value) == 1:
            return value[0]
        return value

    def check(
        self,
        label: str,
        condition: Any,
        *,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> bool:
        """Record one claim about behaviour."""
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

    def eventually(
        self,
        label: str,
        condition: Callable[[], Any],
        *,
        timeout: float = DEFAULT_EVENTUALLY_TIMEOUT,
        interval: float = EVENTUALLY_INTERVAL,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> bool:
        """Record one claim about behaviour that the page is allowed to arrive at."""
        if not callable(condition):
            raise TypeError(
                f"qa.eventually({label!r}, …) needs a callable to re-sample, and was handed "
                f"an already-evaluated {type(condition).__name__}. Python collapsed the read "
                "before this harness saw it, so there is nothing left to retry — hand over "
                "the sampler instead: wrap the expression you just wrote in a lambda "
                "(`lambda: page.text(\"#badge\")`), or pass a bound method "
                "(`badge.is_visible`) or a named nested function."
            )
        passed, polls, settled_ms = self._poll(condition, timeout, interval)
        return self._record(
            label,
            passed,
            _sampled(actual),
            expected,
            covers,
            extra={
                "mode": "eventually",
                "settled_ms": settled_ms,
                "timeout_ms": int(timeout * 1000),
                "polls": polls,
            },
        )

    def require_eventually(
        self,
        label: str,
        condition: Callable[[], Any],
        *,
        timeout: float = DEFAULT_EVENTUALLY_TIMEOUT,
        interval: float = EVENTUALLY_INTERVAL,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> None:
        """`eventually`, stopping the scenario when the page never arrives."""
        if not self.eventually(
            label,
            condition,
            timeout=timeout,
            interval=interval,
            actual=actual,
            expected=expected,
            covers=covers,
        ):
            raise CheckFailed(label)

    def verify(
        self,
        check: str,
        observed: Any,
        *,
        covers: Sequence[str] | None = None,
        label: str = "",
        **args: Any,
    ) -> bool:
        """Make the observation an obligation's `verify:` bullet declares, and record it."""
        verifier = VERIFIERS.get(check)
        if verifier is None:
            raise ValueError(
                f"'{check}' is not a declared check — the vocabulary is: "
                f"{', '.join(sorted(VERIFIERS))}"
            )
        passed, actual, expected = verifier(observed, args)
        rendered = ", ".join(f"{key}={value!r}" for key, value in args.items())
        return self._record(
            label or f"{check}({rendered})",
            passed,
            actual,
            expected,
            covers,
            extra={"check": check, "check_args": args},
        )

    def _poll(
        self, condition: Callable[[], Any], timeout: float, interval: float
    ) -> tuple[bool, int, int]:
        """Re-sample `condition` until it holds or the deadline passes."""
        started = time.monotonic()
        polls = 0
        while True:
            polls += 1
            try:
                passed = bool(condition())
            except BaseException as exc:  # noqa: BLE001 — re-raised unless it means "not yet"
                if not _not_yet(exc):
                    raise
                passed = False
            elapsed = time.monotonic() - started
            if passed or elapsed >= timeout:
                return passed, polls, int(elapsed * 1000)
            time.sleep(min(interval, timeout - elapsed))

    def _record(
        self,
        label: str,
        condition: Any,
        actual: Any,
        expected: Any,
        covers: Sequence[str] | None,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> bool:
        passed = bool(condition)
        self._index += 1
        self.assertions += 1
        if not passed:
            self.failures += 1
        record: dict[str, Any] = {
            "type": "assert",
            "id": f"{self.scenario_id}-{self._index}",
            "label": label,
            "passed": passed,
            "actual": actual,
            "expected": expected,
            "covers": list(covers) if covers is not None else [],
        }
        if extra:
            record.update(extra)
        self._recorder.emit(record)
        return passed


    @contextmanager
    def step(self, label: str) -> Iterator[None]:
        """Group the work of one phase under a named step record in the ledger."""
        self._index += 1
        step_id = f"{self.scenario_id}-step-{self._index}"
        self._recorder.emit(
            {"type": "step_start", "id": step_id, "label": label, "offset_ms": self.offset_ms()}
        )
        try:
            yield
        except BaseException as exc:
            self._recorder.emit(
                {
                    "type": "step_end",
                    "id": step_id,
                    "label": label,
                    "failed": True,
                    "error": repr(exc),
                    "offset_ms": self.offset_ms(),
                }
            )
            raise
        self._recorder.emit(
            {"type": "step_end", "id": step_id, "label": label, "failed": False, "offset_ms": self.offset_ms()}
        )


    def capture(self, key: str, value: Any) -> None:
        """Publish a value into the run ledger so a later report can name it."""
        self._captures[key] = str(value)
        self._recorder.emit({"type": "capture", "key": key, "value": str(value)})

    def get(self, key: str) -> str:
        return self._captures[key]

    def artifact(self, path: str | Path, *, kind: str) -> Path:
        """Register a file — or a directory of files — as evidence."""
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.dir / resolved
        resolved.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {"type": "artifact", "path": str(resolved), "kind": kind}
        if resolved.is_dir():
            record["directory"] = True
        self._recorder.emit(record)
        return resolved

    def secret(self, name: str) -> str:
        declared = REGISTRY.secrets.get(name)
        if declared is None:
            raise KeyError(f"secret {name!r} is not declared in this plan")
        return declared.get()

    def offset_ms(self) -> int:
        """Now, on the run's clock — the same scale every other driver's records use."""
        return self.offset_base_ms + round((time.monotonic() - _PROCESS_START) * 1000)


    def by_role(self, role: str, *, name: str | None = None, **kwargs: Any) -> Any:
        return self.browser_page.get_by_role(role, name=name, **kwargs)

    def by_label(self, text: str, **kwargs: Any) -> Any:
        return self.browser_page.get_by_label(text, **kwargs)

    def by_test_id(self, value: str) -> Any:
        return self.browser_page.get_by_test_id(value)

    def by_text(self, text: str | re.Pattern[str], **kwargs: Any) -> Any:
        return self.browser_page.get_by_text(text, **kwargs)

    def by_css(self, selector: str) -> Any:
        return self.browser_page.locator(selector)

    def goto(self, url: str, **kwargs: Any) -> Any:
        """Navigate a relative path against the target's `base_url`."""
        return self.browser_page.goto(self.http.url_for(url), **kwargs)

    def window(self) -> Any:
        """Open an observation window over the exchanges this page is about to make."""
        recorder = self.diagnostics
        if recorder is None or not hasattr(recorder, "window"):
            raise RuntimeError(
                f"scenario {self.scenario_id!r} reads an HTTP exchange the browser made, but "
                f"its target '{self.target.name}' declares driver '{self.target.driver}' — "
                "only driver='playwright' records what the page requested"
            )
        return recorder.window()

    def capture_text(self, key: str, locator: Any) -> str:
        """Capture a locator's text — a defect if it matches nothing on the page."""
        if locator.count() == 0:
            detail = f"capture {key!r} locator matched no elements on the page"
            self._fault(self.scenario_id, -1, "capture", "defect", detail)
            raise RuntimeError(f"qa {self.scenario_id!r}: {detail}")
        value = locator.inner_text()
        self.capture(key, value)
        return value

    def screenshot(self, name: str = "") -> Path:
        """Photograph the page, measure where it put its content, and register both."""
        path = self.dir / "screenshots" / f"{self.scenario_id}-{name or 'screenshot'}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.browser_page.screenshot(path=str(path), full_page=True)
        self._recorder.emit({"type": "artifact", "path": str(path), "kind": "screenshot"})
        self.diagnostics.measure(path)
        return path

    def device_screenshot(self, name: str = "", *, source: str = "maestro") -> Path:
        """The same thing for a phone: photograph the screen, and measure what is on it."""
        hierarchy = _harness_module("ostler_qa_hierarchy")
        path = self.dir / "screenshots" / f"{self.scenario_id}-{name or 'screenshot'}.png"
        hierarchy.screenshot(path)
        self._recorder.emit({"type": "artifact", "path": str(path), "kind": "screenshot"})
        frame, elements = hierarchy.scan(source=source)
        scan = _harness_module("ostler_qa_scan")
        regions = scan.merge_rects(elements)
        measured = {"schema": DEVICE_LAYOUT_SCHEMA, **scan.summarize(frame, regions)}
        for artifact, payload, kind in (
            (path.with_suffix(".layout.json"), measured, "layout"),
            (path.with_suffix(".regions.json"), regions, "regions"),
        ):
            artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self._recorder.emit({"type": "artifact", "path": str(artifact), "kind": kind})
        return path

    def vet(self, screen: str, name: str = "", components: list[str] | None = None) -> Path:
        """Photograph a screen and hand ostler the screen it is supposed to be."""
        state = name or "vet"
        if self.target.driver == "playwright":
            path = self.screenshot(state)
        elif self.target.driver == "maestro":
            path = self.device_screenshot(state)
        else:
            raise RuntimeError(
                f"scenario {self.scenario_id!r} vets '{screen}' on a '{self.target.driver}' "
                "target, which renders nothing to vet — declare the target with "
                "driver='playwright' for a browser or driver='maestro' for a device"
            )
        self.vets += 1
        self._recorder.emit({
            "type": "vet",
            "screen": screen,
            "state": state,
            "screenshot": str(path),
            "regions": str(path.with_suffix(".regions.json")),
            "components": components or [],
            "url": str(self.page.url) if self.target.driver == "playwright" else "",
        })
        return path

    @property
    def browser_page(self) -> Any:
        if self.page is None:
            raise RuntimeError(
                f"scenario {self.scenario_id!r} reaches for the browser, but its target "
                f"'{self.target.name}' declares driver '{self.target.driver}' — declare the "
                "target with driver='playwright' to get a page"
            )
        return self.page


class Maestro:
    """Run a Maestro flow from inside the scenario, and hand back what it did."""

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def flow(self, commands: Sequence[Any]) -> str:
        """Build flow text from Maestro commands."""
        app_id = self._qa.target.app_id
        if not app_id:
            raise ValueError(f"target '{self._qa.target.name}' declares no app_id")
        return json.dumps({"appId": app_id}) + "\n---\n" + json.dumps(list(commands), indent=2)

    def run(
        self,
        flow: str | Path,
        *,
        name: str = "",
        timeout: float = 600.0,
    ) -> MaestroResult:
        if shutil.which("maestro") is None:
            raise RuntimeError("the maestro CLI is not installed on this machine")
        qa = self._qa
        label = name or qa.scenario_id
        if isinstance(flow, Path):
            path = flow
        else:
            path = qa.dir / "generated" / f"{label}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(flow, encoding="utf-8")
            qa.artifact(path, kind="generated-maestro-flow")
        junit = qa.dir / "traces" / f"{label}-junit.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        test_output = qa.dir / "generated" / f"{label}-maestro-output"
        test_output.mkdir(parents=True, exist_ok=True)
        command = [
            "maestro", "test",
            "--format", "junit",
            "--output", str(junit),
            "--test-output-dir", str(test_output),
            str(path),
        ]
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, flow path built above
                command, cwd=qa.root, capture_output=True, text=True, timeout=timeout, check=False
            )
            output, code = f"{done.stdout}{done.stderr}", done.returncode
        except subprocess.TimeoutExpired as exc:
            output = f"{exc.stdout or ''}{exc.stderr or ''}"
            code = 124
        log = qa.dir / "traces" / f"{label}-maestro.txt"
        log.write_text(output, encoding="utf-8")
        qa.artifact(log, kind="maestro-output")
        if junit.is_file():
            qa.artifact(junit, kind="junit")
        for produced in sorted(test_output.rglob("*")):
            if produced.is_file() and produced.stat().st_size:
                kind = (
                    "maestro-screenshot"
                    if produced.suffix.lower() == ".png"
                    else "maestro-diagnostic"
                )
                qa.artifact(produced, kind=kind)
        return MaestroResult(exit_code=code, output=output, flow=path)


@dataclass
class MaestroResult:
    exit_code: int
    output: str
    flow: Path

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class ToolResult:
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class Tool:
    """One opted-in external command, resolved to an argv on this machine."""

    def __init__(self, qa: Qa, name: str, command: str) -> None:
        self._qa = qa
        self.name = name
        self._command = command

    def run(
        self,
        *args: str,
        timeout: float = 60.0,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ToolResult:
        """Run the tool once, from the repo root unless *cwd* says where, with *env* overlaid."""
        if shutil.which(self._command) is None:
            raise RuntimeError(
                f"qa tool {self.name!r} names command {self._command!r}, which is not "
                "on PATH — `ostler qa validate` should have caught this before the run"
            )
        argv = [self._command, *args]
        where = self._qa.root if cwd is None else self._cwd(cwd)
        overlay = None if env is None else {**os.environ, **self._env(env)}
        try:
            done = subprocess.run(  # noqa: S603 - argv built from a config-declared command
                argv,
                cwd=where,
                env=overlay,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return ToolResult(command=argv, stdout=done.stdout, stderr=done.stderr, exit_code=done.returncode)
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                command=argv,
                stdout=str(exc.stdout) if exc.stdout else "",
                stderr=str(exc.stderr) if exc.stderr else "",
                exit_code=124,
            )

    def _cwd(self, cwd: str | Path) -> Path:
        base = self._qa.dir.resolve()
        candidate = Path(cwd)
        resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError(
                f"qa tool {self.name!r}: cwd {str(cwd)!r} must stay inside the run's qa "
                f"directory ({base})"
            )
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def _env(self, env: Mapping[str, str]) -> dict[str, str]:
        undeclared = sorted(name for name in env if name not in self._qa._tool_env_allowed)
        if undeclared:
            raise ValueError(
                f"qa tool {self.name!r}: env name(s) {', '.join(undeclared)} are not declared "
                "— add them to the plan's tool_env(...) so validation can see them"
            )
        return {name: str(value) for name, value in env.items()}


class Tesseract:
    """OCR over an image, via the `tesseract` CLI opted into `agents.yml`'s `qa.tools`."""

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def ocr(self, image: str | Path, *, timeout: float = 60.0) -> str:
        result = self._qa.tool("tesseract").run(str(image), "stdout", timeout=timeout)
        if not result.ok:
            raise RuntimeError(f"tesseract failed on {image}: {result.stderr or result.stdout}")
        return result.stdout


class Convert:
    """Resize (and, over time, other transforms) via ImageMagick's `convert`."""

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def resize(
        self,
        image: str | Path,
        width: int,
        height: int,
        *,
        out: str | Path | None = None,
        timeout: float = 60.0,
    ) -> Path:
        src = Path(image)
        dest = (
            Path(out)
            if out is not None
            else self._qa.dir / "generated" / f"{src.stem}-{width}x{height}{src.suffix}"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = self._qa.tool("convert").run(
            str(src), "-resize", f"{width}x{height}", str(dest), timeout=timeout
        )
        if not result.ok:
            raise RuntimeError(f"convert failed on {image}: {result.stderr or result.stdout}")
        self._qa.artifact(dest, kind="resized-image")
        return dest



CHECK_METHODS = frozenset({"check", "require", "eventually", "require_eventually", "verify"})

VET_METHOD = "vet"


def count_checks(source: str) -> dict[str, int]:
    """How many `qa.check` / `qa.require` calls each top-level function contains."""
    reachable = _reachable_calls(ast.parse(source))
    return {
        name: sum(
            1
            for call in calls
            if isinstance(call.func, ast.Attribute) and call.func.attr in CHECK_METHODS
        )
        for name, calls in reachable.items()
    }


def _reachable_calls(tree: ast.Module) -> dict[str, list[ast.Call]]:
    """Every call each top-level function makes, following the module helpers it calls."""
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def own(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
        calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
        return sorted(calls, key=lambda call: (call.lineno, call.col_offset))

    found: dict[str, list[ast.Call]] = {}
    for name, node in functions.items():
        seen = {name}
        pending = [node]
        calls: list[ast.Call] = []
        while pending:
            body = own(pending.pop(0))
            calls.extend(body)
            for call in body:
                if not isinstance(call.func, ast.Name) or call.func.id in seen:
                    continue
                helper = functions.get(call.func.id)
                if helper is not None:
                    seen.add(call.func.id)
                    pending.append(helper)
        found[name] = calls
    return found


def extract_check_covers(source: str) -> dict[str, list[str]]:
    """Which obligation ids each scenario's `qa.check`/`qa.require` calls claim, as written."""
    tree = ast.parse(source)
    constants = _module_constants(tree)
    found: dict[str, list[str]] = {}
    for name, calls in _reachable_calls(tree).items():
        claimed: list[str] = []
        for call in calls:
            if (
                not isinstance(call.func, ast.Attribute)
                or call.func.attr not in CHECK_METHODS
            ):
                continue
            for keyword in call.keywords:
                if keyword.arg == "covers":
                    claimed.extend(_covers_ids(keyword.value, constants))
        found[name] = claimed
    return found


def _resolve(node: ast.expr, constants: dict[str, Any]) -> Any:
    """The value the parse can attribute to this expression, or `None` when it cannot."""
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return _literal(node)


def _covers_ids(node: ast.expr, constants: dict[str, Any]) -> list[str]:
    """The obligation ids a `covers=` argument binds, with `COMPUTED` for each unreadable one."""
    written = _resolve(node, constants)
    if isinstance(written, (list, tuple)):
        return [item if isinstance(item, str) else COMPUTED for item in written]
    if isinstance(node, (ast.List, ast.Tuple)):
        elements = [_resolve(element, constants) for element in node.elts]
        return [item if isinstance(item, str) else COMPUTED for item in elements]
    return [COMPUTED]


def _module_constants(tree: ast.Module) -> dict[str, Any]:
    """Module-level `NAME = <literal>` bindings, minus every name bound more than once."""
    constants: dict[str, Any] = {}
    rebound: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            targets = [node.target] if node.value is not None else []
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in constants:
                rebound.add(target.id)
            constants[target.id] = _literal(value) if value is not None else None
    for name in rebound:
        constants.pop(name, None)
    return constants


VERIFY_METHOD = "verify"


def extract_check_calls(source: str) -> dict[str, list[dict[str, Any]]]:
    """Which named checks each scenario invokes, with the arguments it wrote and what it binds."""
    tree = ast.parse(source)
    constants = _module_constants(tree)
    found: dict[str, list[dict[str, Any]]] = {}
    for function, reachable in _reachable_calls(tree).items():
        calls: list[dict[str, Any]] = []
        for call in reachable:
            if not isinstance(call.func, ast.Attribute) or call.func.attr != VERIFY_METHOD:
                continue
            name = _resolve(call.args[0], constants) if call.args else None
            args: dict[str, Any] = {}
            covers: list[str] = []
            for keyword in call.keywords:
                if keyword.arg is None:
                    continue
                if keyword.arg == "covers":
                    covers = _covers_ids(keyword.value, constants)
                elif keyword.arg != "label":
                    value = _resolve(keyword.value, constants)
                    args[keyword.arg] = value if value is not None else COMPUTED
            calls.append(
                {
                    "check": name if isinstance(name, str) else COMPUTED,
                    "args": args,
                    "covers": covers,
                }
            )
        found[function] = calls
    return found


LOCATOR_METHODS = {
    "by_role": "role",
    "get_by_role": "role",
    "by_label": "label",
    "get_by_label": "label",
    "by_test_id": "test_id",
    "get_by_test_id": "test_id",
    "by_text": "text",
    "get_by_text": "text",
    "by_css": "css",
    "locator": "css",
}

COMPUTED = "*"


def extract_locators(source: str) -> dict[str, list[dict[str, Any]]]:
    """The locators and navigations each scenario writes, in the shape `validate` reads."""
    found: dict[str, list[dict[str, Any]]] = {}
    for name, calls in _reachable_calls(ast.parse(source)).items():
        actions: list[dict[str, Any]] = []
        for call in calls:
            if not isinstance(call.func, ast.Attribute):
                continue
            action = _locator_action(call, call.func.attr)
            if action is not None:
                actions.append(action)
        found[name] = actions
    return found


def _locator_action(call: ast.Call, method: str) -> dict[str, Any] | None:
    if method == "goto":
        url = _literal(call.args[0]) if call.args else None
        return {"do": "goto", "url": url} if isinstance(url, str) else None
    strategy = LOCATOR_METHODS.get(method)
    if strategy is None:
        return None
    value = _literal(call.args[0]) if call.args else None
    locator: dict[str, Any] = {strategy: value if isinstance(value, str) else COMPUTED}
    for keyword in call.keywords:
        if keyword.arg == "name" and strategy == "role":
            named = _literal(keyword.value)
            locator["name"] = named if isinstance(named, str) else COMPUTED
    return {"locator": locator}


def extract_vets(source: str) -> dict[str, list[str]]:
    """Which screens each scenario hands to the book, as written."""
    found: dict[str, list[str]] = {}
    for name, calls in _reachable_calls(ast.parse(source)).items():
        screens: list[str] = []
        for call in calls:
            if not isinstance(call.func, ast.Attribute) or call.func.attr != VET_METHOD:
                continue
            screen = _literal(call.args[0]) if call.args else None
            screens.append(screen if isinstance(screen, str) else COMPUTED)
        found[name] = screens
    return found


INSTANCE_METHOD = "instance"


def extract_instances(source: str) -> dict[str, list[dict[str, Any]]]:
    """The concrete instances each scenario declares for repeated obligations, as written."""
    tree = ast.parse(source)
    constants = _module_constants(tree)
    found: dict[str, list[dict[str, Any]]] = {}
    for function, reachable in _reachable_calls(tree).items():
        instances: list[dict[str, Any]] = []
        for call in reachable:
            if not isinstance(call.func, ast.Attribute) or call.func.attr != INSTANCE_METHOD:
                continue
            obligation = _resolve(call.args[0], constants) if call.args else None
            bindings_node = call.args[1] if len(call.args) > 1 else None
            for keyword in call.keywords:
                if keyword.arg == "bindings":
                    bindings_node = keyword.value
            bindings: dict[str, Any] | None = None
            if isinstance(bindings_node, ast.Dict):
                bindings = {}
                for key_node, value_node in zip(bindings_node.keys, bindings_node.values):
                    key = _resolve(key_node, constants) if key_node is not None else None
                    if not isinstance(key, str):
                        bindings = None
                        break
                    value = _resolve(value_node, constants)
                    bindings[key] = value if isinstance(value, str) else COMPUTED
            elif bindings_node is not None:
                written = _resolve(bindings_node, constants)
                if isinstance(written, dict):
                    bindings = {
                        str(key): value if isinstance(value, str) else COMPUTED
                        for key, value in written.items()
                    }
            instances.append(
                {
                    "obligation": obligation if isinstance(obligation, str) else COMPUTED,
                    "bindings": bindings,
                }
            )
        found[function] = instances
    return found


def _literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _describe(module_path: Path) -> dict[str, Any]:
    _load(module_path)
    data = REGISTRY.as_json()
    source = module_path.read_text(encoding="utf-8")
    counts = count_checks(source)
    check_covers = extract_check_covers(source)
    check_calls = extract_check_calls(source)
    locators = extract_locators(source)
    vets = extract_vets(source)
    instances = extract_instances(source)
    for declared in data["scenarios"]:
        declared["checks"] = counts.get(declared["function"], 0)
        declared["check_covers"] = check_covers.get(declared["function"], [])
        declared["check_calls"] = check_calls.get(declared["function"], [])
        declared["locators"] = locators.get(declared["function"], [])
        declared["vets"] = vets.get(declared["function"], [])
        declared["instances"] = instances.get(declared["function"], [])
    return data


def _load(module_path: Path) -> None:
    """Import the plan module by path, with its own directory and the spec root importable."""
    import importlib.util

    sys.path.insert(0, str(module_path.parent.parent))
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("qa_plan", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{module_path} is not an importable Python module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["qa_plan"] = module
    spec.loader.exec_module(module)




def _harness_module(name: str) -> Any:
    """Import a sibling harness module by name."""
    import importlib

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module(name)


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


BROWSER_CLEAN_EXPECTED = "no uncaught page error and no response of status 500 or higher"


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
        tools=context.get("tools", {}),
        fixtures=context.get("fixtures", {}),
        book_fixtures=context.get("book_fixtures", {}),
        tool_env=REGISTRY.tool_env,
    )
    browser = None
    status, error = "passed", None
    try:
        if target_decl.driver == "playwright":
            browser = _open_browser(qa)
        declared.func(qa)
    except CheckFailed:
        status = "failed"
    except BaseException:  # noqa: BLE001 - the traceback is the scenario's verdict
        status, error = "errored", traceback.format_exc()
        print(error, file=sys.stdout)
    if browser is not None:
        unclean = _bind_browser_unclean(qa, browser.unclean())
        problems = [*unclean, *browser.close(failed=status != "passed" or bool(unclean))]
        if problems:
            status = "failed" if status == "passed" else status
            error = "; ".join([part for part in [error, *problems] if part])
    if qa.failures:
        status = "failed" if status == "passed" else status
    if status == "passed" and target_decl.driver in UI_DRIVER_NAMES and qa.vets == 0:
        status = "failed"
        error = (
            f"scenario {declared.id!r} runs against a {target_decl.driver} target and vetted "
            "no screen — call qa.vet('<screen doc>') on each documented state it reaches"
        )
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
    sys.modules.setdefault("ostler_qa", sys.modules["__main__"])
    raise SystemExit(main())
