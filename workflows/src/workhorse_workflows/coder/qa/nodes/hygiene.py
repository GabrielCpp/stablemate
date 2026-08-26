"""The two pre-commit hygiene gates: relocate stray screenshots, reject sentinel IDs.

Ports `flush-root-screenshots.py` and `check-sentinel-ids.py`. Both run right before the
commit, both work on the *code* repo rather than the docs repo, and both are the kind of
check that is worthless unless it is deterministic — an agent asked "did you leave any
placeholders behind?" answers no.

Both scripts had re-typed `workhorse.scriptutil.find_repo_root` character for character
rather than importing it. They call the engine's copy here, which is not a narrowing: the
bodies were identical, and neither YAML node carried a `cwd:`, so the run's `repo_dir`
input (or the upward walk from it) resolves the same repo the environment read did.

The gates disagree about what a problem means, and that stays: a screenshot that cannot be
moved is logged and the flow continues, while a sentinel ID fails the QA pass. One is
tidying, the other is a shipped-code defect.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from unidiff.patch import PatchSet
from unidiff.errors import UnidiffParseError
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import QaResult, ScreenshotFlush
from workhorse_workflows.kit import diff_text, list_tracked_files, merge_base

#: What counts as a screenshot at the repo root.
IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})

#: An added line matching any of these is an unreconciled placeholder in shipped source.
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

#: Only these are scanned. A sentinel in a config file is not shipped behavior.
SOURCE_EXTENSIONS = frozenset({".go", ".ts", ".tsx", ".js", ".jsx"})

#: Filename markers for test files, which are allowed their placeholders.
TEST_MARKERS = (
    "_test.go",
    ".spec.ts",
    ".spec.tsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".test.js",
)


# --- stray screenshots -------------------------------------------------------


def _tracked_names(root: Path) -> set[str]:
    """Top-level files git already tracks. Empty when git is unavailable, which makes the
    move best-effort rather than wrong — nothing is then treated as a committed asset."""
    return {path for path in list_tracked_files(root) if "/" not in path}


def _dest_dir(root: Path, spec_dir: str) -> Path | None:
    """`<spec_dir>/qa/` under the repo root, or `None` when `spec_dir` is not usable.

    The two guards are against a blank or garbage `spec_dir` resolving to — or above — the
    repo root, which would make the "destination" the very directory being cleaned.
    """
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
    """`dest/name`, suffixed `-1`, `-2`, … if it is taken. Moves never overwrite."""
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
    """Move untracked root images into `<spec_dir>/qa/` so `git add -A` cannot commit them.

    QA is supposed to screenshot to an absolute path under the spec dir; in practice a bare
    filename passed to `page.screenshot()` lands at the agent's cwd instead. Conservative on
    purpose — top-level only, untracked only, moves rather than deletes — because the cost
    of being wrong here is destroying a committed asset.
    """
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


# --- sentinel IDs ------------------------------------------------------------


def _base_ref(root: Path) -> str:
    """The ref to diff against: the merge base with the default branch, else `HEAD~1`."""
    for branch in ("origin/master", "origin/main", "master", "main"):
        base = merge_base(root, "HEAD", branch)
        if base:
            return base
    return "HEAD~1"


def _added_lines(root: Path, base_ref: str) -> list[tuple[str, int, str]]:
    """`(filename, lineno, content)` for every `+` line between `base_ref` and `HEAD`.

    Parsed rather than scanned. The hand-written version this replaces tracked the current
    file and line number in loop variables and re-derived the line number from
    `re.search(r"\\+(\\d+)", line)` on the hunk header — which reads the *first* `+N` in
    `@@ -12,0 +34 @@`, and so read the pre-image start for any header whose old side happens
    to be spelled without a comma. Worse, every one of its `startswith` tests is a claim
    about a *line's position in the file*, which a hunk body can forge: a diff of a diff —
    which this repo contains, in its own test fixtures — carries added lines whose own
    content begins `+++ b/` or `@@ `, silently re-pointing the filename and line counter at
    whatever that fixture happened to say. `unidiff` knows a hunk body from a hunk header,
    and reads the target line number the format already states.
    """
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
        # An added line always has a target line number — it is the post-image the hunk
        # header counts. The check is what keeps the span type honest for the callers.
        if line.is_added and line.target_line_no is not None
    ]


def _is_test_file(filename: str) -> bool:
    lower = filename.lower()
    return any(marker in lower for marker in TEST_MARKERS)


def _is_comment_line(content: str, filename: str) -> bool:
    """Whether the line is a pure comment — a heuristic, and only for the two dialects
    whose sentinels this gate is aimed at. Anything else is scanned."""
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
    """Fail the pass if this branch added a fabricated ID or an "until X exists" stub.

    Every failure to *run* the gate returns `passed`, and that is not an oversight: it is a
    pre-commit tidiness check over a diff, and a repo with no git history to diff has no
    added lines to be wrong about. The gate that must fail closed is the evidence gate.
    """
    slug = story_slug or "(unknown)"
    root = find_repo_root(repo_dir)

    try:
        base_ref = _base_ref(root)
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
