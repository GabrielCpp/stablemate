"""`ostler qa clean` — remove the scratch roots the old sibling layout left behind.

Before dry runs nested inside `qa/`, every rehearsal wrote a sibling directory of the
spec: the sanctioned `qa-dry-run/`, plus whatever an agent or a hand-driven session
invented — `qa-fix-*`, `qa-operator-*`, `qa-sandbox`. None of them matched the `qa`
directory a repo ignores, so they were committed: in the case that motivated the nested
layout, 2,167 tracked files and 297 MB of traces and video.

The new layout stops it happening again; it does not remove what already exists, and
`clear_qa_evidence` cannot either. A sweep that inferred "scratch" from a `qa-` prefix
inside the run path would be one bad guess away from deleting `qa-inputs/` — tracked plan
fixtures, resolved as `spec_dir / path`, indistinguishable from scratch by name alone.
Hence a separate command that lists first and deletes only when told to.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ostler.qa.outcome import QaOutcome

__all__ = ["LEGACY_PREFIX", "PROTECTED", "cmd_clean", "legacy_scratch_roots"]

#: What the old layout's directories were called. `qa/` itself is not matched: it is the
#: ledger, and now the parent of all scratch.
LEGACY_PREFIX = "qa-"

#: Directories that share the prefix and are not scratch. `qa-inputs/` holds a plan's
#: `inputs:` fixtures — tracked on purpose, and the run reads them.
PROTECTED = frozenset({"qa-inputs"})

#: Never walked. Cheap insurance against a `--spec` pointed at a repo root: nothing here
#: is a spec directory, and some of it is enormous.
_SKIP = frozenset({".git", ".venv", "node_modules", "__pycache__", ".mypy_cache"})


def legacy_scratch_roots(root: Path) -> list[Path]:
    """Every legacy scratch directory at or under ``root``, outermost first.

    A matched directory is not descended into: its contents are going with it, and a
    `qa-dry-run/qa-dry-run/` from a doubled path should be reported as one root, not two.
    """
    if not root.is_dir():
        return []
    found: list[Path] = []
    if _is_legacy(root):
        return [root]
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.is_symlink() or child.name in _SKIP:
            continue
        found.extend(legacy_scratch_roots(child))
    return found


def _is_legacy(path: Path) -> bool:
    return path.name.startswith(LEGACY_PREFIX) and path.name not in PROTECTED


def _weigh(path: Path) -> tuple[int, int]:
    """``(files, bytes)`` under ``path``. A broken symlink or a file that vanished mid-walk
    is counted as nothing rather than raising — this is a size to print, not an audit."""
    files = 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                files += 1
                total += item.stat().st_size
        except OSError:
            continue
    return files, total


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def cmd_clean(root: Path, *, apply: bool = False) -> QaOutcome:
    """List the legacy scratch roots under ``root``; delete them when ``apply``.

    Listing is the default because deleting is not reversible and the caller is often an
    agent. ``ok`` is true either way — finding nothing and removing what was found are both
    success; only a failed removal is not.
    """
    roots = legacy_scratch_roots(root)
    if not roots:
        return QaOutcome(
            ok=True,
            message=f"No legacy QA scratch directories under {root}.",
            data={"roots": [], "removed": False},
        )

    rows: list[dict[str, Any]] = []
    lines: list[str] = []
    total_files = 0
    total_bytes = 0
    for path in roots:
        files, size = _weigh(path)
        total_files += files
        total_bytes += size
        rows.append({"path": str(path), "files": files, "bytes": size})
        lines.append(f"  {path}  ({files} file(s), {_human(size)})")

    what = (
        f"{len(roots)} legacy QA scratch director{'y' if len(roots) == 1 else 'ies'} "
        f"under {root} — {total_files} file(s), {_human(total_bytes)}"
    )
    header = f"Found {what}:"
    if not apply:
        return QaOutcome(
            ok=True,
            message="\n".join(
                [header, *lines, "", "Nothing was deleted. Re-run with --yes to remove them."]
            ),
            data={"roots": rows, "removed": False},
        )

    errors: list[str] = []
    for path in roots:
        try:
            shutil.rmtree(path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        return QaOutcome(
            ok=False,
            message="Some directories could not be removed:\n"
            + "\n".join(f"  {item}" for item in errors),
            data={"roots": rows, "removed": True, "errors": errors},
        )
    return QaOutcome(
        ok=True,
        message="\n".join([f"Removed {what}:", *lines]),
        data={"roots": rows, "removed": True},
    )
