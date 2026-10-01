#!/usr/bin/env python3
"""Refuse a commit that carries QA evidence, or anything else oversized, into history."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from fnmatch import fnmatch
from pathlib import Path

CONFIG = ".agent-checks.toml"
TABLE = "check-staged-files"

MAX_BYTES = 1_500_000

QA_DIRNAME = "qa"

ARTIFACT_DIRS = frozenset({"steps", "asserts", "traces", "videos", "screenshots"})
LEDGER_FILES = frozenset({"qa-run.ndjson", "run-manifest.json", "qa-session.json"})


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def declarations(root: Path) -> dict:
    config = root / CONFIG
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})


def staged_paths(root: Path) -> list[str]:
    """Repo-relative POSIX paths the commit would add or change."""
    out = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [entry for entry in out.split("\0") if entry]


def staged_size(root: Path, path: str) -> int:
    """Size of the blob *in the index*, which is what the commit would carry."""
    out = _git(root, "cat-file", "-s", f":{path}")
    return int(out.strip())


def is_qa_evidence(root: Path, path: str) -> bool:
    """Whether a staged path sits in a QA scratch directory rather than in source."""
    parts = path.split("/")
    for index, part in enumerate(parts):
        if part != QA_DIRNAME:
            continue
        below = parts[index + 1 :]
        if ARTIFACT_DIRS.intersection(below[:-1]):
            return True
        if below and below[-1] in LEDGER_FILES:
            return True
        qa_dir = root.joinpath(*parts[: index + 1])
        for name in LEDGER_FILES:
            if next(qa_dir.rglob(name), None) is not None:
                return True
    return False


def check_staged_files(root: Path) -> list[str]:
    declared = declarations(root)
    allow: list[str] = list(declared.get("allow", []))
    limit = int(declared.get("max-bytes", MAX_BYTES))

    problems: list[str] = []
    for path in staged_paths(root):
        if any(fnmatch(path, pattern) for pattern in allow):
            continue
        size = staged_size(root, path)
        if size > limit:
            problems.append(
                f"{path}: {size / 1_000_000:.1f} MB staged, "
                f"over the {limit / 1_000_000:.1f} MB limit"
            )
        if is_qa_evidence(root, path):
            problems.append(
                f"{path}: QA evidence — a run wrote it, so nothing should commit it"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repo to check (default: cwd)")
    args = parser.parse_args()

    root = args.root.resolve()
    problems = check_staged_files(root)
    if not problems:
        return 0

    print("\nFAIL check_staged_files:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nA repository is append-only in practice: once these blobs are pushed, every\n"
        "clone downloads them forever and only a history rewrite takes them back.\n"
        "\n"
        "  unstage it            git restore --staged <path>\n"
        "  drop the evidence     ostler qa clean --spec <spec-dir> --yes\n"
        "  it belongs in git     add a glob to [check-staged-files] allow "
        f"in {CONFIG}\n"
        "\n"
        "`--no-verify` also gets the commit in. It is the one route that leaves no trace\n"
        "for a reviewer, which is why the allowlist is tracked.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
