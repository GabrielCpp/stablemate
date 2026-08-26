#!/usr/bin/env python3
"""Guard the public/private split. Run before publishing; wired into `make test`.

stablemate ships publicly. Two things have to stay true, and neither fails loudly on
its own — both break silently on the maintainer's machine, where the private overlay is
configured and shadows everything:

1. **No private overlay name appears anywhere in the repo.** Not in prose, not in a
   fixture, not in a code comment. Repo-wide, because that is the actual rule — this
   check used to scan only ``base-library/`` and could not see a name sitting in a
   workhorse test or a root doc.

2. **The base library stands alone.** No base skill, pack or workflow may depend on the
   overlay. Break this and everything still works here; it fails only for a public user
   who has no overlay at all.

3. **The guards are actually wired.** ``core.hooksPath`` is unset in a fresh clone, so
   the hooks are off until someone runs ``make hooks`` — which is farrier's job, from
   the ``hooks:`` block in ``agents.yml`` — and nothing announces it.

The git pre-commit hook (.githooks/pre-commit) runs check (1) from here, via
``--names-only`` — the same sweep over the same files, so what blocks a commit and what
fails ``make test`` cannot drift apart. That flag skips (2) and (3) because they need the
workspace venv and a farrier import, which a hook has no business requiring.

CI cannot stand in for any of this. The names are untracked by construction, so a runner
has none configured and check (1) skips there — which makes this machine the only place
the guard exists, and an uninstalled hook a real failure rather than a note.

The names are deliberately absent from this file — a denylist publishes the words it
bans as surely as a leak does. ``scripts/private_names.py`` reads them from an untracked
source. With none configured (the public-contributor case), checks (1) and (3) are
skipped.

Check (1) has two halves: the tracked tree, and **reachable git history**. The history
half exists because of a real leak the tree sweep is structurally blind to: a private
name was committed, removed a week later, and every clone kept shipping it in history
while the sweep reported clean. The history check walks every ref — commit messages,
the paths objects live at, and each unique blob's content once — so removal without a
rewrite can never read as clean again.

Run:
    uv run python scripts/check_public.py                 # everything
    python3 scripts/check_public.py --names-only          # what the hook runs (tree only)
    python3 scripts/check_public.py --history             # history alone; stdlib-only,
                                                          # runs in a bare fresh clone
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "base-library"

# The skill families the public base library carries. Two kinds, and the split is the
# same one the two packs make: a directory per tool in this toolchain (`farrier/`,
# `ostler/`, `groom/`, `workhorse/` — the `stablemate` pack), and the generic
# cross-language contracts (`architecture/`, `testing/`, `ui/`, plus the cross-cutting
# singles that own no family — the `general` pack). Per-stack mechanics (`stacks/`) and
# house rules remain overlay content.
#
# It is an allowlist rather than a shape rule on purpose: admitting a new family to the
# public base is a decision somebody makes, not a side effect of creating a directory.
BASE_SKILL_FAMILIES = {
    "farrier",
    "ostler",
    "groom",
    "workhorse",
    "architecture",
    "testing",
    "ui",
    "code-review",
    "diagnosing-bugs",
    "vertical-slicing",
}
RESOLVER = REPO / "scripts" / "private_names.py"
#: What `pre-commit install` writes, and the marker it leaves in what it writes. The
#: scripts themselves still live in `.githooks/` and are still runnable by hand; what
#: moved is only which of them git runs, and on whose say-so.
HOOK_NAME = "hooks/pre-commit"

#: What the wired hook has to contain to be this repo's. Two markers, because the hook
#: has two halves and losing either one is silent: the private-name sweep this script
#: owns, and the fenced line farrier splices in after it. Substrings of the *script*,
#: not of the manager that used to sit in front of it — a marker that named the runner
#: went stale the moment the runner did.
HOOK_MARKERS = ("scripts/check_public.py", "make farrier-run-hook")

# Git's own heuristic: a NUL byte in the first 8 kB means binary. This replaced a
# suffix allowlist (.md/.yml/.py/.sh/.json/.toml/.txt) that had a hole exactly where a
# leak had been living — `.html` was not on it, so two groom mockups carried a private
# name through 95 commits without the sweep ever opening them. And neither were `.js`,
# `.css`, `Makefile`, `Dockerfile` or the hooks themselves. An allowlist has to
# anticipate every extension the repo will ever hold; this only has to tell text from
# bytes, and it is wrong in the safe direction — a misread binary is noise in a report,
# a skipped text file is a leak nobody sees.
BINARY_SNIFF_BYTES = 8000


def _text_of(path: Path) -> str | None:
    """The file's text, or None if it reads as binary or cannot be opened."""
    try:
        with path.open("rb") as handle:
            head = handle.read(BINARY_SNIFF_BYTES)
            if b"\0" in head:
                return None
            return (head + handle.read()).decode("utf-8", errors="replace")
    except OSError:
        return None


