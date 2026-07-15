#!/usr/bin/env python3
"""Pre-commit sentinel gate — reject fabricated placeholder IDs and unreconciled stubs.

Greps the lines added by this story branch (relative to the repo's base branch) for
patterns that indicate shipped code contains un-reconciled placeholders:

  - All-zeros UUID constants  (e.g. "00000000-0000-0000-0000-000000000000")
  - Hex strings that are all-zeros (e.g. "000000000000000000000000000000000000")
  - "falls back until <X> exists" / "falls back.*TODO" in non-comment shipping paths
  - "TODO until", "placeholder until", "stub until" in shipped (non-test) source

Operates on added lines from `git diff <base>..HEAD` in Go/TypeScript/TSX source,
excluding test files (*_test.go, *.spec.ts, *.spec.tsx, *.test.ts, *_test.ts) and
pure-comment lines. Outputs in the same `qa_result` format as verify_qa_evidence.py
so it can slot into the same workflow gate infrastructure.

Git access goes through workhorse.scriptutil (GitPython), so this runs under the
workhorse venv like the other script nodes.

Usage: check-sentinel-ids.py [story_slug]
Outputs JSON on stdout captured under the node's `qa_result` key:
  {"qa_result": {"status": "passed"|"failed", "notes": "..."}}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from workhorse.scriptutil import diff_text, merge_base

# Patterns that flag an added line as a sentinel (applied to the content after the '+' prefix).
# Each entry: (pattern, description)
SENTINEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r'["\']0{8}-0{4}-0{4}-0{4}-0{12}["\']', re.IGNORECASE),
        "all-zeros UUID constant",
    ),
    (
        re.compile(r'["\']0{32,}["\']', re.IGNORECASE),
        "all-zeros hex/UUID constant",
    ),
    (
        re.compile(r"falls\s+back\s+(until|when|if)\s+\S+\s+exists", re.IGNORECASE),
        "'falls back until X exists' stub",
    ),
    (
        re.compile(r"\bTODO\s+until\b", re.IGNORECASE),
        "'TODO until' unreconciled placeholder",
    ),
    (
        re.compile(r"\bplaceholder\s+until\b", re.IGNORECASE),
        "'placeholder until' stub",
    ),
    (
        re.compile(r"\bstub\s+until\b", re.IGNORECASE),
        "'stub until' placeholder",
    ),
]

# Source extensions to scan (skip everything else).
SOURCE_EXTENSIONS = {".go", ".ts", ".tsx", ".js", ".jsx"}

# Filename substrings that mark a file as a test file (skip).
TEST_MARKERS = (
    "_test.go",
    ".spec.ts",
    ".spec.tsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".test.js",
)


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def emit(status: str, notes: str) -> None:
    print(json.dumps({"qa_result": {"status": status, "notes": notes}}))
    sys.exit(0)


def find_base_ref(root: Path) -> str:
    """Return the git ref to diff against (the merge base with the default branch)."""
    for branch in ("origin/master", "origin/main", "master", "main"):
        base = merge_base(root, "HEAD", branch)
        if base:
            return base
    # Fallback: diff against the previous commit.
    return "HEAD~1"


def get_added_lines(root: Path, base_ref: str) -> list[tuple[str, int, str]]:
    """Return (filename, lineno, content) for every + line in the diff.

    Skips diff headers (--- / +++ / @@ lines) and binary-file markers.
    """
    diff = diff_text(root, "--unified=0", base_ref, "HEAD", "--")
    if not diff:
        return []

    lines = diff.splitlines()
    current_file: str = ""
    current_lineno: int = 0
    added: list[tuple[str, int, str]] = []

    for line in lines:
        if line.startswith("diff --git "):
            current_file = ""
            current_lineno = 0
        elif line.startswith("+++ b/"):
            current_file = line[6:]  # strip "+++ b/"
            current_lineno = 0
        elif line.startswith("@@ "):
            # @@ -old +new,count @@ …  — parse the new-file start line
            m = re.search(r"\+(\d+)", line)
            current_lineno = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            current_lineno += 1
            added.append((current_file, current_lineno, line[1:]))
        elif not line.startswith("-"):
            current_lineno += 1

    return added


def is_test_file(filename: str) -> bool:
    lower = filename.lower()
    return any(marker in lower for marker in TEST_MARKERS)


def has_source_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in SOURCE_EXTENSIONS


def is_comment_line(content: str, filename: str) -> bool:
    """Heuristic: skip lines that are pure comments."""
    stripped = content.lstrip()
    if filename.endswith(".go"):
        return stripped.startswith("//")
    if filename.endswith((".ts", ".tsx", ".js", ".jsx")):
        return stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*")
    return False


def main() -> None:
    story_slug = sys.argv[1] if len(sys.argv) > 1 else "(unknown)"
    root = find_repo_root()

    try:
        base_ref = find_base_ref(root)
    except Exception:
        emit("passed", "Sentinel gate: could not determine base ref — skipped (no git history).")

    try:
        added_lines = get_added_lines(root, base_ref)
    except Exception as exc:
        emit("passed", f"Sentinel gate: git diff failed ({exc}) — skipped.")

    if not added_lines:
        emit("passed", f"Sentinel gate: no added lines in diff ({base_ref}..HEAD) — nothing to check.")

    hits: list[str] = []
    for filename, lineno, content in added_lines:
        if not has_source_extension(filename):
            continue
        if is_test_file(filename):
            continue
        if is_comment_line(content, filename):
            continue
        for pattern, description in SENTINEL_PATTERNS:
            if pattern.search(content):
                hits.append(f"{filename}:{lineno}: {description} — {content.strip()[:120]}")
                break  # one hit per line is enough

    if hits:
        emit(
            "failed",
            "Sentinel gate: shipped source contains unreconciled placeholder(s). Remove before "
            "committing — fabricated IDs and 'until X exists' stubs are never valid in the "
            "shipped path:\n- " + "\n- ".join(hits),
        )

    n = len(added_lines)
    emit(
        "passed",
        f"Sentinel gate: {n} added lines scanned in story {story_slug!r} — no fabricated "
        f"placeholder IDs or unreconciled stubs found.",
    )


if __name__ == "__main__":
    main()
