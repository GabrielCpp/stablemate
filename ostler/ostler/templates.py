"""``ostler template new/edit/find/delete/apply`` — CRUD over ``.agents/templates.yml``.

The YAML file is the live definition (a kind is usable via ``ostler new/find/set/remove`` the
moment it's written — see ``dynamic_registry.load_kinds``, consulted by ``model.load()`` on every
run). ``apply`` only does the remaining disk side effects: ``mkdir -p`` each declared kind's
``doc_root`` directory and inject a marker-delimited section into ``CLAUDE.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import dynamic_registry
from .crud import Result
from .dynamic_registry import TemplateKind


def _find_kind_dict(tmpl: dict, kind_name: str) -> dict | None:
    for raw_kind in tmpl.get("kinds") or ():
        if isinstance(raw_kind, dict) and raw_kind.get("name") == kind_name:
            return raw_kind
    return None


def _set_dotted(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        nxt = d.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            d[part] = nxt
        d = nxt
    d[parts[-1]] = value


def _parsed_kinds(tmpl_name: str, tmpl: dict) -> list[TemplateKind]:
    out = []
    for raw_kind in tmpl.get("kinds") or ():
        if not isinstance(raw_kind, dict):
            continue
        kind = dynamic_registry.parse_kind(tmpl_name, raw_kind)
        if kind is not None:
            out.append(kind)
    return out


def new(root: Path, name: str, kinds: list[str] | None = None) -> Result:
    data = dynamic_registry.load_raw(root)
    if name in data:
        return Result(False, f"template '{name}' already exists")
    stub_kinds = []
    for kind_name in kinds or []:
        stub_kinds.append({
            "name": kind_name,
            "doc_root": kind_name,
            "default_path": f"docs/{kind_name}",
            "path_template": "{name}/" + f"{kind_name}.md",
            "required": ["type"],
        })
    data[name] = {"title": name, "kinds": stub_kinds}
    dynamic_registry.save_raw(root, data)
    return Result(True, f"created template '{name}' ({len(stub_kinds)} kind(s))",
                  [dynamic_registry.templates_path(root)])


def find(root: Path, name: str | None = None) -> list[dict]:
    data = dynamic_registry.load_raw(root)
    if name is not None:
        tmpl = data.get(name)
        if not isinstance(tmpl, dict):
            return []
        return [{"name": name, "title": tmpl.get("title", name),
                 "kinds": tmpl.get("kinds") or []}]
    rows = []
    for tmpl_name, tmpl in data.items():
        if not isinstance(tmpl, dict):
            continue
        rows.append({"name": tmpl_name, "title": tmpl.get("title", tmpl_name),
                     "kinds": len(tmpl.get("kinds") or [])})
    return rows


def edit(root: Path, name: str, assignments: list[str]) -> Result:
    """Apply ``kind.field[.subfield]=value`` assignments (``--set``), then re-validate."""
    data = dynamic_registry.load_raw(root)
    tmpl = data.get(name)
    if not isinstance(tmpl, dict):
        return Result(False, f"no template '{name}'")
    tmpl.setdefault("kinds", [])

    for assignment in assignments:
        if "=" not in assignment:
            return Result(False, f"invalid --set '{assignment}' (expected kind.field=value)")
        path, _, raw_value = assignment.partition("=")
        if "." not in path:
            return Result(False, f"invalid --set '{path}' (expected kind.field=value)")
        kind_name, _, field_path = path.partition(".")
        kind_dict = _find_kind_dict(tmpl, kind_name)
        if kind_dict is None:
            kind_dict = {"name": kind_name}
            tmpl["kinds"].append(kind_dict)
        try:
            value = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            value = raw_value
        _set_dotted(kind_dict, field_path, value)

    other_kinds: list[TemplateKind] = []
    for other_name, other_tmpl in data.items():
        if other_name != name and isinstance(other_tmpl, dict):
            other_kinds.extend(_parsed_kinds(other_name, other_tmpl))
    new_kinds = _parsed_kinds(name, tmpl)
    errors = dynamic_registry.validate_kinds(tuple(other_kinds), new_kinds)
    if errors:
        return Result(False, "; ".join(errors))

    data[name] = tmpl
    dynamic_registry.save_raw(root, data)
    return Result(True, f"updated template '{name}'", [dynamic_registry.templates_path(root)])


def delete(root: Path, name: str) -> Result:
    data = dynamic_registry.load_raw(root)
    if name not in data:
        return Result(False, f"no template '{name}'")
    del data[name]
    dynamic_registry.save_raw(root, data)
    return Result(True, f"deleted template '{name}'", [dynamic_registry.templates_path(root)])


# ---------------------------------------------------------------------------
# apply: directory scaffolding + CLAUDE.md guidance (idempotent, re-runnable)
# ---------------------------------------------------------------------------
_MARKER_START = "<!-- ostler:template:{name}:start -->"
_MARKER_END = "<!-- ostler:template:{name}:end -->"


def _claude_section(name: str, title: str, kinds: list[TemplateKind]) -> str:
    lines = [_MARKER_START.format(name=name), f"### {title} (`ostler template {name}`)", ""]
    for k in kinds:
        parent = f", nested under `{k.parent}`" if k.parent else ""
        lines.append(f"- `{k.name}`{parent} — `ostler new {k.name} <name> [field=value ...]`")
    lines += [
        "",
        f"Manage instances with `ostler new/find/set/remove <kind> <name> [field=value ...]`; "
        f"redefine this hierarchy with `ostler template edit {name} --set <kind>.<field>=<value>`.",
        _MARKER_END.format(name=name),
    ]
    return "\n".join(lines) + "\n"


def _inject_claude_md(root: Path, name: str, title: str, kinds: list[TemplateKind]) -> Path:
    path = root / "CLAUDE.md"
    section = _claude_section(name, title, kinds)
    start, end = _MARKER_START.format(name=name), _MARKER_END.format(name=name)
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if pattern.search(existing):
        updated = pattern.sub(section, existing)
    elif existing and not existing.endswith("\n"):
        updated = existing + "\n\n" + section
    elif existing:
        updated = existing + "\n" + section
    else:
        updated = section
    path.write_text(updated, encoding="utf-8")
    return path


def apply(root: Path, name: str) -> Result:
    data = dynamic_registry.load_raw(root)
    tmpl = data.get(name)
    if not isinstance(tmpl, dict):
        return Result(False, f"no template '{name}'")
    kinds = _parsed_kinds(name, tmpl)
    if not kinds:
        return Result(False, f"template '{name}' has no kinds")

    made_dirs: dict[str, Path] = {}
    for k in kinds:
        made_dirs.setdefault(k.doc_root, root / k.default_path)
    paths = []
    for d in made_dirs.values():
        d.mkdir(parents=True, exist_ok=True)
        paths.append(d)

    title = str(tmpl.get("title", name))
    claude_md = _inject_claude_md(root, name, title, kinds)
    paths.append(claude_md)
    return Result(True, f"applied template '{name}' ({len(made_dirs)} dir(s) scaffolded)", paths)
