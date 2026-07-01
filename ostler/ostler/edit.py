"""`ostler edit` — safe, format-preserving structured edits across JSON and Markdown.

All operations are **dry-run by default**: they compute the changes and print a unified diff but
write nothing. Pass ``write=True`` to apply.

    set-owner <gap> <story>   point a knowledge gap at its owning story
    relink <old> <new>        replace a path reference everywhere it appears
    rename <old> <new>        rename a story/epic slug and cascade every reference (+ folder move)
    settle-review <slug>      flip a story's status from a coder review-resolution verdict,
                              but ONLY after verifying every artifact/assertion the verdict
                              cites actually exists (fail-closed — see `settle_review`)
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import markdown
from .model import Graph

# Story status the gate stamps for a fully-addressed, artifact-verified resolution
# vs a verdict that reports an unresolved (blocked) finding.
STATUS_APPLIED = "Review fixes applied"
STATUS_BLOCKED = "Blocked"


@dataclass
class FileChange:
    path: Path
    old: str
    new: str

    def diff(self) -> str:
        rel = self.path.as_posix()
        return "".join(difflib.unified_diff(
            self.old.splitlines(keepends=True),
            self.new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}",
        ))


@dataclass
class EditPlan:
    changes: list[FileChange]
    moves: list[tuple[Path, Path]]  # (src dir, dst dir)
    error: str = ""

    def render(self) -> str:
        if self.error:
            return f"error: {self.error}"
        if not self.changes and not self.moves:
            return "no changes"
        parts = [c.diff() for c in self.changes]
        for src, dst in self.moves:
            parts.append(f"rename {src.as_posix()} -> {dst.as_posix()}\n")
        return "".join(parts)

    def apply(self) -> None:
        for c in self.changes:
            c.path.write_text(c.new, encoding="utf-8")
        for src, dst in self.moves:
            if src.exists():
                src.rename(dst)


def _doc_files(graph: Graph) -> list[Path]:
    files: list[Path] = []
    for key in ("epics", "knowledge", "specs"):
        root = graph.doc_roots[key]
        if root.is_dir():
            files.extend(p for p in root.rglob("*")
                         if p.is_file() and p.suffix in (".json", ".md"))
    return sorted(set(files))


# ---------------------------------------------------------------------------
def _set_json_owner(raw: str, gap_id: str, owner: str) -> str | None:
    """Targeted, format-preserving edit: set the `owner` of the gap whose id is *gap_id*.

    Edits only that gap's `owner` value (or inserts one right after its `id`) so the rest of the
    file — including predykt's inline-compact object style — is untouched.
    """
    id_match = re.search(r'"id"\s*:\s*"' + re.escape(gap_id) + r'"', raw)
    if not id_match:
        return None
    nxt = re.search(r'"id"\s*:\s*"', raw[id_match.end():])
    end = id_match.end() + nxt.start() if nxt else len(raw)
    region = raw[id_match.end():end]

    om = re.search(r'("owner"\s*:\s*")[^"]*(")', region)
    if om:
        new_region = region[:om.start()] + om.group(1) + owner + om.group(2) + region[om.end():]
        return raw[:id_match.end()] + new_region + raw[end:]
    # No owner key in this gap — insert one immediately after the id value.
    return raw[:id_match.end()] + f', "owner": "{owner}"' + raw[id_match.end():]


def set_owner(graph: Graph, gap_id: str, story_slug: str) -> EditPlan:
    hit = graph.find_gap(gap_id)
    if not hit:
        return EditPlan([], [], error=f"no gap '{gap_id}' found")
    record, _ = hit
    raw = record.path.read_text(encoding="utf-8")

    if record.fmt == "json":
        new = _set_json_owner(raw, gap_id, story_slug)
        if new is None:
            return EditPlan([], [], error=f"gap '{gap_id}' not found in {record.path.name}")
    else:
        doc = markdown.split(raw)
        fm = doc.frontmatter or {}
        for g in fm.get("gaps", []):
            if isinstance(g, dict) and g.get("id") == gap_id:
                g["owner"] = story_slug
        doc.raw_frontmatter = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
        new = doc.render()

    if new == raw:
        return EditPlan([], [])
    return EditPlan([FileChange(record.path, raw, new)], [])


def _replace_token(text: str, old: str, new: str) -> str:
    """Replace whole-token occurrences of *old* (slug/path), respecting word/path boundaries."""
    pattern = re.compile(rf"(?<![\w/-]){re.escape(old)}(?![\w/-])")
    return pattern.sub(new, text)


def relink(graph: Graph, old_path: str, new_path: str) -> EditPlan:
    changes = []
    for path in _doc_files(graph):
        raw = path.read_text(encoding="utf-8")
        if old_path not in raw:
            continue
        new = raw.replace(old_path, new_path)
        if new != raw:
            changes.append(FileChange(path, raw, new))
    return EditPlan(changes, [])


def rename(graph: Graph, old_slug: str, new_slug: str) -> EditPlan:
    changes = []
    for path in _doc_files(graph):
        raw = path.read_text(encoding="utf-8")
        new = _replace_token(raw, old_slug, new_slug)
        if new != raw:
            changes.append(FileChange(path, raw, new))

    moves: list[tuple[Path, Path]] = []
    for epic in graph.epics:
        src = epic.directory / "stories" / old_slug
        if src.is_dir():
            moves.append((src, epic.directory / "stories" / new_slug))

    if not changes and not moves:
        return EditPlan([], [], error=f"slug '{old_slug}' not found")
    return EditPlan(changes, moves)


# ---------------------------------------------------------------------------
# settle-review — artifact-gated story-status transition from a coder verdict
# ---------------------------------------------------------------------------
# The coder's apply-review step emits a structured verdict (`review-resolution.json`
# in the story's spec dir) instead of hand-writing the story status. Ostler is the
# only tool that mutates the story status, and here it does so ONLY after verifying
# the verdict's claims against the filesystem — closing the loophole where a
# remediation agent declares a finding "resolved" (and flips the status) without
# producing the proof the reviewer asked for. The verdict shape:
#
#   {
#     "status": "applied" | "blocked",          # the agent's overall claim
#     "findings": [
#       {
#         "id": "Finding 1",
#         "disposition": "addressed" | "blocked",
#         "artifacts": ["evidence/new-foundation-1280.png", ...],   # files that must exist
#         "assertions": [                                            # exact-value checks
#           {"file": "qa/observations.json", "pointer": "form.headingLabel",
#            "equals": "Foundation area"}
#         ]
#       }
#     ]
#   }
#
# Gate rules (fail-closed):
#   - every `artifacts` path of an `addressed` finding must exist under the spec dir;
#   - every `assertions` entry must resolve to its EXACT `equals` value (no "either/or"
#     — the gate refuses an assertion that was broadened to mask a mismatch);
#   - a finding may only be `addressed` if all its artifacts+assertions hold; otherwise
#     the whole transition is refused with the precise reason and NO status is written.
# A verdict that honestly reports a `blocked` finding passes the gate and stamps the
# story `Blocked` (the workflow then escalates to the operator).

RESOLUTION_FILE = "review-resolution.json"
# Per-finding ledger the review loop branches on. settle-review (re)writes it every
# pass so the workflow can re-apply ONLY the still-open findings (targeted re-verify),
# escalate a blocked finding by itself, and approve once every finding is verified —
# instead of re-running a full review that re-litigates already-settled findings.
SETTLEMENT_FILE = "review-settlement.json"


def _navigate(obj, pointer: str):
    """Resolve a dotted pointer (`a.b.0.c`) against parsed JSON. Returns a sentinel
    `KeyError`-raising miss as (False, None); a hit as (True, value)."""
    cur = obj
    for part in pointer.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur[part]
        elif isinstance(cur, list):
            if not (part.lstrip("-").isdigit()):
                return False, None
            idx = int(part)
            if not (-len(cur) <= idx < len(cur)):
                return False, None
            cur = cur[idx]
        else:
            return False, None
    return True, cur


def _verify_finding(spec_dir: Path, finding: dict) -> str:
    """Return "" if the finding's cited artifacts+assertions all hold, else the reason."""
    fid = finding.get("id", "<unnamed finding>")
    for rel in finding.get("artifacts", []) or []:
        if not (spec_dir / rel).is_file():
            return f"{fid}: cited artifact '{rel}' does not exist"
    for a in finding.get("assertions", []) or []:
        afile = a.get("file", "")
        pointer = a.get("pointer", "")
        expected = a.get("equals")
        target = spec_dir / afile
        if not target.is_file():
            return f"{fid}: assertion file '{afile}' does not exist"
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            return f"{fid}: assertion file '{afile}' is not readable JSON ({exc})"
        ok, actual = _navigate(data, pointer)
        if not ok:
            return f"{fid}: assertion pointer '{pointer}' not found in '{afile}'"
        if actual != expected:
            return (f"{fid}: assertion '{afile}:{pointer}' is {actual!r}, "
                    f"expected exactly {expected!r}")
    return ""


