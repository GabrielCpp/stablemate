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
does not. `data["responses"]` raises `KeyError`; a stream-oriented field lookup reads a
missing field as an empty stream and passes vacuously. Every affordance below is shaped to
keep that property: `qa.http` raises on an unexpected status, `qa.dir` is handed in already
resolved, and a scenario that records no assertion cannot pass.
"""

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

#: Overrides both of the above, and takes strict precedence over them. An inherited
#: descriptor does not cross a container boundary, so a sandboxed scenario is handed a path
#: on a bind-mounted directory and appends to it instead. Precedence has to be strict
#: rather than "whichever is set": an fd number left over from the host names, inside the
#: container, either a closed descriptor or an unrelated open file, and `_Recorder` swallows
#: `OSError` — so the failure mode of getting this wrong is a run that records nothing and
#: says nothing about it.
RECORD_PATH_ENV = "OSTLER_QA_RECORD_PATH"

#: See `ostler.qa.plan.MECHANISMS` for why `synthetic` is not here.
MECHANISMS = ("live", "fixture")
DRIVERS = ("python", "playwright", "maestro")

#: The drivers that drive a user interface, and so the ones whose scenarios must vet. There
#: is no exemption list on purpose: the single defect that motivated this passed a run whose
#: every assertion was true, and an opt-out would have been taken by exactly that plan.
UI_DRIVERS = ("playwright", "maestro")

#: Stamped into the layout digest a *device* screenshot writes, so a reader can tell which
#: source measured it: a phone has no laid-out document to overflow, and reporting the
#: browser's schema over a view hierarchy would invite an audit to look for a flag that
#: cannot appear there.
DEVICE_LAYOUT_SCHEMA = "device-layout/1"

DEFAULT_HTTP_TIMEOUT = 30.0

#: How long `qa.eventually` keeps looking, and how often — Playwright's own `expect()`
#: defaults, deliberately: an author who already knows what `expect` costs knows what this
#: costs, and a plan that needs a different number is saying something about the product.
DEFAULT_EVENTUALLY_TIMEOUT = 5.0
EVENTUALLY_INTERVAL = 0.1

#: When this process started, so a diagnostics timestamp can be placed on the *run's* clock
#: rather than its own. The driver hands over the run offset it was at when it spawned us;
#: everything recorded here is that plus the time since this line ran.
_PROCESS_START = time.monotonic()


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
    viewport: Mapping[str, int] | None = None,
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
        viewport=dict(viewport) if viewport is not None else None,
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
    argv: Sequence[str],
    ready_url: str | None = None,
    ready_method: str = "GET",
    ready_status: int = 200,
    cwd: str | None = None,
    timeout: float = 30.0,
) -> None:
    """Declare a daemon the runner starts before the first scenario and stops after the last.

    `argv` is a list, not a command line, and there is no shell behind it. A daemon used to
    be a string run through `bash -c`, which meant `background("x", cmd="go test ./...")`
    was a legal way to smuggle a unit suite into a run whose whole premise is that it
    observes the product — and it survived the sandbox, because the daemon starts on the
    host. An argv list has no `&&`, no `|`, no expansion: the first element is a program and
    the rest are its arguments, and a plan that wants a pipeline has to say which program.

    Readiness is `ostler`'s to poll, not the scenario's — it is what a scenario is entitled
    to assume, and a scenario that has to wait for its own stack turns a startup failure
    into a product failure. It is an HTTP probe: a URL, and optionally the method and status
    that mean "up". `ready_method="POST", ready_status=201` is there for a service whose
    only route is a POST, which is what the retired command form was actually being used
    for — the capability was HTTP the whole time, spelled as a `curl` invocation.
    """
    entry: dict[str, Any] = {"name": name, "argv": list(argv), "timeout": timeout}
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
    """Writes JSONL records to a path, to `RECORD_FD`, or nowhere.

    A closed fd is the normal case under `describe` and under a scenario a developer runs
    by hand with plain `python qa_plan.py`; dropping the records is what makes that work
    without a special mode.
    """

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
        #: Called just before an `expect_status` mismatch raises, so the scenario's owner can
        #: write the observation down. Without it the loudest kind of failure — the product
        #: answering something the plan said it would not — leaves no assertion behind, and
        #: the evidence map reads the obligation as unasserted rather than contradicted.
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


# --------------------------------------------------------------------------------------
# The scenario-facing object
# --------------------------------------------------------------------------------------


def _not_yet(exc: BaseException) -> bool:
    """Does this exception mean "the page has not got there yet", or "the plan is wrong"?

    Only the first is swallowed and retried, and the narrowness is load-bearing. A
    `KeyError` or a `NameError` inside the lambda is a defect in the *scenario*; swallowing
    it would burn the whole deadline and then report a plan defect as a product failure —
    which is the exact mis-hypothesis `eventually` exists to end, recreated inside its own
    fix. `CheckFailed` is excluded for the same reason: a `qa.require` that ran inside the
    condition has already recorded its own verdict and is not a signal to look again.

    Playwright is matched by module rather than by import, because this file may import
    nothing outside the standard library.
    """
    if isinstance(exc, CheckFailed):
        return False
    return isinstance(exc, (TimeoutError, AssertionError)) or type(exc).__module__.split(".")[
        0
    ] == "playwright"


def _sampled(actual: Any) -> Any:
    """Read an `actual=` that may be a callable, after the poll loop has settled.

    A callable `actual` is the only way to report the value that *decided* the verdict
    rather than one read before the wait began — and evidence must never be able to fail
    the scenario, so an exception becomes its own record.
    """
    if not callable(actual):
        return actual
    try:
        return actual()
    except BaseException as exc:  # noqa: BLE001 — evidence, not a verdict
        return repr(exc)


# --------------------------------------------------------------------------------------
# The named checks a `verify:` bullet declares, as observations
#
# Each verifier takes the observed value and the declared arguments and returns
# `(passed, actual, expected)`. It raises — never returns False — when `observed` is the
# wrong *shape*, because a shape mismatch is a defect in the scenario, and recording it as
# a red assertion would file it against the product.
# --------------------------------------------------------------------------------------

#: Distinguishes "this path is absent" from "this path holds None" in `unchanged`.
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
    """Every leaf of a JSON-ish value, keyed by its dotted path.

    Flat, so a diff can name the field that moved. Lists are indexed rather than compared
    as wholes: `keys_unchanged` exists to catch a move implemented as a copy, and a list
    compared as one value reports "the list changed" — the finding it was meant to replace.
    """
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


def _resolve_path(document: Any, path: str) -> tuple[bool, Any]:
    """Walk a dotted/indexed path. Returns whether it resolved, and to what.

    A leading `$` is the JSONPath root token, not a key: `$.item.id` and `item.id` name the
    same field. `ostler.qa.session._extract_path` has always stripped it, and the vocabulary's
    own examples are written with it — without this the two resolvers disagree and a `$`-rooted
    `json_path` fails as *absent* against a document that holds the value.
    """
    segments = re.findall(r"[^.\[\]]+", path)
    if segments and segments[0] == "$":
        segments = segments[1:]
    current = document
    for segment in segments:
        if isinstance(current, dict):
            if segment not in current:
                return False, None
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            if not segment.isdigit() or int(segment) >= len(current):
                return False, None
            current = current[int(segment)]
        else:
            return False, None
    return True, current


def _verify_http_status(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    status, body = _observed_status(observed)
    expected: Any = {"code": args["code"]}
    actual: Any = {"code": status}
    passed = status == args["code"]
    if "title" in args:
        found = body.get("title") if isinstance(body, dict) else None
        expected["title"], actual["title"] = args["title"], found
        passed = passed and found == args["title"]
    return passed, actual, expected


def _verify_json_path(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    resolved, value = _resolve_path(observed, args["path"])
    if args.get("absent"):
        return not resolved, {"present": resolved}, {"present": False}
    if not resolved:
        return False, {"present": False}, {"path": args["path"]}
    if "equals" in args:
        return str(value) == args["equals"], value, args["equals"]
    if "matches" in args:
        return re.search(args["matches"], str(value)) is not None, value, f"~ {args['matches']}"
    # Presence alone is what the bullet declared, and `ostler.checks` says why that is weak.
    # It is still the author's declaration, so it is honoured rather than second-guessed here.
    return True, value, "present"


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
    found = observed if isinstance(observed, int) and not isinstance(observed, bool) else len(observed)
    return found == args["equals"], found, args["equals"]


def _empty(value: Any) -> bool:
    """Nothing there: `None`, or a sized thing with nothing in it."""
    return value is None or (hasattr(value, "__len__") and len(value) == 0)


def _verify_absent(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    return _empty(observed), observed, "absent"


def _verify_created(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Absent before the action, present after — both halves, or it proves nothing.

    The `(before, after)` pair is insisted on rather than inferred for the reason the check
    exists: an after-only read cannot tell a creation from a subject that was already there,
    and that is precisely the pass this excludes. A scenario that has only the after-read is
    told so by `_pair`, at the call, instead of quietly asserting presence.
    """
    before, after = _pair(observed, "created")
    was_absent, is_present = _empty(before), not _empty(after)
    return (
        was_absent and is_present,
        {"before": before, "after": after},
        {"before": "absent", "after": "present"},
    )


