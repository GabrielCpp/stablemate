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

The git pre-commit hook (.githooks/pre-commit) covers (1) for *staged* changes. This is
the whole-tree sweep it cannot be: it catches anything committed before the hook existed,
committed with --no-verify, or already in history.

The names are deliberately absent from this file — a denylist publishes the words it
bans as surely as a leak does. ``scripts/private_names.py`` reads them from an untracked
source. With none configured (the public-contributor case), check (1) is skipped.

Run:
    uv run python scripts/check_public.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "base-library"
RESOLVER = REPO / "scripts" / "private_names.py"

# Every text format the repo ships: prose (md), graphs/configs (yml/toml/json), and
# scripts (py/sh). A leak hides just as well in a script comment as in a heading.
TEXT_SUFFIXES = (".md", ".yml", ".yaml", ".py", ".sh", ".json", ".toml", ".txt")


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
        if path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        scanned += 1
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    if not offenders:
        print(f"ok: no private project names in {scanned} tracked text files")
    return offenders


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
        if skill.layer.name != install.BASE_LAYER_NAME:
            problems.append(f"skill {skill.id!r} did not resolve from the base layer")
        if not skill.id.startswith("stablemate/"):
            problems.append(
                f"skill {skill.id!r} is in the base but is not a stablemate/* skill — "
                "the base carries the toolchain's own skills; everything else is "
                "overlay content"
            )

    workflows_dir = BASE / "workflows"
    names = (
        sorted(p.name for p in workflows_dir.iterdir() if (p / "workflow.yaml").is_file())
        if workflows_dir.is_dir()
        else []
    )
    if not names:
        problems.append(f"the base ships no workflows (looked in {workflows_dir})")
    for name in names:
        if install.find_in_layers("workflows", name) is None:
            problems.append(f"workflow {name!r} is in the base but does not resolve")

    if not problems:
        print(
            f"ok: {len(skills)} base skills and {len(names)} base workflows resolve "
            "with no overlay configured"
        )
    return problems


def main() -> int:
    failures = 0
    for check in (check_no_private_names, check_base_stands_alone):
        problems = check()
        if problems:
            failures += 1
            print(f"\nFAIL {check.__name__}:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
    if failures:
        return 1
    print("\nthe public/private split holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
