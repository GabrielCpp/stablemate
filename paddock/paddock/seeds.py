"""Capture a repo into a seed, and put a seed back on disk."""

from __future__ import annotations

import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from paddock import archive, paths
from paddock.pointer import Pointer, PointerError

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 60


class SeedError(RuntimeError):
    """A capture that must not proceed, or a seed that cannot be put on disk."""


@dataclass(frozen=True, slots=True)
class Captured:
    pointer: Pointer
    zip_path: Path
    pointer_path: Path


def git_head(repo: Path) -> tuple[str, bool]:
    """`(HEAD sha, working tree is dirty)`, or `("", False)` outside a git repo."""
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False
        )

    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        return "", False
    status = git("status", "--porcelain")
    return head.stdout.strip(), bool(status.stdout.strip())


def farrier_installed(repo: Path) -> bool:
    """Whether the repo carries an installed agents layer."""
    return (repo / "agents.yml").exists() or (repo / ".claude").is_dir()


def in_tree_source(repo: Path, data_dir: Path) -> str:
    """*repo* relative to the data directory, or `""` when it is somewhere else on disk."""
    try:
        return repo.resolve().relative_to(data_dir.resolve()).as_posix()
    except ValueError:
        return ""


def _carried_over(
    pointer_path: Path, *, url: str, note: str, excludes: tuple[str, ...]
) -> tuple[str, str, tuple[str, ...]]:
    """Inherit `url`, `note` and `excludes` from the pointer being replaced, unless named here."""
    if not pointer_path.exists():
        return url, note, excludes
    previous = Pointer.load(pointer_path)
    return url or previous.url, note or previous.note, excludes or previous.excludes


def capture(
    repo: Path,
    *,
    name: str,
    data_dir: Path,
    store: Path,
    excludes: tuple[str, ...] = (),
    url: str = "",
    note: str = "",
    force: bool = False,
) -> Captured:
    repo = repo.resolve()
    if not repo.is_dir():
        raise SeedError(f"{repo}: not a directory")
    pointer_path = paths.seed_pointer(data_dir, name)
    if pointer_path.exists() and not force:
        raise SeedError(f"{pointer_path}: seed '{name}' already exists (pass --force to replace)")
    url, note, excludes = _carried_over(pointer_path, url=url, note=note, excludes=excludes)

    junk = archive.junk_in(repo, excludes)
    if junk:
        listed = "\n  ".join(junk)
        raise SeedError(
            f"{repo}: build output or a local environment is still in the tree:\n  {listed}\n"
            "Clean it, or name it with --exclude if the fixture genuinely needs it."
        )
    if not farrier_installed(repo):
        logger.warning(
            "%s carries no agents.yml or .claude/ — capturing a repo farrier never installed into",
            repo,
        )

    head, dirty = git_head(repo)
    zip_path = paths.seed_zip(store, name)
    archive.create(repo, zip_path, prefix=repo.name, excludes=excludes)
    pointer = Pointer(
        name=name,
        repo_dir=repo.name,
        sha256=archive.digest(zip_path),
        bytes=zip_path.stat().st_size,
        head=head,
        dirty=dirty,
        url=url,
        note=note,
        source=in_tree_source(repo, data_dir),
        tree_sha256=archive.tree_digest(repo, excludes),
        excludes=tuple(excludes),
    )
    pointer.write(pointer_path)
    return Captured(pointer=pointer, zip_path=zip_path, pointer_path=pointer_path)


def fetch(pointer: Pointer, *, store: Path, force: bool = False) -> Path:
    """Put the pointer's zip in the store, downloading it only if it is not already right."""
    zip_path = paths.seed_zip(store, pointer.name)
    if zip_path.exists() and not force:
        try:
            pointer.verify(zip_path)
        except PointerError:
            logger.warning("%s does not match the pointer; re-fetching", zip_path)
        else:
            return zip_path
    if not pointer.url:
        raise SeedError(
            f"seed '{pointer.name}' has no url and is not in the store at {zip_path}; "
            "capture it locally or add a url to its pointer"
        )
    scheme = urlparse(pointer.url).scheme
    if scheme != "https":
        raise SeedError(f"seed '{pointer.name}': only https urls are fetched, got {scheme or '(none)'}://")

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    draft = zip_path.with_name(zip_path.name + ".part")
    logger.info("fetching %s -> %s", pointer.url, zip_path)
    try:
        with urllib.request.urlopen(pointer.url, timeout=FETCH_TIMEOUT_S) as response:  # noqa: S310 - scheme checked above
            with draft.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (urllib.error.URLError, OSError) as exc:
        draft.unlink(missing_ok=True)
        raise SeedError(f"fetching {pointer.url}: {exc}") from exc
    actual = archive.digest(draft)
    if actual != pointer.sha256:
        draft.unlink(missing_ok=True)
        raise SeedError(
            f"{pointer.url}: sha256 is {actual}, pointer '{pointer.name}' expects {pointer.sha256}"
        )
    draft.replace(zip_path)
    return zip_path


def unpack(
    pointer: Pointer, *, store: Path, dest: Path, install: bool = True, project: Path | None = None
) -> Path:
    """Extract the seed into *dest*, returning the repo tree inside it."""
    zip_path = fetch(pointer, store=store)
    pointer.verify(zip_path)
    repo = dest / pointer.repo_dir
    if repo.exists():
        shutil.rmtree(repo)
    archive.extract(zip_path, dest)
    if not repo.is_dir():
        raise SeedError(f"{zip_path}: expected a top-level {pointer.repo_dir}/ inside the archive")
    if install:
        reinstall(repo, project=project)
    return repo


def reinstall(repo: Path, *, project: Path | None = None) -> bool:
    """Re-run `farrier install` so the machine-local layer points at *this* path."""
    if not farrier_installed(repo):
        return False
    argv = ["uv", "run", *(("--project", str(project)) if project else ()), "farrier", "install", "--repo", str(repo)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.warning(
            "farrier install failed for %s (exit %d); machine-local paths in the seed are stale:\n%s",
            repo,
            result.returncode,
            result.stderr.strip(),
        )
        return False
    return True
