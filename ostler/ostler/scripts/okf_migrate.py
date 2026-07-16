"""One-shot, idempotent migration from the legacy JSON+markdown layout to the OKF markdown format.

Folds ``seed.json`` + ``dependencies.json`` into each ``epic.md`` (``## Seeds`` / ``## Stories``),
stamps ``type`` frontmatter on every Concept, converts knowledge ``.json`` → ``.md``, turns
``epics-todo.json`` into ``docs/epics/index.md``, and converts ``features/inventory.json`` entries
into ``feature`` Concepts. Legacy JSON is deleted. Re-running is a no-op.

Run:  ``python -m ostler.scripts.okf_migrate [REPO_ROOT]``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from .. import markdown, registry


def _dump_fm(fm: dict) -> str:
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# epics: fold seed.json + dependencies.json into epic.md
# ---------------------------------------------------------------------------
_SEED_META = ("status", "surface", "legacySurface", "backing", "prerequisites", "sourceBullet")


def _seed_block(item: dict) -> list[str]:
    sid = str(item.get("id"))
    out = [f"### {sid}"]
    status = item.get("status") or "backlog"
    out.append(f"- status: {status}")
    for k in _SEED_META:
        if k == "status":
            continue
        v = item.get(k)
        if v:
            out.append(f"- {k}: {str(v).strip()}")
    out.append("")
    prose = [str(item[k]).strip() for k in ("summary", "currentState", "notes") if item.get(k)]
    if prose:
        out.append("\n\n".join(prose))
        out.append("")
    return out


def _story_block(st: dict) -> list[str]:
    slug = str(st.get("slug"))
    covers = [str(x) for x in (st.get("seedItems") or [])]
    deps = [str(x) for x in (st.get("dependencies") or [])]
    out = [f"### {slug}"]
    if st.get("title"):
        out.append(f"- title: {st['title']}")
    if st.get("id"):
        out.append(f"- id: {st['id']}")
    out.append(f"- covers: {', '.join(covers) if covers else '(none)'}")
    out.append(f"- depends on: {', '.join(deps) if deps else '(none)'}")
    if st.get("phase") not in (None, ""):
        out.append(f"- phase: {st['phase']}")
    if st.get("effort"):
        out.append(f"- effort: {st['effort']}")
    out.append("")
    return out


def _stories_from_folders(edir: Path) -> list[dict]:
    """Synthesize story entries from stories/*/story.md when there is no dependencies.json
    (the story folders exist on disk but were never declared in a manifest)."""
    out = []
    for story_md in sorted(edir.glob("stories/*/story.md")):
        slug = story_md.parent.name
        doc = markdown.split(story_md.read_text(encoding="utf-8"))
        fm = (doc.frontmatter or {}) if doc.has_frontmatter else {}
        title = fm.get("title")
        if not title:
            first = next((ln for ln in doc.body.splitlines() if ln.startswith("# ")), "")
            title = first.lstrip("# ").removeprefix("Story:").strip()
        out.append({"slug": slug, "title": title, "seedItems": [], "dependencies": []})
    return out


