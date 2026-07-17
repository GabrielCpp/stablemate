"""User-declared OKF hierarchies — per-repo ``.agents/templates.yml``.

A template lets a repo define its own Concept **kinds** (beyond the built-in
epic/story/knowledge/feature/spec in ``registry.py``) with their own directory shape, required
frontmatter, and status enums. ``model.load()`` merges each discovered kind's ``doc_root`` into
``Graph.doc_roots``; ``doctor.py`` and ``crud_generic.py`` consult ``Graph.template_kinds``
generically. ``registry.py`` itself stays built-ins-only — this module never touches it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ostler import registry

TEMPLATES_FILENAME = "templates.yml"

BUILTIN_NAMES: frozenset[str] = frozenset(t.name for t in registry.REGISTRY)


def templates_path(root: Path) -> Path:
    return root / ".agents" / TEMPLATES_FILENAME


def load_raw(root: Path) -> dict:
    """The parsed ``.agents/templates.yml`` mapping (template name → definition). ``{}`` if
    absent or malformed — mirrors ``model._load_ids``'s tolerant-on-corruption stance."""
    p = templates_path(root)
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def save_raw(root: Path, data: dict) -> None:
    p = templates_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


@dataclass(frozen=True)
class TemplateKind:
    """One Concept kind declared by a template. See the ``ostler template`` design doc for the
    full field-by-field semantics; the short version:

    *doc_root*/*default_path* is this kind's ``Graph.doc_roots`` key + the repo-relative
    directory assigned to it the first time any kind declares it (analogous to the built-in
    ``EntityType.doc_root``, but with an explicit default since template doc_roots have no
    hardcoded ``docs/<key>`` convention). *path_template* is the instance file path relative to
    doc_root, using ``{name}``/``{parent}`` placeholders (see ``crud_generic._resolve_path``).
    *parent* names another kind in the same template this nests under, resolved by scanning the
    parent kind's own instances for a name match (not a stored path) — see ``crud_generic.
    _parent_dir``.
    """
    name: str
    doc_root: str
    default_path: str
    path_template: str
    parent: str | None = None
    id: bool = False
    required: tuple[str, ...] = ()
    fields: dict = field(default_factory=dict)
    extra_files: tuple[dict, ...] = ()
    template: str = ""
    note: str = ""

    @property
    def is_bundle(self) -> bool:
        """True when each instance gets its own directory (``path_template`` ends in
        ``{name}/<file>.md``), so it can validly be another kind's ``parent``."""
        segs = self.path_template.split("/")
        return len(segs) >= 2 and segs[-2] == "{name}"

    @property
    def location(self) -> str:
        """``Path.glob``-style pattern relative to doc_root, for doctor's conformance walk.

        ``{parent}`` (may expand across several real nesting levels) → ``**``; ``{name}`` → ``*``;
        a placeholder mixed with literal characters keeps the literal part (``G{name}`` → ``G*``);
        pure-literal segments pass through unchanged.
        """
        return "/".join(_glob_segment(seg) for seg in self.path_template.split("/"))


def _glob_segment(seg: str) -> str:
    if seg == "{parent}":
        return "**"
    if seg == "{name}":
        return "*"
    return seg.replace("{parent}", "*").replace("{name}", "*")


def parse_kind(template_name: str, raw: dict) -> TemplateKind | None:
    """Build a ``TemplateKind`` from one ``kinds:`` entry. ``None`` if a required field is
    missing (dropped by ``load_kinds``, not a hard error — hard validation happens at
    ``template new``/``edit`` time in ``templates.py``)."""
    name = str(raw.get("name") or "").strip()
    doc_root = str(raw.get("doc_root") or "").strip()
    default_path = str(raw.get("default_path") or "").strip()
    path_template = str(raw.get("path_template") or "").strip()
    if not (name and doc_root and default_path and path_template):
        return None
    return TemplateKind(
        name=name,
        doc_root=doc_root,
        default_path=default_path,
        path_template=path_template,
        parent=(str(raw["parent"]).strip() if raw.get("parent") else None),
        id=bool(raw.get("id", False)),
        required=tuple(raw.get("required") or ()),
        fields=dict(raw.get("fields") or {}),
        extra_files=tuple(raw.get("extra_files") or ()),
        template=template_name,
        note=str(raw.get("note") or ""),
    )


def load_kinds(root: Path) -> tuple[TemplateKind, ...]:
    """Flatten every template's ``kinds:`` into ``TemplateKind``s.

    Drops (silently, tolerant on malformed repo state) any kind colliding with a built-in name
    or an already-seen kind name from an earlier template. ``()`` if the file is absent.
    """
    data = load_raw(root)
    kinds: list[TemplateKind] = []
    seen: set[str] = set(BUILTIN_NAMES)
    for tmpl_name, tmpl in data.items():
        if not isinstance(tmpl, dict):
            continue
        for raw_kind in tmpl.get("kinds") or ():
            if not isinstance(raw_kind, dict):
                continue
            kind = parse_kind(tmpl_name, raw_kind)
            if kind is None or kind.name in seen:
                continue
            seen.add(kind.name)
            kinds.append(kind)
    return tuple(kinds)


def as_entity_types(kinds: tuple[TemplateKind, ...]) -> tuple[registry.EntityType, ...]:
    """Template kinds reduced to the shape ``doctor.py``'s conformance walk consumes —
    conformance-only (no bundled JSON Schema), same treatment ``spec.*`` already gets."""
    return tuple(
        registry.EntityType(name=k.name, doc_root=k.doc_root, location=k.location)
        for k in kinds
    )


def validate_kinds(existing: tuple[TemplateKind, ...], new_kinds: list[TemplateKind]) -> list[str]:
    """Hard-error checks run at ``template new``/``edit`` time (not by ``load_kinds``, which stays
    tolerant): name collisions, a ``parent`` pointing at a leaf-shaped or unknown kind, and
    ``extra_files`` declared on a leaf-shaped kind."""
    errors: list[str] = []
    by_name = {k.name: k for k in existing}
    for k in new_kinds:
        if k.name in BUILTIN_NAMES:
            errors.append(f"kind '{k.name}' collides with a built-in type")
        elif k.name in by_name:
            errors.append(f"kind '{k.name}' already declared")
        by_name[k.name] = k
    for k in new_kinds:
        if k.parent:
            parent = by_name.get(k.parent)
            if parent is None:
                errors.append(f"kind '{k.name}': parent '{k.parent}' is not a declared kind")
            elif not parent.is_bundle:
                errors.append(
                    f"kind '{k.name}': parent '{k.parent}' is leaf-shaped (its path_template "
                    "must end in '{name}/<file>.md' to be usable as a parent)")
        if k.extra_files and not k.is_bundle:
            errors.append(
                f"kind '{k.name}': extra_files requires a bundle-shaped path_template "
                "(ending in '{name}/<file>.md')")
    return errors
