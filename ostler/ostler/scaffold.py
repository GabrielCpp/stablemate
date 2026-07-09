"""`ostler scaffold` — hierarchy-respecting creation of UI-profile nodes (§9).

Two shapes, both driven by the per-type ``UINodeType`` spec in ``registry.py``:

* **file-level** (`screen`/`cli`/`server`/`concept`/`format`/`flow`) — a whole ``.md`` placed in
  the type's context folder under its service (``ostler scaffold screen changes-view --service
  groom`` → ``docs/features/groom/gui/screens/changes-view.md``), emitting the frontmatter, the
  file's own bullet stubs, and its ``required_sections`` skeleton.
* **section-level** (`component`/`interaction`/`endpoint`/`command`/`invocation`) — a ``### id``
  inserted under its ``## Heading`` inside an existing surface doc (creating the heading if absent),
  with the ordered ``bullet_keys`` stubs: ``ostler scaffold interaction click-file --in
  gui/screens/changes-view.md``.

The output is already canonical (frontmatter + bullet order match ``ostler fmt``), so scaffolding is
the deterministic remedy for the ``missing-*`` / ``unresolved-*`` linter errors: the agent respects
the §4 layout *by construction* instead of inferring it.
"""

from __future__ import annotations

from pathlib import Path

from . import crud, markdown, registry
from .crud import Result
from .model import Graph


def _bullet_stubs(uitype: registry.UINodeType) -> list[str]:
    return [f"- {bk.key}:" for bk in uitype.bullet_keys]


def _file_body(uitype: registry.UINodeType, title: str) -> str:
    lines = [f"# {title}", ""]
    stubs = _bullet_stubs(uitype)
    if stubs:
        lines += [*stubs, ""]
    for heading in uitype.required_sections:
        lines += [f"## {heading}", ""]
    return "\n".join(lines) + "\n"


def _resolve_in_file(graph: Graph, in_file: str) -> Path:
    candidate = Path(in_file)
    if candidate.is_absolute():
        return candidate
    if (graph.root / in_file).exists():
        return graph.root / in_file
    return graph.doc_roots["features"] / in_file


def _scaffold_file(graph: Graph, uitype: registry.UINodeType, name: str,
                   service: str | None, title: str) -> Result:
    if not service:
        return Result(False, f"file-level type '{uitype.name}' requires --service")
    if "/" in name or name in (".", ".."):
        return Result(False, f"invalid name '{name}'")
    froot = graph.doc_roots["features"]
    rel = Path(service)
    if uitype.context:
        rel = rel / uitype.context
    path = froot / rel / f"{name}.md"
    if path.exists():
        return Result(False, f"{uitype.name} '{name}' already exists at "
                             f"{path.relative_to(graph.root).as_posix()}")
    fm = {"type": uitype.name, "slug": name, "title": title}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{crud.dump_frontmatter(fm)}---\n{_file_body(uitype, title)}",
                    encoding="utf-8")
    return Result(True, f"scaffolded {uitype.name} '{name}' -> "
                        f"{path.relative_to(graph.root).as_posix()}", [path])


def _scaffold_section(graph: Graph, uitype: registry.UINodeType, name: str,
                      in_file: str | None) -> Result:
    if not in_file:
        return Result(False, f"section-level type '{uitype.name}' requires --in <surface-doc>")
    path = _resolve_in_file(graph, in_file)
    if not path.is_file():
        return Result(False, f"no such surface doc: {in_file}")
    doc = markdown.split(path.read_text(encoding="utf-8"))
    section = doc.find_section(uitype.heading)
    if section is not None and any(c.title.strip() == name for c in section.children):
        return Result(False, f"{uitype.name} '{name}' already exists in "
                             f"{path.relative_to(graph.root).as_posix()}")
    block = [f"### {name}", *_bullet_stubs(uitype), ""]
    crud._insert_subsection(doc, uitype.heading, block)
    path.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"scaffolded {uitype.name} '{name}' under ## {uitype.heading} in "
                        f"{path.relative_to(graph.root).as_posix()}", [path])


def scaffold(graph: Graph, type_name: str, name: str, *, service: str | None = None,
             in_file: str | None = None, title: str | None = None) -> Result:
    uitype = registry.ui_type(type_name)
    if uitype is None:
        return Result(False, f"'{type_name}' is not a UI-profile type "
                             f"(one of {', '.join(registry.UI_TYPES_BY_NAME)})")
    if uitype.kind == "file":
        return _scaffold_file(graph, uitype, name, service, title or name)
    return _scaffold_section(graph, uitype, name, in_file)