def _migrate_epic(edir: Path) -> bool:
    seed_f = edir / "seed.json"
    deps_f = edir / "dependencies.json"
    epic_f = edir / "epic.md"
    if not epic_f.exists():
        return False
    has_legacy = seed_f.exists() or deps_f.exists()
    old = markdown.split(epic_f.read_text(encoding="utf-8"))
    fm = (old.frontmatter or {}) if old.has_frontmatter else {}
    if fm.get("type") == "epic" and not has_legacy:
        return False  # already migrated

    seed = _read_json(seed_f) if seed_f.exists() else {}
    deps = _read_json(deps_f) if deps_f.exists() else {}
    body = old.body
    fm.setdefault("type", "epic")
    fm.setdefault("id", str(deps.get("epicId") or seed.get("epicId") or edir.name))
    title = (fm.get("title") or deps.get("epicTitle")
             or (body.splitlines()[0].lstrip("# ").strip() if body.strip() else edir.name))
    fm["title"] = title

    # strip any pre-existing canonical sections from the old body, then re-append fresh
    lines = body.split("\n")
    cut = len(lines)
    for i, ln in enumerate(lines):
        if ln.strip() in ("## Seeds", "## Stories"):
            cut = i
            break
    narrative = "\n".join(lines[:cut]).rstrip()

    parts = [narrative, "", "## Seeds", ""]
    for item in (seed.get("items") or []):
        if item.get("id"):
            parts += _seed_block(item)
    parts += ["## Stories", ""]
    stories = deps.get("stories") or _stories_from_folders(edir)
    for st in stories:
        if st.get("slug"):
            parts += _story_block(st)

    epic_f.write_text(f"---\n{_dump_fm(fm)}---\n{chr(10).join(parts).rstrip()}\n", encoding="utf-8")
    seed_f.unlink(missing_ok=True)
    deps_f.unlink(missing_ok=True)
    return True


def _stamp_stories(edir: Path) -> int:
    n = 0
    for story_md in edir.glob("stories/*/story.md"):
        doc = markdown.split(story_md.read_text(encoding="utf-8"))
        fm = (doc.frontmatter or {}) if doc.has_frontmatter else {}
        if fm.get("type") == "story":
            continue
        slug = story_md.parent.name
        status = fm.get("status")
        if not status:
            sec = doc.find_section("Implementation Status")
            import re
            m = re.search(r"\*\*Status\*\*:\s*(.+)", sec.text if sec else doc.body)
            status = m.group(1).strip() if m else "Not started"
        fm = {"type": "story", "slug": slug, "status": status, **fm}
        fm["type"], fm["slug"], fm["status"] = "story", slug, status
        story_md.write_text(f"---\n{_dump_fm(fm)}---\n{doc.body}", encoding="utf-8")
        n += 1
    return n


# ---------------------------------------------------------------------------
# knowledge: .json → .md, stamp type on .md
# ---------------------------------------------------------------------------
def _migrate_knowledge(kroot: Path) -> int:
    n = 0
    for path in sorted(kroot.rglob("*.json")):
        data = _read_json(path)
        data.setdefault("type", "knowledge")
        surface = data.get("surface") or path.relative_to(kroot).with_suffix("").as_posix()
        data["surface"] = surface
        out = path.with_suffix(".md")
        body = f"# Surface knowledge: {surface}\n"
        out.write_text(f"---\n{_dump_fm(data)}---\n{body}", encoding="utf-8")
        path.unlink()
        n += 1
    for path in sorted(kroot.rglob("*.md")):
        doc = markdown.split(path.read_text(encoding="utf-8"))
        fm = (doc.frontmatter or {}) if doc.has_frontmatter else {}
        if fm.get("type") == "knowledge":
            continue
        fm = {"type": "knowledge", **fm}
        path.write_text(f"---\n{_dump_fm(fm)}---\n{doc.body}", encoding="utf-8")
        n += 1
    return n


