"""Run a QA scenario on a machine where the repository is not on disk.

QA is supposed to prove that the product behaves, not that its test suite passes. The rule
saying so has always been prose in a prompt — *a source check, unit test, build or
narrative is not behavioral evidence* — and prose cannot filter prose: the audits keep
finding plans whose acceptance criteria rest on a suite's exit code.

This module replaces the rule with the absence of the capability. A sandboxed scenario runs
in a container that has an interpreter, the QA harness, and its own spec directory — and
nothing else. `go test ./...` fails on a missing directory. `npx vitest` fails on a missing
command. A jsdom overclaim is impossible because there is no source to import. Nothing has
to police it, and there is nothing to argue with.

Three decisions carry most of the design:

**Paths are identical on both sides.** The spec directory is bind-mounted at its own host
absolute path, and an empty tmpfs is mounted at the repository root. So a screenshot the
scenario writes at `/w/repo/docs/specs/07/qa/shot.png` is at that path on the host too, and
every existing host-side check — the manifest's `relative_to(spec_dir)`, the vetter's
sidecar lookup, `ffprobe` on a video — keeps working with no translation layer. Translating
paths instead would have meant maintaining a mapping in five places that each fail
differently, one of them by silently reporting a screen "was gone by the time it was
measured".

**One container per scenario.** `docker exec` into a long-lived container would break the
kill contract: on a timeout, killing the client leaves the scenario running inside, still
writing into the bind-mounted spec directory after the manifest was hashed. `docker run
--rm` plus `docker kill` reproduces "the process group dies, and its children with it"
exactly, and the ~300ms it costs is noise against a 300s scenario budget.

**Records travel by file, not by pipe.** An inherited fd does not cross a container
boundary and a FIFO's EOF is defined by writer count — which is unknowable when the writer
is a container you may have to kill. An append-only file degrades the way the reader
already expects: a truncated last line is dropped, and a missing terminal record is graded
as the failure it is.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ostler.qa.drivers import DisplayRecorder, DriverBlocked, Launcher, PythonDriver
from ostler.qa.gateway import Gateway, Verb
from ostler.qa.harness_host import harness_argv
from ostler.qa.session import QaSession, _redact_bytes

#: The repo-owned file the sandbox is configured from. Everything environment-specific —
#: the network to join, which port reaches which service, what the gateway allows — is
#: declared *by the repository under test*, never defaulted by ostler. A default network
#: name or forwarding rule baked in here would be a capability the plan's author could rely
#: on without ever declaring it.
STACK_FILE = "qa-stack.yml"

DEFAULT_BASE_IMAGE = "ostler-qa-sandbox:base"
DEFAULT_BROWSER_IMAGE = "ostler-qa-sandbox:browser"

#: Writable, and outside every mount that matters. The image sets `HOME` here too; the
#: tmpfs is what makes it writable for a container running as an arbitrary uid.
CONTAINER_HOME = "/tmp/sandbox-home"

#: Where the X sockets live by convention, and where a browser looks for them.
X11_SOCKET_DIR = "/tmp/.X11-unix"

#: Fixed, because the display lives in a container of its own — there is no other X server
#: in there to collide with, so the host's "pick a free number" dance buys nothing.
SANDBOX_DISPLAY = ":99"

#: Docker's own name for "the host, from in here". Requires `--add-host`, which every
#: container below gets.
HOST_ALIAS = "host.docker.internal"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _docker(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603, S607 — fixed argv, `docker` resolved from PATH
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass(frozen=True)
class SandboxConfig:
    """The `sandbox:` block of the repository's `qa-stack.yml`."""

    network: str = ""
    #: Loopback port inside the container -> `host:port` reachable from it. Plans hardcode
    #: `http://localhost:8090` inside scenario *bodies*, not only in `target(base_url=…)`,
    #: so rewriting target URLs cannot move a plan into a container and editing every
    #: literal would mean the plan that ran is not the plan that was reviewed.
    forward: dict[int, str] = field(default_factory=dict)
    base_image: str = DEFAULT_BASE_IMAGE
    browser_image: str = DEFAULT_BROWSER_IMAGE
    gateway_allow: tuple[Verb, ...] = ()

    @classmethod
    def load(cls, root: Path) -> "SandboxConfig":
        path = root / STACK_FILE
        raw: Any = {}
        if path.is_file():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded.get("sandbox") or {}
        if not isinstance(raw, dict):
            raise DriverBlocked(f"{STACK_FILE}: `sandbox:` must be a mapping")
        images = raw.get("images") or {}
        gateway = raw.get("gateway") or {}
        forward: dict[int, str] = {}
        for port, upstream in (raw.get("forward") or {}).items():
            text = str(upstream)
            if ":" not in text:
                raise DriverBlocked(
                    f"{STACK_FILE}: forward entry for port {port} must be `host:port`, got {text!r}"
                )
            forward[int(port)] = text
        try:
            allow = tuple(Verb.parse(entry) for entry in (gateway.get("allow") or ()))
        except ValueError as exc:
            raise DriverBlocked(f"{STACK_FILE}: {exc}") from exc
        return cls(
            network=str(raw.get("network", "")),
            forward=forward,
            base_image=str(images.get("base", DEFAULT_BASE_IMAGE)),
            browser_image=str(images.get("browser", DEFAULT_BROWSER_IMAGE)),
            gateway_allow=allow,
        )