def _private_names_module():
    spec = importlib.util.spec_from_file_location("private_names", RESOLVER)
    assert spec and spec.loader, f"cannot load the name resolver at {RESOLVER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tracked_files() -> list[Path]:
    """Files git tracks. The scan set, and deliberately not ``rglob``.

    What ships is what is tracked. Walking the tree instead would sweep in every
    untracked thing that happens to be lying around — a rendered `.agents/` tree, a
    playwright artifact dir, a venv — and report the maintainer's own local output as a
    leak. It also means no hand-maintained exclusion list to drift.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p]


def check_no_private_names() -> list[str]:
    """No private overlay name in any tracked path or file. Repo-wide."""
    private_names = _private_names_module()
    pattern = private_names.pattern(private_names.load())
    if pattern is None:
        print(
            f"skip: no private names configured (${private_names.ENV_VAR} or "
            f"$GIT_DIR/{private_names.GIT_FILE}) — nothing to check against"
        )
        return []

    offenders: list[str] = []
    scanned = 0
    for path in _tracked_files():
        rel = path.relative_to(REPO).as_posix()
        # The path itself counts: a private name in a directory or filename ships too.
        if pattern.search(rel):
            offenders.append(f"{rel}: (in the path)")
            continue
        text = _text_of(path) if path.is_file() else None
        if text is None:
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    if not offenders:
        print(f"ok: no private project names in {scanned} tracked text files")
    return offenders


def check_no_private_names_in_history() -> list[str]:
    """No private name anywhere reachable from any ref — messages, paths, blobs.

    The tree sweep above sees only the checkout. A name committed and later removed
    passes it while shipping in every clone's history, which is exactly how the one
    real incident survived: added in one commit, removed two hundred commits ago,
    invisible to every guard that reads the tree. This check walks ``--all`` refs
    (branches, tags, the stash) so that state can only be reached by an actual
    history rewrite.

    A blob is scanned once no matter how many commits carry it, so the cost is one
    object walk plus one ``cat-file`` stream over unique blobs — seconds, not the
    per-commit tree scan ``git grep $(git rev-list --all)`` would be.
    """
    private_names = _private_names_module()
    pattern = private_names.pattern(private_names.load())
    if pattern is None:
        # The tree check already printed the skip note; stay quiet here.
        return []

    offenders: list[str] = []

    # Commit messages. -z NUL-separates records of "<sha>\n<subject+body>".
    log = subprocess.run(
        ["git", "-C", str(REPO), "log", "--all", "-z", "--format=%H%n%B"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for record in log.split("\0"):
        if not record:
            continue
        sha, _, message = record.partition("\n")
        if pattern.search(message):
            offenders.append(f"commit {sha[:12]}: (in the commit message)")

    # Every object reachable from any ref, with the path it lives at. Commits have
    # no path; trees and blobs do. Paths count the same way they do in the tree
    # sweep — a private name in a historical filename ships too.
    listing = subprocess.run(
        ["git", "-C", str(REPO), "rev-list", "--all", "--objects"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    candidates: dict[str, str] = {}  # sha -> path, deduplicated
    flagged_paths: set[str] = set()
    for line in listing.splitlines():
        sha, _, path = line.partition(" ")
        if not path:
            continue  # a commit
        if pattern.search(path) and path not in flagged_paths:
            flagged_paths.add(path)
            offenders.append(f"history path {path!r}: (in the path)")
        candidates.setdefault(sha, path)

    # One cat-file stream over the candidates; only blobs have content to scan.
    # Streamed, not captured: all historical versions of every file pass through.
    with subprocess.Popen(
        ["git", "-C", str(REPO), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as proc:
        stdin, stdout = proc.stdin, proc.stdout
        assert stdin is not None and stdout is not None

        def _feed() -> None:
            for sha in candidates:
                stdin.write(sha.encode() + b"\n")
            stdin.close()

        feeder = threading.Thread(target=_feed)
        feeder.start()
        scanned = 0
        while True:
            header = stdout.readline()
            if not header:
                break
            sha, kind, size_text = header.decode().split()
            size = int(size_text)
            body = stdout.read(size)
            stdout.read(1)  # the trailing newline
            if kind != "blob":
                continue
            if b"\0" in body[:BINARY_SNIFF_BYTES]:
                continue
            scanned += 1
            text = body.decode("utf-8", errors="replace")
            if pattern.search(text):
                where = subprocess.run(
                    [
                        "git", "-C", str(REPO), "log", "--all", "-1",
                        f"--find-object={sha}", "--format=%h",
                    ],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                offenders.append(
                    f"blob {sha[:12]} at {candidates[sha]!r} (e.g. commit {where}): "
                    "(in historical content)"
                )
        feeder.join()

    if not offenders:
        print(f"ok: no private project names in {scanned} historical blobs across all refs")
    else:
        offenders.append(
            "history offenders need a rewrite (git filter-repo --replace-text), "
            "not a removal commit — removal is what made this class invisible"
        )
    return offenders


def _installed_hook() -> Path:
    """The pre-commit hook git would run here, asked of git rather than assembled.

    ``git rev-parse --git-path`` answers for the repository it is standing in, which is
    the only way to get this right in the two layouts that are not a plain clone: a
    linked worktree (``.git`` is a file, and hooks live in the common directory it points
    at) and a ``core.hooksPath`` that redirects them somewhere else entirely. The literal
    fallback is for a tree git will not answer for at all, where "absent" is the honest
    reading anyway.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--git-path", HOOK_NAME],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return REPO / ".git" / HOOK_NAME
    path = Path(out)
    return path if path.is_absolute() else REPO / path