def _verify_removed(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Present before the action, absent after — the mirror of `created`, and for the mirror
    reason: absence afterwards alone passes on a subject that was never there."""
    before, after = _pair(observed, "removed")
    return (
        not _empty(before) and _empty(after),
        {"before": before, "after": after},
        {"before": "present", "after": "absent"},
    )


def _verify_visible(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    if hasattr(observed, "is_visible"):
        shown = bool(observed.is_visible())
        text = observed.inner_text() if shown and "text" in args else None
    else:
        shown, text = bool(observed), observed if "text" in args else None
    if "text" not in args:
        return shown, {"visible": shown}, {"visible": True}
    contains = shown and args["text"] in str(text)
    return contains, {"visible": shown, "text": text}, {"visible": True, "text": args["text"]}


def _verify_persists(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    written, reread = _pair(observed, "persists")
    return reread is not None and reread == written, reread, written


def _verify_emitted(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    found = len(observed)
    if "count" in args:
        return found == args["count"], found, args["count"]
    return found > 0, found, "at least one"


def _verify_conflict_on_stale(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    status, _ = _observed_status(observed)
    # Any refusal counts, 409 is what the contract usually says. What must not pass is a 2xx:
    # an unconditional overwrite accepts the stale write and reports success, which is the
    # exact defect this check exists to exclude.
    return 400 <= status < 500, status, "a refusal (4xx)"


#: What observing each named check means, keyed by the name a `verify:` bullet declares.
#:
#: The vocabulary itself lives in `ostler.checks` — this file is stdlib-only and executes
#: under the project's interpreter, where ostler is not installed, so the names are spelled
#: twice on purpose. `ostler.checks` is the authority on *what may be declared*; this table
#: is the authority on *what observing it means*. A name here with no spec there is
#: unreachable — no bullet can declare it — and a spec there with no entry here fails at the
#: call, by name, on the line that made it. Neither drifts silently.
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
    "persists": _verify_persists,
    "emitted": _verify_emitted,
    "conflict_on_stale": _verify_conflict_on_stale,
}


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
        offset_base_ms: int = 0,
        tools: Mapping[str, str] | None = None,
    ) -> None:
        self.scenario_id = scenario_id
        self.target = target
        self.root = root
        self.spec_dir = spec_dir
        self.dir = qa_dir
        self.covers = list(covers)
        #: `{name: command}` for every QA tool this repo opted into (`agents.yml`'s
        #: `qa: {tools: [...]}`) and ostler resolved to a definition. Built and preflighted
        #: on ostler's side of the process boundary — see `ostler.qa.tools` — because this
        #: file cannot read `agents.yml` or the stablemate config; it only ever imports the
        #: standard library.
        self._tool_commands = dict(tools or {})
        self.http = Http(target.base_url, on_unexpected_status=self._status_mismatch)
        self._recorder = recorder
        self._captures: dict[str, str] = {}
        self._index = 0
        self.assertions = 0
        self.failures = 0
        #: How many screens this scenario handed to the book. Zero on a UI target is a
        #: failure, not a stylistic omission — see `_run`.
        self.vets = 0
        self.offset_base_ms = offset_base_ms
        #: The Playwright page, for a `playwright` target. `None` otherwise, and reaching
        #: for it says so — a scenario declared against the wrong target is a mistake worth
        #: an `AttributeError` on the line that made it.
        self.page: Any = None
        #: The live console/network record for a `playwright` target: `console_errors()`,
        #: `page_errors()`, `failed_requests()`, `responses()`. The diagnostics *file* is
        #: written after the scenario returns, so this is the only way a scenario can fail
        #: itself on a 5xx or an uncaught exception it provoked.
        self.diagnostics: Any = None
        self.maestro = Maestro(self)
        self.tesseract = Tesseract(self)
        self.convert = Convert(self)

    def tool(self, name: str) -> "Tool":
        """A user- or machine-declared external command, opted into via `agents.yml`.

        The generic escape hatch for a repo's own tools (`ocr-diff`, a linter, whatever)
        that have no typed wrapper — `qa.tesseract`/`qa.convert` are this same mechanism
        with a friendlier surface for the two built-ins, and reach it the same way.
        """
        command = self._tool_commands.get(name)
        if command is None:
            raise RuntimeError(
                f"qa tool {name!r} is not available — opt into it via this repo's "
                f"agents.yml `qa: {{tools: [{name!r}]}}`, and if it is not a built-in, "
                f"define it in ~/.config/stablemate/config.toml's [qa_tools.{name}]"
            )
        return Tool(self, name, command)

    # -- assertions --------------------------------------------------------------------

    def _status_mismatch(
        self, method: str, url: str, status: int, allowed: Sequence[int]
    ) -> None:
        """Write down an `expect_status` the product did not meet, before it raises.

        `qa.http.post(..., expect_status=409)` *is* an assertion — the plan said the product
        refuses this, and it did not. Until this record existed the mismatch only ever became
        an `HttpError`, which aborts the scenario before any `qa.check` runs: the run log then
        held no assertion bound to the obligation, and the evidence map called it
        `claimed-but-unasserted` — a QA gap — when what actually happened was the product
        contradicting the book. A seeded compare-and-swap defect was detected exactly this way
        and scored as a miss.

        Bound to the scenario's whole `covers`, unlike a bare `check`, which binds only what
        it was given. The two cases are not symmetrical: a passing check credited to every
        obligation the scenario declared would report the set proven by one observation,
        whereas this record can only ever *add* a contradiction, and only to obligations this
        scenario itself claimed — and it aborts the scenario, so none of the rest of that
        claim will be shown either.
        """
        self._record(
            f"{method} {url} answers {list(allowed)}",
            False,
            status,
            list(allowed),
            self.covers,
        )

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
        """Record one claim about behaviour that the page is allowed to arrive at.

        The difference from `check` is the type of `condition`, and it is the whole point:
        `check` receives an **already-collapsed bool**, so Python samples the DOM and hands
        this harness a dead `False` that cannot be retried, re-read, or told apart from
        "not yet". `.count()`, `.get_attribute()`, `.inner_text()` and `page.evaluate()`
        sample once and never retry, so against a UI still resolving a fetch or a re-render
        they report whatever was on screen at that instant — and the failure that produces
        wears the exact shape of a product defect: intermittent, with a plausible actual.
        A live story spent its whole repair budget on that wrong hypothesis.

        So hand over the sampler, not its result::

            qa.eventually("badge shown", lambda: badge.count() > 0, covers=["ac:2"])

        The condition is evaluated once before any sleep, so an already-true claim costs
        nothing and records `settled_ms: 0`. `actual` may be a callable too, and is then
        read after the poll loop settles — the value that decided the verdict rather than
        one sampled before the wait began.
        """
        if not callable(condition):
            raise TypeError(
                f"qa.eventually({label!r}, …) needs a callable to re-sample, and was handed "
                f"an already-evaluated {type(condition).__name__}. Python collapsed the read "
                "before this harness saw it, so there is nothing left to retry — wrap it: "
                "lambda: <the expression you just wrote>."
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
        """`eventually`, stopping the scenario when the page never arrives.

        The stopping variant matters more here than it does for `check`: when the state a
        journey was waiting for never came, every later assertion is reading a page that is
        not the one the plan is about, and the run reports a cascade of failures whose
        actual values are all noise. That is what made the motivating run unreadable.
        """
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
        """Make the observation an obligation's `verify:` bullet declares, and record it.

        This is the assertion whose strength is not the author's to choose. `qa.check` takes
        an already-collapsed bool, so the scenario decides what "the manifest is unchanged"
        means and can decide it weakly — mask the object before diffing, compare three
        entries but never the key inventory, read back through the session that wrote. Here
        the book names the check and its arguments, `ostler qa validate` refuses a plan that
        does not invoke exactly that call, and the comparison is `VERIFIERS`'. The assertion
        cannot be weaker than the claim because the assertion *is* the claim.

            qa.verify("http_status", response, code=409, title="Manifest Conflict",
                      covers=[OBLIGATION])

        `observed` is what the scenario went and got — a response, a parsed document, a
        locator, or the `(before, after)` pair a differential check compares. Its shape is
        the check's, and a wrong one raises rather than recording red: a scenario that hands
        `unchanged` a single value has a defect of its own, and filing that against the
        product is how a QA run reports a bug nobody has.
        """
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
        """Re-sample `condition` until it holds or the deadline passes.

        Returns the verdict, how many times it looked, and how long it took to settle.
        """
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
            # The assertion's own binding only. Falling back to `self.covers` — the
            # scenario's whole list — stamped every obligation onto every assertion in
            # the body, so one passing check reported the entire set proven and deleting
            # the check that did the proving left the evidence row green. `validate`
            # refuses a plan whose obligations are not each claimed, so a bare
            # `qa.check` here is an extra claim, not an uncredited one.
            "covers": list(covers) if covers is not None else [],
        }
        # Absent rather than zero on a plain `check`: a `settled_ms: 0` on an assertion that
        # was never retried is a claim about a sample nobody took, and a reader deciding
        # whether a red assertion is a race would believe it.
        if extra:
            record.update(extra)
        self._recorder.emit(record)
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

    def offset_ms(self) -> int:
        """Now, on the run's clock — the same scale every other driver's records use."""
        return self.offset_base_ms + round((time.monotonic() - _PROCESS_START) * 1000)

    # -- the browser -------------------------------------------------------------------
    #
    # `qa.page` is the whole Playwright API and a scenario may use it directly. These five
    # helpers exist for one reason beyond brevity: `describe` reads their constant
    # arguments out of the parsed tree, so `ostler qa validate` can still hold a browser
    # scenario to the role and name the OKF book documents for what it covers. A locator
    # written as `qa.page.get_by_text(...)` is invisible to that check.

    def by_role(self, role: str, *, name: str | None = None, **kwargs: Any) -> Any:
        return self.browser_page.get_by_role(role, name=name, **kwargs)

    def by_label(self, text: str, **kwargs: Any) -> Any:
        return self.browser_page.get_by_label(text, **kwargs)

    def by_test_id(self, value: str) -> Any:
        return self.browser_page.get_by_test_id(value)

    def by_text(self, text: str | re.Pattern[str], **kwargs: Any) -> Any:
        # Playwright's own default (`exact=False`, whitespace-normalised substring), not a
        # pinned `exact=True`. The pinned form silently matched nothing whenever the page
        # rendered the text inside a larger node — a composite string, a filename quoted in
        # a sentence — and the miss reads downstream as a product defect rather than as a
        # locator that cannot match. `str | Pattern` for the same reason `by_label` takes
        # `**kwargs`: an author who needs a case-insensitive match should not have to drop
        # to `qa.page.get_by_text`, which `extract_locators` cannot see.
        return self.browser_page.get_by_text(text, **kwargs)

    def by_css(self, selector: str) -> Any:
        return self.browser_page.locator(selector)

    def goto(self, url: str, **kwargs: Any) -> Any:
        """Navigate, resolving a relative path against the target's `base_url`."""
        return self.browser_page.goto(self.http.url_for(url), **kwargs)

    def screenshot(self, name: str = "") -> Path:
        """Photograph the page, measure where it put its content, and register both.

        The `.layout.json` beside the image is the half a machine can read: `ostler vet`'s
        DOM scan of the same instant, every structural region's box against the viewport. A
        screenshot alone can only be judged by a person looking at it, and nothing in the run
        looks at it — which is how a page that renders as a narrow column against one margin
        passes a scenario that proves every element it names is present.
        """
        path = self.dir / "screenshots" / f"{self.scenario_id}-{name or 'screenshot'}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.browser_page.screenshot(path=str(path), full_page=True)
        self._recorder.emit({"type": "artifact", "path": str(path), "kind": "screenshot"})
        self.diagnostics.measure(path)
        return path

    def device_screenshot(self, name: str = "", *, source: str = "maestro") -> Path:
        """The same thing for a phone: photograph the screen, and measure what is on it.

        A device has no DOM, so the regions come from its view hierarchy —
        `maestro hierarchy` by default, `uiautomator` where Maestro does not reach on
        Android. Both are translated into the element shape the DOM scan produces, so the
        `.layout.json` and `.regions.json` written here are the same documents a browser
        writes and are read by the same audit and the same `placement:` check.
        """
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
        """Photograph a screen and hand ostler the screen it is supposed to be.

        `screenshot` records geometry nobody has an opinion about. This one names the
        documented screen, so ostler can register what rendered against what the book placed
        — and a component sitting where the book does not put it becomes a failed assertion
        in the ledger, inside the story, rather than a picture somebody might open.

        The resolving happens on the ostler side: the harness runs under the project's
        interpreter, has never seen the book, and cannot import ostler to look.

        `components` narrows the registration to the anchors it names, for a photograph
        taken mid-journey that establishes part of a screen rather than the whole of it.
        Omit it and the whole screen is answered for, which is the honest default; a name
        the screen does not document fails the scenario rather than narrowing to nothing.
        """
        state = name or "vet"
        if self.target.driver == "playwright":
            path = self.screenshot(state)
        elif self.target.driver == "maestro":
            path = self.device_screenshot(state)
        else:
            # Said here rather than left to `browser_page`, whose advice — declare the target
            # with driver='playwright' — is exactly wrong for a scenario that drives no UI.
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
    """Run a Maestro flow from inside the scenario, and hand back what it did.

    The verdict is the caller's: `run` returns the result and the scenario asserts on it,
    the way it asserts on an HTTP response. Under the YAML format the driver appended a
    single synthetic `maestro-flow` assertion of its own, which made a mobile scenario's
    coverage ride on the exit code of the CLI rather than on anything the plan claimed.
    """

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def flow(self, commands: Sequence[Any]) -> str:
        """Build flow text from Maestro commands.

        YAML is a superset of JSON and Maestro's parser accepts it, which is what lets a
        stdlib-only harness write a flow at all. A scenario with a hand-written flow file
        passes its path to `run` instead.
        """
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
    """One opted-in external command, resolved to an argv on this machine.

    Handed back by `Qa.tool(name)`, never constructed directly — the command it runs
    came from the opt-in/definition split in `ostler.qa.tools`, not from anything this
    scenario wrote.
    """

    def __init__(self, qa: Qa, name: str, command: str) -> None:
        self._qa = qa
        self.name = name
        self._command = command

    def run(self, *args: str, timeout: float = 60.0) -> ToolResult:
        if shutil.which(self._command) is None:
            raise RuntimeError(
                f"qa tool {self.name!r} names command {self._command!r}, which is not "
                "on PATH — `ostler qa validate` should have caught this before the run"
            )
        argv = [self._command, *args]
        try:
            done = subprocess.run(  # noqa: S603 - argv built from a config-declared command
                argv, cwd=self._qa.root, capture_output=True, text=True, timeout=timeout, check=False
            )
            return ToolResult(command=argv, stdout=done.stdout, stderr=done.stderr, exit_code=done.returncode)
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                command=argv,
                stdout=str(exc.stdout) if exc.stdout else "",
                stderr=str(exc.stderr) if exc.stderr else "",
                exit_code=124,
            )


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