class Sandbox:
    """Everything a sandboxed run owns, for exactly as long as the run.

    Run-scoped rather than a module singleton on purpose: a leaked container keeps a port
    and a bind mount, and the only place with a guaranteed teardown on every exception path
    is the runner's own `finally`.
    """

    def __init__(self, config: SandboxConfig, *, session: QaSession, root: Path) -> None:
        self.config = config
        self.session = session
        self.root = root.resolve()
        self.spec_dir = session.spec_dir.resolve()
        self.gateway = Gateway(session, self.root, list(config.gateway_allow))
        self.label = f"ostler.run_id={session.run_id}"
        self._workdir = Path(tempfile.mkdtemp(prefix="ostler-qa-sandbox-"))
        self._scratch: list[Path] = [self._workdir]
        self._checked_images: set[str] = set()

    # -- lifecycle ------------------------------------------------------------------------

    def start(self) -> None:
        if shutil.which("docker") is None:
            raise DriverBlocked("--sandbox needs docker on PATH, and it is not there")
        if self.spec_dir == self.root:
            # The tmpfs at the repo root would shadow the spec-directory bind, and the plan
            # module would vanish. Worth saying plainly rather than as an import error.
            raise DriverBlocked(
                "--sandbox needs the spec directory to sit below the repository root; "
                f"both resolve to {self.root}"
            )
        self.gateway.start()

    def stop(self) -> None:
        try:
            self.gateway.stop()
        finally:
            # A container that outlived its scenario holds a bind mount into the spec
            # directory. Sweeping by label is the only way to catch one whose `--rm` did not
            # fire, and it costs one docker call on a clean run.
            leaked = _docker("ps", "-aq", "--filter", f"label={self.label}").stdout.split()
            if leaked:
                _docker("rm", "-f", *leaked)
                self.session.append(
                    {"kind": "runner_error", "message": f"removed {len(leaked)} leaked container(s)"}
                )
            for path in self._scratch:
                shutil.rmtree(path, ignore_errors=True)

    def launcher_for(self, target_id: str, target: dict[str, Any]) -> "ContainerLauncher":
        browser = str(target.get("driver", "python")) == "playwright"
        image = self.config.browser_image if browser else self.config.base_image
        return ContainerLauncher(self, image=image, browser=browser)

    # -- shared plumbing ------------------------------------------------------------------

    @property
    def gateway_url(self) -> str:
        return f"http://{HOST_ALIAS}:{self.gateway.port}"

    def ensure_image(self, image: str) -> None:
        """Fail before the first scenario if the image is missing or cannot run the harness.

        Both halves matter. A missing image is obvious; an image that exists but whose
        harness will not start produces a run in which every scenario "produced no result",
        which reads as a plan defect for as long as it takes someone to try it by hand.
        """
        if image in self._checked_images:
            return
        if _docker("image", "inspect", image).returncode:
            raise DriverBlocked(
                f"the QA sandbox image '{image}' is not built — build it with:\n"
                f"  docker build -f docker/sandbox/Dockerfile --target <base|browser> "
                f"-t {image} <path to ostler>"
            )
        probe = _docker("run", "--rm", "--entrypoint", "python3", image, "-m", "ostler_qa")
        # The harness prints its usage and exits non-zero when called with no verb. That is
        # the positive signal: it means the module was found and executed.
        if "usage" not in (probe.stdout + probe.stderr).lower():
            detail = (probe.stderr or probe.stdout).strip()[-500:]
            raise DriverBlocked(
                f"the QA sandbox image '{image}' cannot run the harness: {detail}"
            )
        self._checked_images.add(image)

    def container_name(self, suffix: str) -> str:
        return _SAFE_NAME.sub("-", f"ostler-{self.session.run_id}-{suffix}")[:120]

    def scratch_dir(self, prefix: str) -> Path:
        path = Path(tempfile.mkdtemp(prefix=f"ostler-qa-{prefix}-"))
        self._scratch.append(path)
        return path

    def write_env_file(self, name: str, env: dict[str, str]) -> Path:
        """Hand the container its environment through a 0600 file, never through `-e`.

        `docker run -e SECRET=…` puts the value in the docker client's argv, where every
        other user on the machine reads it out of `ps`. A plan's secrets are real
        credentials for the live stack, so this is not a theoretical distinction.
        """
        path = self._workdir / f"{_SAFE_NAME.sub('-', name)}.env"
        lines = []
        for key, value in sorted(env.items()):
            if "\n" in value:
                raise DriverBlocked(
                    f"the value of '{key}' contains a newline, which docker --env-file "
                    "cannot carry into the sandbox"
                )
            lines.append(f"{key}={value}")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path

    def base_argv(self, name: str) -> list[str]:
        """The flags every container in the sandbox shares, minus the `docker` itself."""
        argv = [
            "run", "--rm",
            "--name", name,
            "--label", self.label,
            # The invoking uid, so artifacts written into the bind-mounted spec directory
            # belong to the human. Root-owned files there would survive the run and make the
            # *next* run's `shutil.rmtree(qa_dir)` fail with EPERM.
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--add-host", f"{HOST_ALIAS}:host-gateway",
        ]
        if self.config.network:
            argv += ["--network", self.config.network]
        return argv

    def mount_argv(self) -> list[str]:
        """Identity path mapping: the spec directory here, an empty repository root there.

        Docker mounts parents before children, so the tmpfs at the repository root is in
        place before the spec-directory bind lands inside it. The result is a filesystem
        where every path the plan knows is valid and nothing else from the repo exists.
        """
        return [
            "--tmpfs", str(self.root),
            "--tmpfs", CONTAINER_HOME,
            "-v", f"{self.spec_dir}:{self.spec_dir}",
            "-w", str(self.root),
        ]


