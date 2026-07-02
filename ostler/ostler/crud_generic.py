"""Kind-agnostic CRUD for instances of template-declared kinds (``.agents/templates.yml``).

Mirrors ``crud.py``'s per-type functions (``create_epic``, ``delete_feature``, ...) but driven by
a ``dynamic_registry.TemplateKind`` looked up at call time instead of a hardcoded shape — the
``ostler new/find/set/remove <kind> <name> [field=value ...]`` verbs all funnel through here.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import crud, ids, markdown, registry
from .dynamic_registry import TemplateKind
from .model import Graph


def _kind_by_name(graph: Graph, kind_name: str) -> TemplateKind | None:
    for k in graph.template_kinds:
        if k.name == kind_name:
            return k
    return None


def _safe_component(name: str) -> str | None:
    """None if *name* is safe to use as a path component; else an error message."""
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return f"invalid name '{name}'"
    return None


def _kind_children(graph: Graph, kind_name: str) -> list[TemplateKind]:
    return [k for k in graph.template_kinds if k.parent == kind_name]


def _instance_name(kind: TemplateKind, path: Path) -> str:
    return path.parent.name if kind.is_bundle else path.stem


def _find_path(graph: Graph, kind: TemplateKind, name: str) -> Path | None:
    base = graph.doc_roots.get(kind.doc_root)
    if base is None or not base.is_dir():
        return None
    for path in sorted(base.glob(kind.location)):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        if _instance_name(kind, path) == name:
            return path
    return None


def _resolve_path(graph: Graph, kind: TemplateKind, name: str,
                  fields: dict) -> tuple[Path | None, crud.Result | None]:
    """Substitute ``{name}``/``{parent}`` into ``kind.path_template``.

    *fields* is mutated: the parent-kind field (e.g. ``program=SMCNv3``) is popped once consumed,
    so it never ends up written into the child's own frontmatter.
    """
    subs = {"name": name}
    if kind.parent:
        if kind.parent not in fields:
            return None, crud.Result(False, f"missing required field '{kind.parent}'")
        parent_name = fields.pop(kind.parent)
        err = _safe_component(str(parent_name))
        if err:
            return None, crud.Result(False, err)
        parent_kind = _kind_by_name(graph, kind.parent)
        if parent_kind is None:
            return None, crud.Result(False, f"unknown parent kind '{kind.parent}'")
        parent_path = _find_path(graph, parent_kind, str(parent_name))
        if parent_path is None:
            return None, crud.Result(False, f"no {kind.parent} '{parent_name}'")
        doc_root = graph.doc_roots[kind.doc_root]
        subs["parent"] = parent_path.parent.relative_to(doc_root).as_posix()
    rel = kind.path_template.format(**subs)
    return graph.doc_roots[kind.doc_root] / rel, None


def create_instance(graph: Graph, kind_name: str, name: str, fields: dict) -> crud.Result:
    kind = _kind_by_name(graph, kind_name)
    if kind is None:
        return crud.Result(False, f"no template-declared kind '{kind_name}'")
    err = _safe_component(name)
    if err:
        return crud.Result(False, err)

    fields = dict(fields)
    path, err_result = _resolve_path(graph, kind, name, fields)
    if err_result is not None:
        return err_result
    if path.exists():
        return crud.Result(False, f"{kind_name} '{name}' already exists")

    missing = [r for r in kind.required if r != "type" and not fields.get(r)]
    if missing:
        return crud.Result(False, f"missing required field(s): {', '.join(missing)}")
    for fname, spec in kind.fields.items():
        enum = (spec or {}).get("enum")
        if enum and fname in fields and fields[fname] not in enum:
            return crud.Result(
                False, f"invalid {fname} '{fields[fname]}' (one of {', '.join(str(e) for e in enum)})")

    fm = {"type": kind.name, **fields}
    if kind.id:
        fm["id"] = ids.allocate(graph)
    fm["type"] = kind.name  # a caller-supplied `type` field must never override the kind's own

    path.parent.mkdir(parents=True, exist_ok=True)
    title = fields.get("title", name)
    path.write_text(f"---\n{crud.dump_frontmatter(fm)}---\n# {title}\n\n", encoding="utf-8")
    paths = [path]

    if kind.extra_files:
        interp = {**fields, "name": name}
        for ef in kind.extra_files:
            ef_path = path.parent / str(ef.get("path", "")).format(**interp)
            if ef_path.exists():
                continue
            ef_path.parent.mkdir(parents=True, exist_ok=True)
            ef_path.write_text(str(ef.get("content", "")).format(**interp), encoding="utf-8")
            paths.append(ef_path)

    entity_id = str(fm.get("id", ""))
    suffix = f" ({entity_id})" if entity_id else ""
    return crud.Result(True, f"created {kind_name} '{name}'{suffix}", paths, entity_id=entity_id)


def find_instance(graph: Graph, kind_name: str, name: str | None = None) -> list[dict]:
    kind = _kind_by_name(graph, kind_name)
    if kind is None:
        return []
    base = graph.doc_roots.get(kind.doc_root)
    if base is None or not base.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(base.glob(kind.location)):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        inst_name = _instance_name(kind, path)
        if name is not None and inst_name != name:
            continue
        try:
            fm = (markdown.split(path.read_text(encoding="utf-8")).frontmatter) or {}
        except OSError:
            continue
        row = dict(fm)
        row["type"] = kind.name
        row["name"] = inst_name
        row["path"] = path.relative_to(graph.root).as_posix()
        rows.append(row)
    return rows


def edit_instance(graph: Graph, kind_name: str, name: str, fields: dict) -> crud.Result:
    kind = _kind_by_name(graph, kind_name)
    if kind is None:
        return crud.Result(False, f"no template-declared kind '{kind_name}'")
    path = _find_path(graph, kind, name)
    if path is None:
        return crud.Result(False, f"no {kind_name} '{name}'")
    for fname, spec in kind.fields.items():
        enum = (spec or {}).get("enum")
        if enum and fname in fields and fields[fname] not in enum:
            return crud.Result(
                False, f"invalid {fname} '{fields[fname]}' (one of {', '.join(str(e) for e in enum)})")

    doc = markdown.split(path.read_text(encoding="utf-8"))
    fm = doc.frontmatter or {"type": kind.name}
    fm.update(fields)
    fm["type"] = kind.name
    doc.raw_frontmatter = crud.dump_frontmatter(fm)
    path.write_text(doc.render(), encoding="utf-8")
    return crud.Result(True, f"updated {kind_name} '{name}'", [path])


def delete_instance(graph: Graph, kind_name: str, name: str) -> crud.Result:
    kind = _kind_by_name(graph, kind_name)
    if kind is None:
        return crud.Result(False, f"no template-declared kind '{kind_name}'")
    path = _find_path(graph, kind, name)
    if path is None:
        return crud.Result(False, f"no {kind_name} '{name}'")
    if kind.is_bundle:
        shutil.rmtree(path.parent)
        removed = path.parent
    else:
        path.unlink()
        removed = path
    return crud.Result(True, f"deleted {kind_name} '{name}'", [removed])