# ---------------------------------------------------------------------------
# features: stamp type on .md; convert inventory.json entries to Concepts
# ---------------------------------------------------------------------------
def _migrate_features(froot: Path) -> int:
    n = 0
    inv = froot / "inventory.json"
    if inv.exists():
        data = _read_json(inv)
        entries = data.get("surfaces") or data.get("entries") or []
        for e in entries:
            if not isinstance(e, dict):
                continue
            slug = str(e.get("slug") or e.get("id") or "").strip()
            if not slug:
                continue
            area = str(e.get("area") or "").strip()
            out = (froot / area / f"{slug}.md") if area else (froot / f"{slug}.md")
            if out.exists():
                continue
            fm = {"type": "feature", "slug": slug, "title": str(e.get("title") or slug)}
            if area:
                fm["area"] = area
            for k in ("route", "url", "role", "capture", "purpose"):
                if e.get(k) not in (None, ""):
                    fm[k] = e[k]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(f"---\n{_dump_fm(fm)}---\n# {fm['title']}\n", encoding="utf-8")
            n += 1
        inv.unlink()
    for path in sorted(froot.rglob("*.md")):
        if path.name in ("index.md", "log.md"):
            continue
        doc = markdown.split(path.read_text(encoding="utf-8"))
        fm = (doc.frontmatter or {}) if doc.has_frontmatter else {}
        if fm.get("type") == "feature":
            continue
        rel = path.relative_to(froot).with_suffix("")
        fm = {"type": "feature",
              "slug": str(fm.get("slug") or rel.name),
              "title": str(fm.get("title") or rel.name),
              **fm}
        fm["type"] = "feature"
        path.write_text(f"---\n{_dump_fm(fm)}---\n{doc.body}", encoding="utf-8")
        n += 1
    return n


# ---------------------------------------------------------------------------
# specs: stamp a spec.* type on each process artifact (conformance only)
# ---------------------------------------------------------------------------
def _migrate_specs(sroot: Path) -> int:
    n = 0
    for path in sorted(sroot.glob("*/*.md")):
        if path.name in registry.RESERVED_FILES:
            continue
        doc = markdown.split(path.read_text(encoding="utf-8"))
        fm = (doc.frontmatter or {}) if doc.has_frontmatter else {}
        if str(fm.get("type", "")).startswith("spec"):
            continue
        fm.pop("type", None)   # a present-but-blank `type:` must not shadow the stamp
        fm = {"type": registry.spec_type_for(path.name), **fm}
        path.write_text(f"---\n{_dump_fm(fm)}---\n{doc.body}", encoding="utf-8")
        n += 1
    return n


# ---------------------------------------------------------------------------
# epics-todo.json → docs/epics/index.md
# ---------------------------------------------------------------------------
def _migrate_todo(eroot: Path) -> bool:
    todo = eroot / "epics-todo.json"
    if not todo.exists():
        return False
    try:
        names = _read_json(todo)
    except json.JSONDecodeError:
        names = []
    if not isinstance(names, list):
        names = []
    lines = ["# Epics", "",
             "The ordered work queue for this repo (the OKF index of the epics bundle).", ""]
    for n in names:
        lines.append(f"- [{n}]({n}/epic.md)")
    (eroot / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    todo.unlink()
    return True


def _rewrite_knowledge_refs(docs: Path) -> None:
    """Story/epic prose that links ``docs/knowledge/…​.json`` must follow the ``.json`` → ``.md``
    conversion."""
    import re
    pat = re.compile(r"(docs/knowledge/[^\s)\]'\"`]+)\.json")
    for path in docs.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        new = pat.sub(r"\1.md", text)
        if new != text:
            path.write_text(new, encoding="utf-8")


def migrate(root: Path) -> dict:
    root = Path(root)
    docs = root / "docs"
    report = {"epics": 0, "stories": 0, "knowledge": 0, "features": 0, "specs": 0, "todo": False}
    eroot = docs / "epics"
    if eroot.is_dir():
        for edir in sorted(eroot.iterdir()):
            if not edir.is_dir():
                continue
            if _migrate_epic(edir):
                report["epics"] += 1
            report["stories"] += _stamp_stories(edir)
        report["todo"] = _migrate_todo(eroot)
    if (docs / "knowledge").is_dir():
        report["knowledge"] = _migrate_knowledge(docs / "knowledge")
    if (docs / "features").is_dir():
        report["features"] = _migrate_features(docs / "features")
    if (docs / "specs").is_dir():
        report["specs"] = _migrate_specs(docs / "specs")
    if docs.is_dir():
        _rewrite_knowledge_refs(docs)
    return report


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.cwd()
    rep = migrate(root)
    print(f"migrated {root}: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
