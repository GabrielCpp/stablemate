"""Capture a repo into a seed, and put a seed back on disk.

The three verbs the CLI exposes, with the policy in one place:

* **capture** — zip a repo as it stands, refuse the junk that must never enter a fixture,
  and write the tracked pointer beside it.
* **fetch** — bring a pointer's zip onto this machine over plain HTTPS, verified by
  sha256 before it is allowed into the store.
* **unpack** — verify, extract, and re-point the machine-local bits that a zip cannot
  carry correctly.

That last clause is the one with teeth. A repo carries absolute paths in places a zip
reproduces faithfully and uselessly: a `.git/hooks/*` shim naming an interpreter under
the capture machine's home, a `.venv` symlink (refused outright), a farrier-installed
agents layer generated for a path that no longer exists. Unpack rewrites what it can
identify and says what it could not.
"""

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

#: How long a fetch may stall with no bytes moving before it is abandoned. A seed is
#: hundreds of MiB, so this bounds silence, not the transfer.
FETCH_TIMEOUT_S = 60


class SeedError(RuntimeError):
    """A capture that must not proceed, or a seed that cannot be put on disk."""


@dataclass(frozen=True, slots=True)
class Captured:
    pointer: Pointer
    zip_path: Path
    pointer_path: Path


def git_head(repo: Path) -> tuple[str, bool]:
    """`(HEAD sha, working tree is dirty)`, or `("", False)` outside a git repo.

    Recorded for legibility only — the sha256 is what identifies the seed. A pointer
    saying which commit a fixture was captured at is how a human reading the tree six
    months later can tell whether it predates a change they care about.
    """
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
    """Whether the repo carries an installed agents layer.

    A seed captured before `farrier install` runs is legal — a genesis task starts from
    a bare repo on purpose — so this is a warning at capture, never a refusal.
    """
    return (repo / "agents.yml").exists() or (repo / ".claude").is_dir()


def in_tree_source(repo: Path, data_dir: Path) -> str:
    """*repo* relative to the data directory, or `""` when it is somewhere else on disk.

    What separates a fixture the repo tracks — where an edit to the tree and a stale zip
    are the same event, and the freshness guard has something to recompute — from a seed
    captured out of a live session's workdir, which has no in-tree source and so cannot
    drift from one.
    """
    try:
        return repo.resolve().relative_to(data_dir.resolve()).as_posix()
    except ValueError:
        return ""


def _carried_over(pointer_path: Path, *, url: str, note: str) -> tuple[str, str]:
    """Inherit `url` and `note` from the pointer being replaced, unless this call names them.

    A re-capture re-measures the tree; it does not re-decide where the zip is served from or
    what the seed is. Those two fields are the only ones a person typed rather than a hash
    computed, so a `--force` that silently blanks them costs a fixture its fetch story and
    its one line of prose — and the usual reason to re-capture is that a file in the tree
    moved, which is exactly when nobody is thinking about the pointer's prose.

    Empty means inherit, so clearing one is an edit to the TOML rather than a flag. That is
    the right way round: dropping a url by omission is the failure this exists to stop, and
    a re-capture is not where you would deliberately go to do it.
    """
    if not pointer_path.exists() or (url and note):
        return url, note
    previous = Pointer.load(pointer_path)
    return url or previous.url, note or previous.note


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
    url, note = _carried_over(pointer_path, url=url, note=note)

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
    )
    pointer.write(pointer_path)
    return Captured(pointer=pointer, zip_path=zip_path, pointer_path=pointer_path)


def fetch(pointer: Pointer, *, store: Path, force: bool = False) -> Path:
    """Put the pointer's zip in the store, downloading it only if it is not already right.

    The first (and so far only) backend is an unauthenticated HTTPS GET: a public bucket
    object or a share link. Anything else — an authenticated client, a credential — is
    deferred until a private fixture actually needs one, and would be a new branch here
    rather than a change to the pointer format.
    """
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
    # Verified before it is allowed into the store, so a truncated or swapped download
    # never becomes the thing the next run treats as the fixture.
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
    """Extract the seed into *dest*, returning the repo tree inside it.

    *dest* is emptied of any previous copy of this repo first: an unpack that merges into
    a stale tree is the subtlest way a benchmark run starts from a state nobody captured.
    """
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
    """Re-run `farrier install` so the machine-local layer points at *this* path.

    Best-effort by design. A seed of a repo farrier was never run in has nothing to
    re-point, and a machine without farrier on it can still unpack a seed to look at it;
    neither is a reason to fail the unpack. What is *not* best-effort is saying so — a
    silently un-reinstalled tree is a run whose agent reads skills generated for another
    machine's paths.
    """
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