# --------------------------------------------------------------------------------------
# describe
# --------------------------------------------------------------------------------------

#: The methods on `qa` that append an assertion record. A scenario claiming coverage and
#: calling none of them proves nothing, and unlike shell that is now statically visible.
#: `eventually`/`require_eventually` are in here for one reason and it is worth stating:
#: `count_checks` and `extract_check_covers` both key off this set, so a retrying assertion
#: counts as an assertion and its `covers=` binds with no other edit. Leaving them out would
#: have made the doctrine's recommended spelling the one that fails validation.
#: `verify` is in here for the same reason: it records an assertion, and its `covers=` binds
#: exactly as the others' does. It is also the *only* one `extract_check_calls` reads, since
#: it is the only one that names a check from the book.
CHECK_METHODS = frozenset({"check", "require", "eventually", "require_eventually", "verify"})

#: The method that photographs a screen and hands it to the book for registration. A UI
#: scenario that never calls it proves every element it names is *present* and nothing at
#: all about where they landed — which is the shape of run this exists to stop passing.
VET_METHOD = "vet"


def count_checks(source: str) -> dict[str, int]:
    """How many `qa.check` / `qa.require` calls each top-level function contains.

    Static, by `ast`, and that is the point: the YAML format could only be defended by
    `_exit_sentinel`, a regex guessing whether a shell string proved anything. Here the
    question "does this scenario assert" has an actual answer before anything runs.

    Counts calls nested in loops, `with` blocks and helper branches, and calls in the
    module-level helpers the scenario invokes — see `_reachable_calls` for why following
    them is the honest reading rather than the lenient one.
    """
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
    """Every call each top-level function makes, following the module helpers it calls.

    A scenario that factors its assertions into `verify_created(qa, observation)` and calls
    it asserts exactly as much as one that inlines them — the ledger the run writes cannot
    tell the two apart, because at runtime there is no difference. Reading only the
    scenario's own body made the static half disagree: the plan bound its obligations
    correctly and validation answered `no assertion invokes it`, naming neither the real
    problem nor its fix. Inlining is not a fix either, since a node's `verify:` bullets fan
    out onto every obligation it mints and the resulting plan repeats the same twenty-id
    call in every scenario.

    Calls in each function are ordered by position and the caller's own come first, so the
    action numbers the locator problems cite still count down the scenario as written.
    Recursion terminates on the visited set, so a helper pair that calls each other is read
    once rather than forever.
    """
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
    """Which obligation ids each scenario's `qa.check`/`qa.require` calls claim, as written.

    The scenario-level `covers=` is a promise about the whole function; this is the part that
    says *which assertion* discharges it. Without the distinction the two are impossible to
    tell apart, and the gap is not theoretical: a scenario declaring `covers=["ac:4"]` passed
    validation on the strength of any one assertion anywhere in its body, so deleting the two
    checks that actually exercised AC4 turned a failing run green while the ledger went on
    reporting AC4 covered. Removing an assertion has to fail here, loudly, instead of reading
    downstream as a product that started working.

    Only ids the parse can *read* are recovered, and anything else contributes `COMPUTED` —
    which matches no obligation, so the obligation stays unclaimed and the caller reports it.
    That is deliberate rather than lenient: a binding validation cannot read is a binding the
    evidence gate cannot count either.

    A module-level `NAME = "okf:…"` counts as readable, because it is: the value is in the
    parse tree, one assignment away, and resolving it makes the static answer agree with the
    runtime one instead of contradicting it. Obligation ids run to ninety characters and a
    plan binding twenty of them per call is unreadable spelled out; every author reaches for
    the constant, and before this the gate answered a correctly-bound assertion with "no
    assertion invokes it" — which names neither the real problem nor its fix. A name assigned
    more than once is left `COMPUTED`: which value reached the call is then a question the
    parse genuinely cannot answer.
    """
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
    """The value the parse can attribute to this expression, or `None` when it cannot.

    A bare name is looked up in the module's own constants — the value is one assignment
    away in the same tree, so reading it is still static.
    """
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return _literal(node)


