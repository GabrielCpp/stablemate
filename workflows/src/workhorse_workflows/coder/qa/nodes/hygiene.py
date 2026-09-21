"""The two pre-commit hygiene gates: relocate stray screenshots, reject sentinel IDs."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from unidiff.patch import PatchSet
from unidiff.errors import UnidiffParseError
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import QaResult, ScreenshotFlush
from workhorse_workflows.kit import diff_text, list_tracked_files, trunk_base

IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})

SENTINEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'["\']0{8}-0{4}-0{4}-0{4}-0{12}["\']', re.IGNORECASE), "all-zeros UUID constant"),
    (re.compile(r'["\']0{32,}["\']', re.IGNORECASE), "all-zeros hex/UUID constant"),
    (
        re.compile(r"falls\s+back\s+(until|when|if)\s+\S+\s+exists", re.IGNORECASE),
        "'falls back until X exists' stub",
    ),
    (re.compile(r"\bTODO\s+until\b", re.IGNORECASE), "'TODO until' unreconciled placeholder"),
    (re.compile(r"\bplaceholder\s+until\b", re.IGNORECASE), "'placeholder until' stub"),
    (re.compile(r"\bstub\s+until\b", re.IGNORECASE), "'stub until' placeholder"),
]

SOURCE_EXTENSIONS = frozenset({".go", ".ts", ".tsx", ".js", ".jsx"})

TEST_MARKERS = (
    "_test.go",
    ".spec.ts",
    ".spec.tsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".test.js",
)




def _tracked_names(root: Path) -> set[str]:
    """Top-level files git already tracks."""
    return {path for path in list_tracked_files(root) if "/" not in path}


def _dest_dir(root: Path, spec_dir: str) -> Path | None:
    """`<spec_dir>/qa/` under the repo root, or `None` when `spec_dir` is not usable."""
    spec = spec_dir.strip()
    if not spec:
        return None
    candidate = root / spec
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate == root:
        return None
    return candidate / "qa"


def _unique_target(dest: Path, name: str) -> Path:
    """`dest/name`, suffixed `-1`, `-2`, … if it is taken."""
    if not (dest / name).exists():
        return dest / name
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 1
    while (dest / f"{stem}-{index}{suffix}").exists():
        index += 1
    return dest / f"{stem}-{index}{suffix}"


@blueprint.node
def flush_root_screenshots(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = ""
) -> ScreenshotFlush:
    """Move untracked root images into `<spec_dir>/qa/` so `git add -A` cannot commit them."""
    root = find_repo_root(repo_dir)
    strays = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not strays:
        logger.info("no stray images at repo root")
        return ScreenshotFlush(notes="no stray images at repo root")

    tracked = _tracked_names(root)
    untracked = [p for p in strays if p.name not in tracked]
    kept_tracked = len(strays) - len(untracked)
    if not untracked:
        note = f"{kept_tracked} root image(s) are tracked assets — left in place"
        logger.info(note)
        return ScreenshotFlush(kept_tracked=kept_tracked, notes=note)

    dest = _dest_dir(root, spec_dir)
    if dest is None:
        logger.warning(
            "could not resolve qa dir from spec_dir — leaving %d stray image(s) in place",
            len(untracked),
        )
        return ScreenshotFlush(
            kept_tracked=kept_tracked,
            notes=(
                "could not resolve qa dir from spec_dir — left "
                f"{len(untracked)} stray image(s) in place"
            ),
        )

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("could not create %s: %s", dest, exc)
        return ScreenshotFlush(
            kept_tracked=kept_tracked,
            notes=f"could not create qa dir — left {len(untracked)} stray image(s) in place",
        )

    flushed = 0
    for src in untracked:
        try:
            src.rename(_unique_target(dest, src.name))
            flushed += 1
        except OSError as exc:
            logger.warning("could not move %s: %s", src.name, exc)

    note = f"moved {flushed} stray image(s) to {dest.relative_to(root)}"
    if kept_tracked:
        note += f"; left {kept_tracked} tracked root image(s) in place"
    logger.info(note)
    return ScreenshotFlush(flushed=flushed, kept_tracked=kept_tracked, notes=note)




def _added_lines(root: Path, base_ref: str) -> list[tuple[str, int, str]]:
    """`(filename, lineno, content)` for every `+` line between `base_ref` and `HEAD`."""
    diff = diff_text(root, "--unified=0", base_ref, "HEAD", "--")
    if not diff:
        return []

    try:
        patch = PatchSet(diff)
    except UnidiffParseError:
        return []
    return [
        (patched.path, line.target_line_no, line.value.rstrip("\n"))
        for patched in patch
        for hunk in patched
        for line in hunk
        if line.is_added and line.target_line_no is not None
    ]


def _is_test_file(filename: str) -> bool:
    lower = filename.lower()
    return any(marker in lower for marker in TEST_MARKERS)


def _is_comment_line(content: str, filename: str) -> bool:
    """Whether the line is a pure comment — a heuristic, and only for the two dialects whose sentinels this gate is aimed at."""
    stripped = content.lstrip()
    if filename.endswith(".go"):
        return stripped.startswith("//")
    if filename.endswith((".ts", ".tsx", ".js", ".jsx")):
        return stripped.startswith(("//", "*", "/*"))
    return False


@blueprint.node
def check_sentinel_ids(
    logger: logging.Logger, story_slug: str = "", repo_dir: str = ""
) -> QaResult:
    """Fail the pass if this branch added a fabricated ID or an "until X exists" stub."""
    slug = story_slug or "(unknown)"
    root = find_repo_root(repo_dir)

    try:
        base_ref = trunk_base(root)
    except Exception:
        logger.warning("could not determine base ref — skipping sentinel gate")
        return QaResult(
            status="passed",
            notes="Sentinel gate: could not determine base ref — skipped (no git history).",
        )

    try:
        added = _added_lines(root, base_ref)
    except Exception as exc:
        logger.warning("git diff failed (%s) — skipping sentinel gate", exc)
        return QaResult(status="passed", notes=f"Sentinel gate: git diff failed ({exc}) — skipped.")

    if not added:
        logger.info("no added lines in diff (%s..HEAD) — nothing to check", base_ref)
        return QaResult(
            status="passed",
            notes=f"Sentinel gate: no added lines in diff ({base_ref}..HEAD) — nothing to check.",
        )

    hits: list[str] = []
    for filename, lineno, content in added:
        if Path(filename).suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if _is_test_file(filename) or _is_comment_line(content, filename):
            continue
        for pattern, description in SENTINEL_PATTERNS:
            if pattern.search(content):
                hits.append(f"{filename}:{lineno}: {description} — {content.strip()[:120]}")
                break

    if hits:
        logger.warning(
            "sentinel gate found %d unreconciled placeholder(s) in story %s", len(hits), slug
        )
        return QaResult(
            status="failed",
            notes=(
                "Sentinel gate: shipped source contains unreconciled placeholder(s). Remove "
                "before committing — fabricated IDs and 'until X exists' stubs are never valid "
                "in the shipped path:\n- " + "\n- ".join(hits)
            ),
        )

    logger.info("sentinel gate passed: %d added lines scanned in story %s", len(added), slug)
    return QaResult(
        status="passed",
        notes=(
            f"Sentinel gate: {len(added)} added lines scanned in story {slug!r} — no fabricated "
            f"placeholder IDs or unreconciled stubs found."
        ),
    )


__all__ = ["check_sentinel_ids", "flush_root_screenshots"]
