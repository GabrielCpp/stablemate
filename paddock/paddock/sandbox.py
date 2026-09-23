"""Run a command in a container that holds the stablemate tools as installed packages, and no stablemate checkout."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

IMAGE = "paddock-sandbox"
HOME = "/tmp/sandbox-home"
WORK = "/work"
RUNS = "/runs"
CONFIG = "/etc/stablemate/config.toml"
CREDENTIALS = f"{HOME}/.claude/.credentials.json"
BASE_LIBRARY = "/opt/stablemate/base-library"
DOCKERFILE = Path("paddock") / "docker" / "Dockerfile"


class SandboxError(RuntimeError):
    """A sandbox that cannot be built or started."""


def _run_or_raise(argv: Sequence[str], *, cwd: Path) -> None:
    proc = subprocess.run(list(argv), cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise SandboxError(f"`{' '.join(argv[:2])}` exited {proc.returncode}. Its output above names the cause")


def claude_code_version() -> str:
    """The Claude Code release this machine runs, so the container's agents behave as the host's do."""
    try:
        proc = subprocess.run(["claude", "--version"], capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SandboxError("no `claude` on this machine. Pass --claude-code-version to pick the release") from exc
    version = proc.stdout.split(" ", 1)[0].strip()
    if proc.returncode != 0 or not version:
        raise SandboxError("`claude --version` printed no version. Pass --claude-code-version to pick the release")
    return version


def build_context(root: Path, dest: Path) -> Path:
    """Put the Dockerfile and every workspace member's wheel in *dest*, so the image installs packages and copies no source tree."""
    _ = shutil.copy2(root / DOCKERFILE, dest / "Dockerfile")
    _run_or_raise(["uv", "build", "--all-packages", "--wheel", "--out-dir", str(dest / "wheels")], cwd=root)
    return dest


def build(root: Path, *, claude_code: str, tag: str = IMAGE) -> None:
    """Build the sandbox image from the packages of the checkout at *root*."""
    with tempfile.TemporaryDirectory(prefix="paddock-sandbox-") as scratch:
        context = build_context(root, Path(scratch))
        _run_or_raise(
            ["docker", "build", "--build-arg", f"CLAUDE_CODE_VERSION={claude_code}", "--tag", tag, str(context)],
            cwd=context,
        )


def _contains(outer: Path, inner: Path) -> bool:
    return inner == outer or inner.is_relative_to(outer)


@dataclass(frozen=True)
class Mount:
    """A host path the container sees, where it sees it, and whether it may write there."""

    source: Path
    target: str
    read_only: bool


@dataclass(frozen=True)
class Sandbox:
    """The paths a run sees: the app it works on, where its runs go, its model config, the agent login and, when named, the base library its skills render from."""

    app: Path
    runs_dir: Path
    config: Path
    credentials: Path
    image: str = IMAGE
    base_library: Path | None = None

    def app_dir(self) -> str:
        """Where the app sits inside the container. The name is kept, because a repo's name is read from its directory."""
        return f"{WORK}/{self.app.name}"

    def mounts(self) -> tuple[Mount, ...]:
        """Every path the container sees."""
        library = () if self.base_library is None else (Mount(self.base_library, BASE_LIBRARY, read_only=True),)
        return (
            Mount(self.app, self.app_dir(), read_only=False),
            Mount(self.runs_dir, RUNS, read_only=False),
            Mount(self.config, CONFIG, read_only=True),
            Mount(self.credentials, CREDENTIALS, read_only=False),
            *library,
        )

    def refusals(self, checkout: Path) -> tuple[str, ...]:
        """Each mount that is missing, or that would show the container the stablemate checkout at *checkout*."""
        found: list[str] = []
        for mount in self.mounts():
            if not mount.source.exists():
                found.append(f"{mount.source} does not exist. Create it, or name another path for {mount.target}")
            elif _contains(mount.source.resolve(), checkout.resolve()):
                found.append(
                    f"{mount.source} holds the stablemate checkout at {checkout}, so the run would see it. "
                    + f"Copy what {mount.target} needs out of it and mount the copy"
                )
        return tuple(found)

    def docker_run_argv(self, command: Sequence[str], *, uid: int, gid: int, name: str = "") -> list[str]:
        """The `docker run` line that runs *command* in the app, as *uid*, seeing nothing but the mounts."""
        volume_flags = [
            f"--volume={mount.source.resolve()}:{mount.target}{':ro' if mount.read_only else ''}"
            for mount in self.mounts()
        ]
        name_flag = [f"--name={name}"] if name else []
        base_library_env = [] if self.base_library is None else [f"--env=STABLEMATE_BASE_DIR={BASE_LIBRARY}"]
        return [
            "docker", "run", "--rm", "--init",
            f"--user={uid}:{gid}",
            f"--workdir={self.app_dir()}",
            f"--env=STABLEMATE_CONFIG={CONFIG}",
            *base_library_env,
            *name_flag,
            *volume_flags,
            self.image,
            *command,
        ]