def _covers_ids(node: ast.expr, constants: dict[str, Any]) -> list[str]:
    """The obligation ids a `covers=` argument binds, with `COMPUTED` for each unreadable one.

    Both halves of the binding — the scenario's claim and the check call `ostler qa validate`
    compares against the book — read this, so a spelling that binds in one has to bind in the
    other. They disagreeing is what reports a correctly-bound assertion as absent.
    """
    written = _resolve(node, constants)
    if isinstance(written, (list, tuple)):
        return [item if isinstance(item, str) else COMPUTED for item in written]
    if isinstance(node, (ast.List, ast.Tuple)):
        elements = [_resolve(element, constants) for element in node.elts]
        return [item if isinstance(item, str) else COMPUTED for item in elements]
    return [COMPUTED]


def _module_constants(tree: ast.Module) -> dict[str, Any]:
    """Module-level `NAME = <literal>` bindings, minus every name bound more than once.

    Rebinding is the whole reason for the exclusion rather than last-write-wins: a name the
    module reassigns has no single value at the point of a call, and guessing one would put
    an id in the ledger the run never asserted.
    """
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


#: The method that makes a declared observation, and the one `extract_check_calls` reads.
VERIFY_METHOD = "verify"


def extract_check_calls(source: str) -> dict[str, list[dict[str, Any]]]:
    """Which named checks each scenario invokes, with the arguments it wrote and what it binds.

    This is the half of the binding that `ostler qa validate` compares against the book: an
    obligation whose `verify:` bullet declares `keys_unchanged(subject="pages")` is only
    covered by a scenario that calls exactly that, with those arguments, bound to that id.
    A weaker assertion is no longer a judgment call about whether the oracle is strong
    enough — it is a call that is not the declared one, and the difference is a string
    comparison.

    Static, and only what the parse can read: an argument it cannot becomes `"*"`, which
    canonicalises to a call matching no declaration, so the obligation stays unbound and the
    caller says so. A module-level constant it can read, and does — the same spelling has to
    bind here and in `extract_check_covers`, or a plan passes one half of the binding and is
    reported absent by the other. Read before anything runs, which is the only moment at
    which the answer is still cheap.
    """
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


