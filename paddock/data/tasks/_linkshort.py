"""The link-shortener acceptance gate: twelve black-box checks over a built product."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

TOTAL = 12

SERVER_PORT = 18081

PROJECT_ID = "paddock-gate"

EMULATOR_WAIT_S = 120.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A 302 is the answer under test, not a hop to follow."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _request(
    method: str, url: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, str], str]:
    """One HTTP exchange as `(status, headers, body)`; status 0 when nothing answered."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        return 0, {}, str(err)


def run_checks(base: str, restart: Callable[[], None]) -> list[dict[str, Any]]:
    """The twelve checks, over a server already listening at *base*."""
    checks: list[dict[str, Any]] = []

    def note(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    destination = "https://example.com/articles/2026/a-rather-long-destination?ref=paddock"
    status, _, body = _request("POST", f"{base}/links", {"url": destination})
    note("create returns 201", status == 201, f"status {status}")
    try:
        created = json.loads(body)
    except json.JSONDecodeError:
        created = {}
    key = str(created.get("key") or "")
    note("create body carries a key", bool(key), body[:200])
    note(
        "short_url is base/<key>",
        bool(key) and str(created.get("short_url") or "") == f"{base}/{key}",
        str(created.get("short_url") or body[:200]),
    )

    status, headers, _ = _request("GET", f"{base}/{key or 'never-minted'}")
    note(
        "redirect is a 302 to the destination",
        status == 302 and headers.get("Location") == destination,
        f"status {status}, location {headers.get('Location')!r}",
    )

    status, _, body = _request("GET", f"{base}/no-such-key-000000")
    note("unknown key is a 404", status == 404, f"status {status}")
    note("404 body is a problem with a title", '"title"' in body and "Not Found" in body, body[:200])

    for name, payload in (
        ("relative url is a 400", {"url": "/relative/path"}),
        ("javascript url is a 400", {"url": "javascript:alert(1)"}),
        ("empty url is a 400", {"url": ""}),
        ("missing url is a 400", {}),
    ):
        status, _, body = _request("POST", f"{base}/links", payload)
        note(name, status == 400 and '"title"' in body, f"status {status}: {body[:120]}")

    status, _, body = _request("POST", f"{base}/links", {"url": destination})
    try:
        second = str(json.loads(body).get("key") or "")
    except json.JSONDecodeError:
        second = ""
    note(
        "repeated destination mints a distinct key",
        status == 201 and bool(second) and second != key,
        f"{key!r} then {second!r}",
    )

    restart()
    status, headers, _ = _request("GET", f"{base}/{key or 'never-minted'}")
    note(
        "key survives a server restart",
        status == 302 and headers.get("Location") == destination,
        f"status {status}, location {headers.get('Location')!r}",
    )
    return checks




def _free_port() -> int:
    with socket.socket() as probe_socket:
        probe_socket.bind(("localhost", 0))
        return int(probe_socket.getsockname()[1])


def _port_free(port: int) -> bool:
    with socket.socket() as probe_socket:
        return probe_socket.connect_ex(("localhost", port)) != 0


def _spawn(argv: list[str], log: IO[str], **kwargs: Any) -> subprocess.Popen[str]:
    """Start a service in its own session, so stopping it stops its whole process group."""
    return subprocess.Popen(
        argv, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, **kwargs
    )


def _stop(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    with_group = getattr(os, "killpg", None)
    try:
        if with_group:
            with_group(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
        try:
            if with_group:
                with_group(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError):
            return
        proc.wait(timeout=10)


def _wait_http(url: str, budget_s: float) -> bool:
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        status, _, _ = _request("GET", url)
        if status:
            return True
        time.sleep(1.0)
    return False


def _wait_port(port: int, budget_s: float) -> bool:
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        if not _port_free(port):
            return True
        time.sleep(0.25)
    return False




def probe(product: Path, workdir: Path, log_dir: Path) -> dict[str, Any]:
    """Build, serve and grade one product tree."""
    api = product / "api"
    if not (api / "go.mod").is_file():
        return {"ran": False, "reason": f"no Go module at {api}"}
    for tool in ("go", "gcloud"):
        if shutil.which(tool) is None:
            return {"ran": False, "reason": f"{tool} is not on PATH"}
    if not _port_free(SERVER_PORT):
        return {
            "ran": False,
            "reason": f"port {SERVER_PORT} is already taken and the product hardcodes it",
        }

    workdir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    binary = workdir / "server"
    build = subprocess.run(
        ["go", "build", "-o", str(binary), "./cmd/server"],
        cwd=str(api), capture_output=True, text=True, check=False,
    )
    (log_dir / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    if build.returncode != 0:
        return {
            "ran": True, "passed": 0, "total": TOTAL, "checks": [],
            "reason": f"go build exited {build.returncode} — see build.log",
        }

    emulator_port = _free_port()
    env = {
        **os.environ,
        "FIRESTORE_EMULATOR_HOST": f"localhost:{emulator_port}",
        "FIRESTORE_PROJECT_ID": PROJECT_ID,
        "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
    }
    server: subprocess.Popen[str] | None = None
    with (log_dir / "emulator.log").open("w", encoding="utf-8") as emulator_log:
        emulator = _spawn(
            [
                "gcloud", "emulators", "firestore", "start",
                f"--host-port=localhost:{emulator_port}",
            ],
            emulator_log,
        )
        try:
            if not _wait_http(f"http://localhost:{emulator_port}/", EMULATOR_WAIT_S):
                return {
                    "ran": False,
                    "reason": f"firestore emulator did not answer within {EMULATOR_WAIT_S:.0f}s",
                }

            def start() -> subprocess.Popen[str]:
                with (log_dir / "server.log").open("a", encoding="utf-8") as server_log:
                    return _spawn([str(binary)], server_log, cwd=str(workdir), env=env)

            def restart() -> None:
                nonlocal server
                _stop(server)
                server = start()
                _wait_port(SERVER_PORT, 30.0)

            server = start()
            if not _wait_port(SERVER_PORT, 30.0):
                return {
                    "ran": True, "passed": 0, "total": TOTAL, "checks": [],
                    "reason": f"server never listened on :{SERVER_PORT} — see server.log",
                }
            checks = run_checks(f"http://localhost:{SERVER_PORT}", restart)
            return {
                "ran": True,
                "passed": sum(1 for check in checks if check["ok"]),
                "total": TOTAL,
                "checks": checks,
            }
        finally:
            _stop(server)
            _stop(emulator)


def gate_line(outcome: dict[str, Any]) -> str:
    """The headline fragment for one gate outcome."""
    if not outcome.get("ran"):
        return "gate not run"
    return f"gate {outcome['passed']}/{outcome['total']}"


def gate_detail(run_id: str, outcome: dict[str, Any]) -> list[str]:
    """The detail lines for one gate outcome: the score, then every check that is not ok."""
    if not outcome.get("ran"):
        return [f"  {run_id}: gate not run — {outcome.get('reason', '')}"]
    lines = [f"  {run_id}: {gate_line(outcome)}"]
    if outcome.get("reason"):
        lines.append(f"    {outcome['reason']}")
    lines.extend(
        f"    not ok: {check['name']} ({check['detail']})"
        for check in outcome.get("checks", [])
        if not check["ok"]
    )
    return lines
