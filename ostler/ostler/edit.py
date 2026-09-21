"""`ostler edit` — safe, format-preserving structured edits across JSON and Markdown."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ostler import markdown
from ostler.model import Graph

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
    moves: list[tuple[Path, Path]]
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
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dst)


def _doc_files(graph: Graph) -> list[Path]:
    files: list[Path] = []
    for key in ("epics", "specs", "features"):
        root = graph.doc_roots[key]
        if root.is_dir():
            files.extend(p for p in root.rglob("*")
                         if p.is_file() and p.suffix in (".json", ".md"))
    return sorted(set(files))


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


def _href_style_and_target(root: Path, href: str, origin: Path) -> tuple[str, str, str]:
    """Classify *href* (cited from *origin*) the same way ``Graph.resolve_doc_ref`` does."""
    raw = href.split("?", 1)[0]
    path_part, _, anchor = raw.partition("#")
    if path_part.startswith("/"):
        return "rooted", path_part.lstrip("/"), anchor
    try:
        rel_candidate = (origin.parent / path_part).resolve().relative_to(root).as_posix()
    except ValueError:
        rel_candidate = None
    if rel_candidate is not None and (root / rel_candidate).is_file():
        return "relative", rel_candidate, anchor
    return "bare", path_part, anchor


def migrate_context(graph: Graph, node_type: str, service: str) -> EditPlan:
    """Move every ``node_type`` file for *service* into its registry ``context`` folder."""
    from ostler.registry import UI_TYPES_BY_NAME

    uitype = UI_TYPES_BY_NAME.get(node_type)
    if uitype is None:
        return EditPlan([], [], error=f"no UI node type named {node_type!r}")

    root = graph.root.resolve()
    features_root = graph.doc_roots["features"]
    service_root = (features_root / service).resolve()
    if not service_root.is_dir():
        return EditPlan([], [], error=f"no service directory {service_root.as_posix()}")
    expected_dir = (service_root / uitype.context) if uitype.context else service_root

    moves_map: dict[Path, Path] = {}
    for node in graph.ui_nodes_of_type(node_type):
        if node.kind != "file":
            continue
        node_path = node.path.resolve()
        try:
            node_path.relative_to(service_root)
        except ValueError:
            continue
        if node_path.parent == expected_dir:
            continue
        moves_map[node_path] = expected_dir / node_path.name

    if not moves_map:
        return EditPlan([], [], error=f"no {node_type} files to move for service '{service}'")

    def repo_rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    old_to_new_id = {repo_rel(old): repo_rel(new) for old, new in moves_map.items()}

    texts: dict[Path, str] = {}

    def current_text(path: Path) -> str:
        if path not in texts:
            texts[path] = path.read_text(encoding="utf-8")
        return texts[path]

    for node in graph.ui_nodes:
        if not node.links:
            continue
        citing_old = node.path.resolve()
        citing_new = moves_map.get(citing_old, citing_old)
        text = current_text(citing_old)
        for _text, href, _line in node.links:
            style, target_id, anchor = _href_style_and_target(root, href, citing_old)
            new_target_id = old_to_new_id.get(target_id, target_id)
            if new_target_id == target_id and citing_new == citing_old:
                continue
            if style == "rooted":
                new_href = "/" + new_target_id
            elif style == "relative":
                new_href = (root / new_target_id).relative_to(
                    citing_new.parent, walk_up=True).as_posix()
            else:
                new_href = new_target_id
            if anchor:
                new_href = f"{new_href}#{anchor}"
            if new_href == href:
                continue
            old_link = f"]({href})"
            new_link = f"]({new_href})"
            if old_link in text:
                text = text.replace(old_link, new_link)
        texts[citing_old] = text

    file_changes = []
    for path, new_text in texts.items():
        old_text = path.read_text(encoding="utf-8")
        if new_text != old_text:
            file_changes.append(FileChange(path, old_text, new_text))

    moves = sorted(moves_map.items())
    return EditPlan(file_changes, moves)



RESOLUTION_FILE = "review-resolution.json"
SETTLEMENT_FILE = "review-settlement.json"


def _navigate(obj, pointer: str):
    """Resolve a dotted pointer (`a.b.0.c`) against parsed JSON."""
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
        if not isinstance(a, dict):
            return (f"{fid}: assertion must be an object {{file, pointer, equals}}, "
                     f"got {a!r}")
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
    """Compute (do not write) the story.md status FileChange — same transform as crud.set_status, but as a dry-runnable plan entry."""
    found = graph.find_story(slug)
    if found is None or found[1].story_md is None:
        return EditPlan([], [], error=f"no story '{slug}' with a story.md")
    path = found[1].story_md
    raw = path.read_text(encoding="utf-8")
    doc = markdown.split(raw)
    fm = doc.frontmatter or {"type": "story", "slug": slug}
    fm["status"] = status
    doc.raw_frontmatter = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    _set_status_bullet(doc, status)
    return FileChange(path, raw, doc.render())


def _set_status_bullet(doc: markdown.MarkdownDoc, status: str) -> None:
    """Rewrite the value of the story's ``- **Status**: …`` bullet in place."""
    bullet = doc.find_bullet("status")
    if bullet is None:
        return
    lines = doc.body.split("\n")
    head, sep, _ = lines[bullet.line_start].partition(":")
    if sep:
        lines[bullet.line_start] = f"{head}{sep} {status}"
        doc.replace_body(lines)


def _ledger_change(spec_dir: Path, ledger: dict) -> FileChange:
    """Plan the per-finding settlement sidecar write (created if absent, refreshed each pass)."""
    path = spec_dir / SETTLEMENT_FILE
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    new = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    return FileChange(path, old, new)


def settle_review(graph: Graph, slug: str) -> EditPlan:
    """Settle a story's review **per finding** from its `review-resolution.json`."""
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

    if any_blocked:
        status_change = _story_status_change(graph, slug, STATUS_BLOCKED)
    elif all_verified:
        status_change = _story_status_change(graph, slug, STATUS_APPLIED)
    else:
        status_change = None
    if isinstance(status_change, EditPlan):
        return status_change
    if status_change is not None and status_change.old != status_change.new:
        changes.append(status_change)
    return EditPlan(changes, [])