def check_hooks_installed() -> list[str]:
    """The guard has to be plugged in, and git does not plug it in for you.

    A fresh clone runs no hooks at all — and stays that way through a re-clone, a
    ``git init``, or a worktree someone made last week — so every guard is silently off
    until ``make hooks`` runs. Nothing surfaces that state: commits simply keep working.

    This is the check that would have caught the real incident it was written for. A
    private name reached a test fixture and survived several commits, not because the
    hook missed it but because the hook was never running.

    The probe is the installed file rather than ``core.hooksPath``, because the config
    being set says only that git will look in ``.githooks/`` — not that the two guards
    are in the file it finds there. ``farrier hooks`` sets the config and splices its
    own fenced region in one step, so a repo can be half-wired by nothing worse than an
    interrupted install.

    *Which* file that is, git decides — see :func:`_installed_hook`. Reading it off
    ``<repo>/.git/hooks/`` fails a linked worktree, where ``.git`` is a file and the hook
    git actually runs lives in the common directory. That is not a hypothetical: this
    check reported every guard missing from a worktree whose commits it had just been
    seen blocking.
    """
    private_names = _private_names_module()
    if not private_names.load():
        # A public contributor has no list to enforce, so a hook that would be a no-op
        # anyway is nothing to fail over.
        return []
    installed = _installed_hook()
    text = installed.read_text(encoding="utf-8", errors="replace") if installed.is_file() else ""
    missing = [marker for marker in HOOK_MARKERS if marker not in text]
    if missing:
        detail = "absent" if not text else "missing " + ", ".join(repr(m) for m in missing)
        return [
            f"{installed} is {detail} — the private-name, commit-message and "
            "generated-file guards are not running on this clone. Fix: make hooks"
        ]
    print(f"ok: git hooks resolve through {installed}")
    return []


