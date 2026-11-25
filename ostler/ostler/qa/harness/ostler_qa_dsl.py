from __future__ import annotations

import inspect
import linecache
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import FunctionType
from typing import Any

from ostler_qa_diagnostics import DRIVER_NAMES, MECHANISMS, resolve_addresses


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
        base_url=resolve_addresses(base_url) if base_url is not None else None,
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
    """The line a scenario's definition opens on, its first decorator; ``0`` when its source is gone."""
    code = getattr(inspect.unwrap(func), "__code__", None)
    if code is None or not linecache.getlines(code.co_filename):
        return 0
    return code.co_firstlineno