class ContainerLauncher(Launcher):
    """Start each scenario as its own container, and grade it exactly as a local one."""

    def __init__(self, sandbox: Sandbox, *, image: str, browser: bool) -> None:
        self.sandbox = sandbox
        self.image = image
        self.browser = browser
        self._display: ContainerDisplayRecorder | None = None

    def preflight(self, driver: PythonDriver) -> None:
        # Deliberately *not* checking `driver.interpreter()`. A target that names the
        # project's `.venv` is naming a path that only exists on the host; in the sandbox
        # the image's own interpreter is the one that runs, and blocking on the venv's
        # absence would refuse every sandboxed run of every existing plan.
        self.sandbox.ensure_image(self.image)

    def window_recorder(
        self, driver: PythonDriver, *, width: int, height: int, fps: int
    ) -> DisplayRecorder:
        self._display = ContainerDisplayRecorder(
            self.sandbox,
            driver.session,
            driver.target_id,
            width=width,
            height=height,
            fps=fps,
            image=self.image,
        )
        return self._display

    def no_result_hint(self) -> str:
        return (
            " — it ran in the QA sandbox, where the repository is not on disk. A scenario "
            "there may import the standard library and its spec-directory siblings, and may "
            "reach the running system over HTTP; it cannot run the project's build or test "
            "tooling, and evidence that needed to would not have been behavioral evidence"
        )

    def execute(
        self, driver: PythonDriver, scenario_id: str, timeout: float, context: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str, int, bool]:
        session = driver.session
        record_path = session.qa_dir / "records" / f"{scenario_id}.ndjson"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        # Created host-side and empty: the container appends to it, and a file that already
        # exists is one the container's uid does not have to be able to create.
        record_path.write_text("", encoding="utf-8")

        name = self.sandbox.container_name(scenario_id)
        env_file = self.sandbox.write_env_file(scenario_id, self._env(driver, record_path))
        argv = [
            "docker",
            *self.sandbox.base_argv(name),
            *self.sandbox.mount_argv(),
            "--env-file", str(env_file),
        ]
        if self._display is not None:
            argv += ["-v", f"{self._display.socket_dir}:{X11_SOCKET_DIR}"]
        argv += [
            self.image,
            *harness_argv(
                Path("python3"),
                "run",
                str(driver.module_path()),
                scenario_id,
                json.dumps(context),
            ),
        ]

        process = subprocess.Popen(  # noqa: S603 — argv assembled above from resolved paths
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        timed_out = False
        try:
            output_raw, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # `docker kill`, not a signal to the client: the scenario is PID 1 inside, so
            # this is the container equivalent of killing the process group — everything the
            # scenario spawned goes with it, which is the guarantee a local run has.
            _docker("kill", name)
            output_raw, _ = process.communicate()
            timed_out = True

        records = _read_records(record_path)
        safe = _redact_bytes(output_raw or b"", session.secret_values.values())
        return records, safe.decode("utf-8", errors="replace"), process.returncode, timed_out

    def _env(self, driver: PythonDriver, record_path: Path) -> dict[str, str]:
        """Build the container's environment from nothing, and add only what is declared.

        `session.command_env()` is `{**os.environ, …}`, which is right for a local
        subprocess and wrong here: it would hand a sandbox `DOCKER_HOST`, `SSH_AUTH_SOCK`,
        `AWS_*`, `GITHUB_TOKEN`, the agent's own API key, and the `*_PROXY` variables that
        `urllib` in the harness silently honours. Starting from `{}` means a variable
        reaches the scenario because someone declared it.
        """
        session = driver.session
        env: dict[str, str] = {
            "QA_DIR": str(session.qa_dir),
            # Strict precedence over the inherited-fd channel, which names a host fd number
            # that in here is either closed or something else entirely.
            "OSTLER_QA_RECORD_PATH": str(record_path),
            "OSTLER_QA_GATEWAY_URL": self.sandbox.gateway_url,
            "OSTLER_QA_GATEWAY_TOKEN": self.sandbox.gateway.token,
            **{key: str(value) for key, value in session.env.items()},
            # Keyed by secret *name*: that is what the harness reads (`os.environ.get(name)`),
            # not the `from_env` variable it was sourced from on the host.
            **session.secret_values,
        }
        if self.sandbox.config.forward:
            env["OSTLER_SANDBOX_FORWARD"] = json.dumps(
                {str(port): upstream for port, upstream in self.sandbox.config.forward.items()}
            )
        if driver.launch_env.get("DISPLAY"):
            env["DISPLAY"] = driver.launch_env["DISPLAY"]
        return env


class ContainerDisplayRecorder(DisplayRecorder):
    """An X server and a screen recorder, each in a container, filming the sandbox.

    Sharing the host's X socket with the scenario container would be a hole straight through
    the wall this module exists to build, so the display moves too. Two containers rather
    than one because ffmpeg must be PID 1 in its own: it finalizes the mp4 on SIGINT, and
    `docker kill --signal=INT` only reaches PID 1. A shell holding both would swallow it and
    leave an unplayable file — which looks exactly like a recording that never happened.

    It subclasses `DisplayRecorder` for `_finalize`, which is the half that matters: the
    duration, dimension and frame-rate checks that stop an empty desktop from being filed as
    evidence apply identically wherever ffmpeg ran.
    """

    def __init__(
        self,
        sandbox: Sandbox,
        session: QaSession,
        target: str,
        *,
        width: int,
        height: int,
        fps: int,
        image: str,
    ) -> None:
        super().__init__(session, target, width=width, height=height, fps=fps)
        self.sandbox = sandbox
        self.image = image
        self.display = SANDBOX_DISPLAY
        self.socket_dir = sandbox.scratch_dir("x11")
        self._xvfb_name = sandbox.container_name(f"xvfb-{target}")
        self._ffmpeg_name = sandbox.container_name(f"ffmpeg-{target}")

    def start(self) -> dict[str, str]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        socket_mount = ["-v", f"{self.socket_dir}:{X11_SOCKET_DIR}"]
        xvfb = _docker(
            *self.sandbox.base_argv(self._xvfb_name), "-d", *socket_mount,
            "--entrypoint", "Xvfb", self.image,
            self.display, "-screen", "0", f"{self.width}x{self.height}x24", "-nolisten", "tcp",
        )
        if xvfb.returncode:
            raise DriverBlocked(f"sandbox X server would not start: {xvfb.stderr.strip()}")

        socket_file = self.socket_dir / f"X{self.display.lstrip(':')}"
        deadline = time.monotonic() + 15
        while not socket_file.exists():
            if time.monotonic() > deadline:
                raise DriverBlocked("sandbox X server did not publish its socket within 15s")
            time.sleep(0.1)

        ffmpeg = _docker(
            *self.sandbox.base_argv(self._ffmpeg_name), "-d", *socket_mount,
            # The video lands in the qa directory at its identity path, so the host-side
            # `ffprobe` and `register_artifact` need to know nothing about containers.
            "-v", f"{self.sandbox.spec_dir}:{self.sandbox.spec_dir}",
            "-e", f"DISPLAY={self.display}",
            "--entrypoint", "ffmpeg", self.image,
            *self.argv()[1:],
        )
        if ffmpeg.returncode:
            _docker("rm", "-f", self._xvfb_name)
            raise DriverBlocked(f"sandbox screen recorder would not start: {ffmpeg.stderr.strip()}")

        time.sleep(1.0)
        if _docker("inspect", "-f", "{{.State.Running}}", self._ffmpeg_name).stdout.strip() != "true":
            logs = _docker("logs", "--tail", "20", self._ffmpeg_name)
            _docker("rm", "-f", self._xvfb_name, self._ffmpeg_name)
            raise DriverBlocked(
                f"sandbox screen recorder exited immediately: {(logs.stderr or logs.stdout).strip()[-500:]}"
            )

        self.started = time.monotonic()
        self.start_offset = self.session.offset_ms()
        self.session.append(
            {"kind": "video_start", "target": self.target, "driver": "playwright", "mode": "window"}
        )
        return {"DISPLAY": self.display}

    def stop(self) -> None:
        try:
            # SIGINT, so ffmpeg writes its trailer and moves the `moov` atom. `docker stop`
            # sends SIGTERM, which ffmpeg treats as "die now" and leaves the file unplayable.
            _docker("kill", "--signal=INT", self._ffmpeg_name)
            _docker("wait", self._ffmpeg_name, timeout=30)
        except subprocess.TimeoutExpired:
            _docker("rm", "-f", self._ffmpeg_name)
        finally:
            _docker("rm", "-f", self._xvfb_name)
        self._finalize()


def _read_records(path: Path) -> list[dict[str, Any]]:
    """Read what the scenario managed to write, keeping whatever parsed.

    Read once, after the process is gone — there is no consumer of a live record stream, and
    polling a file to hand the same list to the same grader afterwards would only add a way
    to miss the tail. A half-written last line is dropped rather than raised on: a scenario
    that was killed mid-write still has an account of everything before that, and losing it
    would replace a legible partial failure with none at all.
    """
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