#: How a locator helper is spelled, and the strategy key it stands for. Both the `qa.` form
#: and Playwright's own `page.` form are listed: a scenario is free to use the page directly,
#: and the book check should still see what it addressed.
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

#: Stands in for a locator argument that is computed rather than written. A role addressed
#: through a variable still counts as *addressed by role* — the check that would otherwise
#: fire says no locator uses a role at all, which would be false.
COMPUTED = "*"


def extract_locators(source: str) -> dict[str, list[dict[str, Any]]]:
    """The locators and navigations each scenario writes, in the shape `validate` reads.

    Static, and it has to be: `_validate_book_locators` holds a browser scenario to the
    role, name and route the OKF book documents for what it covers, and validation runs
    before anything is executed. Under YAML the action list was the plan; here the plan is
    code, so the list is recovered from the parsed tree instead.

    Only what is written literally is recovered. A computed role becomes `"*"` — addressed
    by role, matching no documented one — and a computed `goto` URL is omitted rather than
    reported as a route the book does not document.
    """
    found: dict[str, list[dict[str, Any]]] = {}
    # `_reachable_calls` orders each function's calls by position, so a locator wrapped in
    # `.click()` no longer sorts after a bare one written below it — the problems this feeds
    # name the offending action by its number in the scenario.
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
    """Which screens each scenario hands to the book, as written.

    Recovered statically for the same reason the locators are: "does this browser scenario
    prove the page looked right" has to have an answer before a run spends an hour arriving
    at one. A computed screen becomes `"*"` — vetted, but naming a document validation
    cannot check against the packet.
    """
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
    for declared in data["scenarios"]:
        declared["checks"] = counts.get(declared["function"], 0)
        declared["check_covers"] = check_covers.get(declared["function"], [])
        declared["check_calls"] = check_calls.get(declared["function"], [])
        declared["locators"] = locators.get(declared["function"], [])
        declared["vets"] = vets.get(declared["function"], [])
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


