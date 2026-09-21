"""`ostler qa clean` — remove the scratch roots the old sibling layout left behind."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ostler.qa.outcome import QaOutcome

__all__ = ["LEGACY_PREFIX", "PROTECTED", "cmd_clean", "legacy_scratch_roots"]

LEGACY_PREFIX = "qa-"

PROTECTED = frozenset({"qa-inputs"})

_SKIP = frozenset({".git", ".venv", "node_modules", "__pycache__", ".mypy_cache"})


def legacy_scratch_roots(root: Path) -> list[Path]:
    """Every legacy scratch directory at or under ``root``, outermost first."""
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
    """``(files, bytes)`` under ``path``."""
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
    """List the legacy scratch roots under ``root``; delete them when ``apply``."""
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
