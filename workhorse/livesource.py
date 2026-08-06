"""Installing a package from a read-only bind, without importing the bind itself.

Harness code, like `supervisor.py` beside it: COPY'd into the image, not part of the
`workhorse-agent` distribution.

The container installs some packages from a host bind rather than from the image, so
an edit on the host reaches the next start with no rebuild. Doing that with a plain
`uv tool install --editable /mnt/<pkg>-src` means the running process imports **live
from the bind** — and that is the bug: the operator is editing the very files a
running process is importing, so a save part-way through a multi-file change is a
torn import waiting to happen, and there is nothing to fall back to when the edit is
wrong.

So the bind is never imported. Each refresh copies it to a **new generation
directory** and installs from that copy:

    /mnt/<name>-src          read-only bind of the host source   (never imported)
    /opt/live/<name>/0001    writable copy, installed            (imported)
    /opt/live/<name>/0002    the next refresh                    (imported after it)

Two properties fall out, and both are the point:

* A generation directory is written once and never touched again, so a process
  importing from it cannot see a half-saved file — whatever the operator is doing on
  the host meanwhile.
* A refresh that fails to install leaves the previous generation in place and still
  installed, so a bad edit costs a restart rather than the observer.

It is deliberately generic over the package. groom's sidecar is the first caller;
a workflow distribution installed from a local path (pipx discovery, §4.6 of
the internal container-concurrent-runs plan) is the second, and it needs no second
implementation.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("supervisor.livesource")

# Never copied into a generation. `.venv` and `node_modules` are the expensive ones
# and are rebuilt by the install anyway; `.git` can dwarf the source it belongs to;
# bytecode from another interpreter is worse than useless.
COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "node_modules", "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache"
)

# How many generations survive a refresh. Two, so the *previous* one is still on disk
# while a process started from it is running — killing the directory out from under a
# live import is precisely what this module exists to avoid.
KEEP_GENERATIONS = 2


@dataclass(frozen=True)
class LiveSource:
    """A package installed from a host bind, one generation at a time."""

    name: str
    # The read-only bind. Absent when the operator did not mount it, which is a
    # supported configuration rather than an error.
    mount: Path
    # Where this package's generations live. Container-local on purpose: a copy of
    # the host source is per-container state, and a fresh container should re-stage
    # rather than inherit a generation staged from some earlier edit.
    root: Path
    # Extra local packages to install alongside it. groom's sidecar needs the image's
    # own workhorse here, not a released one — see `observer_source` in supervisor.py.
    with_editable: tuple[Path, ...] = field(default_factory=tuple)


def generations(root: Path) -> list[Path]:
    """Existing generation dirs, oldest first.

    Names are zero-padded numbers so lexical order is chronological order, which is
    what lets this be a plain sort rather than a stat of every entry.
    """
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit())


def stage(source: LiveSource) -> Path | None:
    """Copy the bind into a fresh generation dir and return it.

    Returns None when there is nothing to stage — no mount, or a copy that failed.
    Neither is fatal: the caller keeps whatever generation it already had.
    """
    if not source.mount.is_dir():
        return None
    existing = generations(source.root)
    nth = int(existing[-1].name) + 1 if existing else 1
    target = source.root / f"{nth:04d}"
    try:
        source.root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source.mount, target, ignore=COPY_IGNORE, symlinks=True)
    except OSError as exc:
        log.warning("could not stage %s generation %s: %s", source.name, nth, exc)
        shutil.rmtree(target, ignore_errors=True)
        return None
    return target


def install(source: LiveSource, generation: Path, bin_dir: Path) -> bool:
    """Install one generation as a uv tool, returning whether it worked.

    `--no-sources` keeps the install standalone: the source declares workspace
    members this copy does not contain, and resolving them would fail on a directory
    that only ever holds one package. What the package genuinely needs from *this
    image* is passed explicitly through `with_editable` instead.
    """
    cmd = ["uv", "tool", "install", "--force", "--editable", str(generation), "--no-sources"]
    for extra in source.with_editable:
        cmd += ["--with-editable", str(extra)]
    try:
        result = _run(cmd, bin_dir)
    except OSError as exc:  # uv itself missing — nothing to recover from, not fatal
        log.warning("could not install %s: %s", source.name, exc)
        return False
    if result.returncode != 0:
        log.warning(
            "installing %s generation %s failed (exit %d); keeping the previous one",
            source.name, generation.name, result.returncode,
        )
        return False
    return True


def _run(cmd: list[str], bin_dir: Path) -> subprocess.CompletedProcess[bytes]:
    """The one place this module spawns anything — and so the one test seam."""
    return subprocess.run(
        cmd,
        env={**os.environ, "UV_TOOL_BIN_DIR": str(bin_dir)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )


def prune(root: Path, keep: int = KEEP_GENERATIONS) -> None:
    """Drop all but the newest `keep` generations. Best-effort by design."""
    for stale in generations(root)[:-keep] if keep > 0 else generations(root):
        shutil.rmtree(stale, ignore_errors=True)


def refresh(source: LiveSource, bin_dir: Path) -> Path | None:
    """Stage a new generation and install it. Returns the generation now installed.

    None means nothing changed — there was no mount, the copy failed, or the install
    failed. In every one of those cases the previously installed generation is still
    there and still installed, which is what makes a bad edit survivable.
    """
    generation = stage(source)
    if generation is None:
        return None
    if not install(source, generation, bin_dir):
        # The failed copy is removed rather than kept: leaving it would make the next
        # refresh's generation number skip, and it is not installed by anything.
        shutil.rmtree(generation, ignore_errors=True)
        return None
    log.info("%s: installed generation %s", source.name, generation.name)
    prune(source.root)
    return generation