def _story_status_change(graph: Graph, slug: str, status: str) -> FileChange | EditPlan:
    """Compute (do not write) the story.md status FileChange — same transform as
    crud.set_status, but as a dry-runnable plan entry. Returns an EditPlan(error=…) on
    a missing story."""
    found = graph.find_story(slug)
    if found is None or found[1].story_md is None:
        return EditPlan([], [], error=f"no story '{slug}' with a story.md")
    path = found[1].story_md
    raw = path.read_text(encoding="utf-8")
    doc = markdown.split(raw)
    fm = doc.frontmatter or {"type": "story", "slug": slug}
    fm["status"] = status
    doc.raw_frontmatter = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    doc.body = re.sub(r"(\*\*Status\*\*:\s*).*", lambda m: m.group(1) + status,
                      doc.body, count=1)
    return FileChange(path, raw, doc.render())


def _ledger_change(spec_dir: Path, ledger: dict) -> FileChange:
    """Plan the per-finding settlement sidecar write (created if absent, refreshed each
    pass). Always emitted so the workflow has the authoritative per-finding state."""
    path = spec_dir / SETTLEMENT_FILE
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    new = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    return FileChange(path, old, new)


def settle_review(graph: Graph, slug: str) -> EditPlan:
    """Settle a story's review **per finding** from its `review-resolution.json`.

    For each finding the verdict claims `addressed`, every cited artifact/assertion is
    verified against the filesystem (fail-closed: unproven proof never counts as done).
    The outcome is a three-way ledger written to `review-settlement.json`:

      - ``verified`` — addressed AND its proof holds (settled once; stays settled);
      - ``open``     — addressed but a cited artifact is missing / an assertion is wrong
                       (re-apply just this finding; never flips status to applied);
      - ``blocked``  — the verdict reports it unresolvable (escalates individually).

    The story status is flipped to ``Review fixes applied`` ONLY when every finding is
    verified and none blocked; to ``Blocked`` when any finding is blocked; and is left
    untouched while findings are merely open (the loop re-applies them). A malformed
    verdict (no findings / unknown disposition) is still a hard error."""
    spec_dir = graph.doc_roots["specs"] / slug
    resolution = spec_dir / RESOLUTION_FILE
    if not resolution.is_file():
        return EditPlan([], [], error=f"no {RESOLUTION_FILE} in {spec_dir.as_posix()}")
    try:
        verdict = json.loads(resolution.read_text(encoding="utf-8"))
    except ValueError as exc:
        return EditPlan([], [], error=f"{RESOLUTION_FILE} is not valid JSON ({exc})")

    findings = verdict.get("findings", [])
    if not isinstance(findings, list) or not findings:
        return EditPlan([], [], error=f"{RESOLUTION_FILE} has no findings")

    verified: list[str] = []
    open_: list[dict] = []
    blocked: list[str] = []
    for finding in findings:
        fid = finding.get("id", "<unnamed finding>")
        disposition = str(finding.get("disposition", "")).lower()
        if disposition == "addressed":
            reason = _verify_finding(spec_dir, finding)
            if reason:
                open_.append({"id": fid, "reason": reason})
            else:
                verified.append(fid)
        elif disposition == "blocked":
            blocked.append(fid)
        else:
            return EditPlan([], [], error=f"{fid}: unknown disposition '{disposition}'")

    any_blocked = bool(blocked) or str(verdict.get("status", "")).lower() == "blocked"
    all_verified = not open_ and not any_blocked and len(verified) == len(findings)
    ledger = {
        "verified": verified,
        "open": open_,
        "blocked": blocked,
        "all_verified": all_verified,
        "any_blocked": any_blocked,
    }
    changes: list[FileChange] = [_ledger_change(spec_dir, ledger)]

    # Status transition is all-or-nothing on the per-finding outcome: applied only when
    # every finding verified, blocked when any is, otherwise unchanged (open → re-apply).
    if any_blocked:
        status_change = _story_status_change(graph, slug, STATUS_BLOCKED)
    elif all_verified:
        status_change = _story_status_change(graph, slug, STATUS_APPLIED)
    else:
        status_change = None
    if isinstance(status_change, EditPlan):  # missing story → propagate the error
        return status_change
    if status_change is not None and status_change.old != status_change.new:
        changes.append(status_change)
    return EditPlan(changes, [])