def _isolate_from_the_overlay(install, config, discovery, base_cache) -> list[str]:
    """Resolve as a public user would: base only, no overlay in env or home config."""
    os.environ.pop("FARRIER_LIBRARY_DIR", None)
    # Point the shared config at an empty temp file. Setting $STABLEMATE_CONFIG also
    # suppresses the legacy per-tool fallback, so this cannot read the maintainer's
    # actual overlay config.
    os.environ[config.CONFIG_PATH_ENV] = str(Path(tempfile.mkdtemp()) / "config.toml")
    # Name THIS base explicitly. With the config blanked there is no other route to one,
    # and resolution would otherwise fall through to the cache and fetch 16M from GitHub
    # mid-check — which would also check the wrong library (main's, not this tree's).
    os.environ[discovery.BASE_DIR_ENV] = str(BASE)
    os.environ[base_cache.FETCH_ENV] = "0"
    install.set_layers(None)
    if [layer.name for layer in install.LAYERS] != [install.BASE_LAYER_NAME]:
        return ["the base library is not the only layer — the check would mean nothing"]
    return []


def check_base_stands_alone() -> list[str]:
    """Nothing in the base may depend on the private overlay."""
    from farrier import install
    from stablemate_core import base_cache, config, discovery

    if not install.is_library_dir(BASE):
        return [f"{BASE} is not a usable library root"]

    problems = _isolate_from_the_overlay(install, config, discovery, base_cache)
    if problems:
        return problems

    skills = install.load_layered_sources("skill", "library", "skills")
    if not skills:
        return ["the base library resolves no skills at all"]
    for skill in skills:
        if skill.layer is None or skill.layer.name != install.BASE_LAYER_NAME:
            problems.append(f"skill {skill.id!r} did not resolve from the base layer")
        family = skill.id.split("/", 1)[0]
        if family not in BASE_SKILL_FAMILIES:
            problems.append(
                f"skill {skill.id!r} is in the base but not in a base family "
                f"({', '.join(sorted(BASE_SKILL_FAMILIES))}) — the base carries the "
                "toolchain's own skills plus the generic cross-language contracts; "
                "stack mechanics and house rules are overlay content"
            )

    # There is no workflow clause. The base shipped four workflow directories until the
    # YAML front-end was retired; a workflow is now an installed Python distribution reached
    # through its own console script, which is a distribution's business and not
    # the library's. What the base still carries is markdown, and the question this check
    # asks of it is the one above: does it resolve without the overlay.
    if not problems:
        print(f"ok: {len(skills)} base skills resolve with no overlay configured")
    return problems


def main(argv: list[str]) -> int:
    # --names-only is the pre-commit hook's entry point: the tree sweep alone, which is
    # pure stdlib and needs no venv — the history walk would put seconds on the critical
    # path of every commit for a state a commit cannot even create. --history is the
    # standalone history walk, also stdlib-only, so it can verify a bare fresh clone
    # (post-rewrite, pre-push) where no venv exists. The default run does everything.
    unknown = [a for a in argv if a not in ("--names-only", "--history")]
    if unknown:
        print(
            f"usage: check_public.py [--names-only | --history]  (got {unknown})",
            file=sys.stderr,
        )
        return 2
    if "--names-only" in argv:
        checks = (check_no_private_names,)
    elif "--history" in argv:
        checks = (check_no_private_names_in_history,)
    else:
        checks = (
            check_no_private_names,
            check_no_private_names_in_history,
            check_hooks_installed,
            check_base_stands_alone,
        )

    failures = 0
    for check in checks:
        problems = check()
        if problems:
            failures += 1
            print(f"\nFAIL {check.__name__}:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
    if failures:
        if "--names-only" in argv:
            print(
                "\nstablemate is public: replace these with neutral placeholders\n"
                "(acme, globex, api-service, web-app, mobile-app, example.com).\n"
                "To commit anyway: git commit --no-verify",
                file=sys.stderr,
            )
        return 1
    if "--names-only" not in argv:
        print("\nthe public/private split holds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