def _harness_module(name: str) -> Any:
    """Import a sibling harness module by name.

    Not a module-scope `import ostler_qa_hierarchy`, because this file is also loaded from
    the *ostler* side by path (`harness_host.load_harness_module`) with the harness
    directory nowhere on `sys.path` — a top-level sibling import would make loading this
    module for its constants raise `ModuleNotFoundError`. Inside a scenario the directory is
    already on `PYTHONPATH`; the insert is what makes the two callers agree.
    """
    import importlib

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module(name)


def _open_browser(qa: Qa) -> Any:
    """Start Playwright for a browser target and hand the page to the scenario.

    The import is here rather than at module scope because this file also runs under the
    interpreter of a project that tests nothing but an HTTP API, and playwright is a heavy
    dependency to demand of it. There is no fallback: a `playwright` target on an
    interpreter without playwright is an error, and it says which interpreter and what to
    install rather than degrading into a scenario that silently proves nothing.
    """
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
    )
    qa.page = browser.open()
    qa.diagnostics = browser
    return browser


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
    )
    browser = None
    status, error = "passed", None
    try:
        # Inside the try: a browser that will not start is a scenario that errored, with a
        # traceback in the record. Outside it the process would die before emitting anything
        # and the driver could only report that no result arrived.
        if target_decl.driver == "playwright":
            browser = _open_browser(qa)
        declared.func(qa)
    except CheckFailed:
        status = "failed"
    except BaseException:  # noqa: BLE001 - the traceback is the scenario's verdict
        status, error = "errored", traceback.format_exc()
        # Also to stdout, which ostler keeps as an artifact. The record carries the same
        # text, but a person debugging a red scenario opens the output file — and finding it
        # empty is what sends them to re-run the scenario by hand to see the exception.
        print(error, file=sys.stdout)
    if browser is not None:
        # Closing is what finalizes the trace and the video, so it happens before the
        # verdict is emitted — but its complaints are appended to the verdict, never
        # substituted for it.
        problems = browser.close(failed=status != "passed")
        if problems:
            status = "failed" if status == "passed" else status
            error = "; ".join([part for part in [error, *problems] if part])
    if qa.failures:
        status = "failed" if status == "passed" else status
    # A scenario that claims coverage and recorded nothing has proved nothing. Reporting it
    # as passed is exactly the vacuity this format exists to end, so it is a failure here
    # rather than a reviewer's job four laps later.
    # The same vacuity one layer out: on a UI target every assertion can hold while the page
    # renders as a sliver against one margin. `validate` refuses a plan whose UI scenario
    # never vets; this is the half a plan cannot lie its way past, since it counts the calls
    # that actually ran.
    if status == "passed" and target_decl.driver in UI_DRIVERS and qa.vets == 0:
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
    # `python -m ostler_qa` binds this file to `__main__`, so a plan's own
    # `from ostler_qa import scenario` would import a *second* copy — with a second,
    # empty REGISTRY, and a describe that reports no scenarios at all. Alias the name to
    # the running module before any plan is imported.
    sys.modules.setdefault("ostler_qa", sys.modules["__main__"])
    raise SystemExit(main())
