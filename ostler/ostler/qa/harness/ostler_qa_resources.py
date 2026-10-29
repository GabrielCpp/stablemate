"""Outside services a run borrows from and reads: the desk that probes a resource, sends the requests a fixture's steps and a claim's observations name, and gives back what was borrowed."""

from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

FaultSink = Callable[[str, int, str, str, str], None]
EventSink = Callable[[Mapping[str, Any]], None]

READ_INTERVAL_S = 0.5


@dataclass(frozen=True)
class Reply:
    """What a resource answered: its status and the body it sent."""
    status: int
    body: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass(frozen=True)
class Observed:
    """A resource's document as the last read returned it."""
    status: int
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass
class PendingRelease:
    fixture: str
    index: int
    resource: str
    method: str
    path: str
    body: str | None
    env: Mapping[str, str]
    timeout: float


@dataclass
class ResourceDesk:
    """The resources a book names, probed once per run, with the releases a borrow owes."""
    resources: Mapping[str, Mapping[str, Any]]
    fault: FaultSink
    emit: EventSink
    scenario: str
    probed: dict[str, str] = field(default_factory=dict)
    releases: list[PendingRelease] = field(default_factory=list)

    def known(self, stem: str) -> Mapping[str, Any]:
        spec = self.resources.get(stem)
        if spec is None:
            detail = f"names resource {stem!r}, which no resource page in the book declares"
            self.fault(stem, -1, "probe", "defect", detail)
            raise RuntimeError(f"qa resource {stem!r} {detail}")
        return spec

    def secrets_of(self, stem: str) -> dict[str, str]:
        """The values of the secrets a resource needs, read from the harness's own environment."""
        spec = self.known(stem)
        credential = spec.get("credential") or {}
        names = [*spec.get("secrets", []), *([credential["secret"]] if credential.get("secret") else [])]
        values: dict[str, str] = {}
        for name in names:
            value = os.environ.get(name)
            if value is None:
                self._unavailable(stem, f"secret {name!r} is not set in the harness's own environment")
            values[name] = str(value)
        return values

    def base_of(self, stem: str) -> str:
        spec = self.known(stem)
        base = os.path.expandvars(str(spec.get("base", ""))).rstrip("/")
        if "$" in base or not base:
            self._unavailable(stem, f"base {spec.get('base')!r} names an environment variable that is not set")
        return base

    def headers_of(self, stem: str) -> dict[str, str]:
        credential = self.known(stem).get("credential")
        if not credential:
            return {}
        value = self.secrets_of(stem)[credential["secret"]]
        scheme = credential.get("scheme") or ""
        return {credential["header"]: f"{scheme} {value}".strip()}

    def _unavailable(self, stem: str, detail: str) -> None:
        self.probed[stem] = detail
        self.fault(stem, -1, "probe", "capability", detail)
        raise RuntimeError(f"qa resource {stem!r} is unavailable: {detail}")

    def ensure_reachable(self, stem: str) -> None:
        """Run the resource's probe once per run, and gap every claim that needs it when it does not answer."""
        spec = self.known(stem)
        if stem in self.probed:
            cached = self.probed[stem]
            if cached:
                self._unavailable(stem, cached)
            return
        if spec.get("reach") == "cli":
            self._probe_cli(stem, spec)
        else:
            self._probe_http(stem, spec)
        self.probed[stem] = ""

    def _probe_http(self, stem: str, spec: Mapping[str, Any]) -> None:
        probe = spec.get("probe") or {}
        request = probe.get("request") or {"method": "GET", "path": "/"}
        try:
            reply = self.send(stem, request["method"], request["path"], None, float(probe.get("timeout", 30)))
        except OSError as exc:
            self._unavailable(stem, f"{request['method']} {request['path']} could not connect: {exc}")
        else:
            if not reply.ok:
                self._unavailable(stem, f"{request['method']} {request['path']} answered {reply.status}")

    def _probe_cli(self, stem: str, spec: Mapping[str, Any]) -> None:
        binary = str(spec.get("binary", ""))
        if shutil.which(binary) is None:
            hint = f" ({spec['install']})" if spec.get("install") else ""
            self._unavailable(stem, f"binary {binary!r} is not on the PATH{hint}")
        env = {**os.environ, **self.secrets_of(stem)}
        command = str((spec.get("probe") or {}).get("command", ""))
        if not command:
            return
        try:
            done = subprocess.run(  # noqa: S603 - a book-declared probe
                ["/bin/sh", "-c", command], env=env, capture_output=True, text=True, check=False,
                timeout=float((spec.get("probe") or {}).get("timeout", 30)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._unavailable(stem, f"probe could not run: {exc}")
        else:
            if done.returncode != 0:
                self._unavailable(stem, f"probe exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}")

    def send(self, stem: str, method: str, path: str, body: str | None, timeout: float) -> Reply:
        """One request to a resource, carrying its credential. An HTTP error status is an answer, not an exception."""
        url = self.base_of(stem) + path
        headers = self.headers_of(stem)
        data = body.encode("utf-8") if body is not None else None
        if data is not None:
            headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=timeout) as raw:  # noqa: S310
                return Reply(raw.status, raw.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            return Reply(exc.code, exc.read().decode("utf-8", errors="replace"))
        except urllib.error.URLError as exc:
            raise OSError(str(exc.reason)) from exc

    def register_release(self, pending: PendingRelease, secrets: Sequence[str]) -> None:
        """Remember a release the scenario owes, and announce it so a run that dies before it can still be cleaned up."""
        self.releases.append(pending)
        shown = {k: v for k, v in pending.env.items() if k not in secrets}
        path = string.Template(pending.path).safe_substitute(shown)
        self.emit({"type": "release-pending", "scenario": self.scenario, "fixture": pending.fixture,
                   "step": pending.index, "resource": pending.resource, "method": pending.method, "path": path})

    def release_all(self) -> list[str]:
        """Send every owed release, last borrowed first. Each runs on its own, and the problems come back."""
        problems: list[str] = []
        owed, self.releases = self.releases[::-1], []
        for pending in owed:
            ok, detail = True, ""
            try:
                path = string.Template(pending.path).substitute(pending.env)
                body = string.Template(pending.body).substitute(pending.env) if pending.body else None
                reply = self.send(pending.resource, pending.method, path, body, pending.timeout)
                ok = reply.ok
                detail = "" if ok else f"{pending.method} {path} answered {reply.status}"
            except (OSError, KeyError, ValueError, RuntimeError) as exc:
                ok, detail = False, f"{pending.method} {pending.path} failed: {exc}"
            self.emit({"type": "release", "scenario": self.scenario, "fixture": pending.fixture,
                       "step": pending.index, "ok": ok, "detail": detail})
            if not ok:
                problems.append(f"release {pending.fixture!r} step {pending.index} failed: {detail}")
        return problems

    def observe(
        self, stem: str, observation: str, path: str, *, within: float,
        holds: Callable[[Observed], bool],
    ) -> Observed:
        """Read an observation, re-reading until *holds* or *within* seconds pass, and return the last read."""
        self.ensure_reachable(stem)
        spec = self.known(stem)
        step = (spec.get("observations") or {}).get(observation)
        if step is None:
            detail = f"resource {stem!r} declares no observation {observation!r}"
            self.fault(stem, -1, "observe", "defect", detail)
            raise RuntimeError(f"qa {detail}")
        timeout = float((step or {}).get("timeout", 30))
        started = time.monotonic()
        polls = 0
        last: Observed | None = None
        error = ""
        while True:
            polls += 1
            try:
                reply = self.send(stem, "GET", path, None, timeout)
                last, error = Observed(reply.status, reply.body), ""
                if reply.ok and holds(last):
                    break
                if not reply.ok:
                    error = f"GET {path} answered {reply.status}"
            except OSError as exc:
                error = f"GET {path} could not connect: {exc}"
            except ValueError:
                error = ""
            elapsed = time.monotonic() - started
            if elapsed >= within:
                break
            time.sleep(min(READ_INTERVAL_S, within - elapsed))
        elapsed = time.monotonic() - started
        self.emit({"type": "observe", "scenario": self.scenario, "resource": stem, "observation": observation,
                   "polls": polls, "elapsed_ms": int(elapsed * 1000)})
        if last is None or error:
            detail = error or f"GET {path} returned nothing"
            self.fault(stem, -1, "observe", "defect", detail)
            raise RuntimeError(f"qa observation {stem}.{observation}: {detail}")
        return last
