"""The decisions a service settled, one markdown file each under `decisions/` beside the
service. The file names the Python elements it explains; the Python never names the file."""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from typing import Any

from ostler.book.service import Service
from ostler.book.sources import kinds

HEADER = ("story", "date", "elements", "sources")
SEARCHED = ("story", "elements", "sources")
MODEL_MODULES = ("rules", "lifecycle", "cast")


@dataclass(frozen=True)
class Decision:
    slug: str
    story: str
    date: str
    elements: tuple[str, ...]
    body: str
    path: str
    offset: int = 0
    sources: tuple[str, ...] = ()
    header: tuple[tuple[int, str], ...] = ()

    def first(self) -> str:
        text = " ".join(self.body.split())
        match = re.search(r"[.!?](\s|$)", text)
        return text[:match.start() + 1] if match else text

    def line(self) -> str:
        return f"{self.slug} (story {self.story}, {self.date}): {self.first()}"

    def lines(self) -> list[tuple[int, str]]:
        return [(self.offset + n, text) for n, text in enumerate(self.body.splitlines(), 1)]

    def searchable(self) -> list[tuple[int, str]]:
        return [*self.header, *self.lines()]


def folder(module: str) -> str:
    return os.path.dirname(importlib.import_module(module).__file__ or "")


def directory(module: str) -> str:
    return os.path.join(folder(module), "decisions")


def shared(module: str) -> str | None:
    """The package a surface-split book keeps above its surfaces, holding the model and no `service.py`. Its
    `decisions/` and `QUESTIONS.md` belong to every surface. None for a book of one surface."""
    if "." not in module:
        return None
    above = os.path.dirname(folder(module))
    if os.path.isfile(os.path.join(above, "service.py")) or not os.path.isdir(os.path.join(above, "model")):
        return None
    return module.rsplit(".", 1)[0]


def folders(module: str) -> list[str]:
    """Where a surface reads its decisions and questions: its own folder, then the book's shared root."""
    return [folder(module), *([os.path.dirname(folder(module))] if shared(module) else [])]


def surfaces(module: str) -> list[str]:
    """Every surface of the book `module` is one surface of, itself included."""
    root = shared(module)
    if root is None:
        return [module]
    above = os.path.dirname(folder(module))
    return [f"{root}.{name}" for name in sorted(os.listdir(above))
            if os.path.isfile(os.path.join(above, name, "service.py"))]


def read_page(path: str, searched: tuple[str, ...]) -> tuple[dict[str, str], tuple[tuple[int, str], ...], str, int]:
    """A page's header fields, its searched header lines, its body and the line the body starts on."""
    with open(path) as f:
        rows = f.read().splitlines()
    fields: dict[str, str] = {}
    header: list[tuple[int, str]] = []
    n = 0
    while n < len(rows) and rows[n].strip():
        key, _, value = rows[n].partition(":")
        fields[key.strip()] = value.strip()
        if key.strip() in searched:
            header.append((n + 1, f"{key.strip()}: {value.strip()}"))
        n += 1
    return fields, tuple(header), "\n".join(rows[n + 1:]).strip("\n"), n + 1


def parse(path: str) -> Decision:
    fields, header, body, offset = read_page(path, SEARCHED)
    elements = tuple(e.strip() for e in fields.get("elements", "").split(",") if e.strip())
    sources = tuple(e.strip() for e in fields.get("sources", "").split(",") if e.strip())
    return Decision(os.path.basename(path).removesuffix(".md"), fields.get("story", ""), fields.get("date", ""),
                    elements, body, path, offset, sources, header)


def load(module: str) -> list[Decision]:
    found: list[Decision] = []
    for place in folders(module):
        root = os.path.join(place, "decisions")
        if os.path.isdir(root):
            found += [parse(os.path.join(root, name)) for name in sorted(os.listdir(root)) if name.endswith(".md")]
    return found


def is_shared(decision: Decision, module: str) -> bool:
    """Whether the decision sits in the book's shared root rather than in the surface's own folder."""
    return os.path.dirname(os.path.dirname(decision.path)) != folder(module)


def model_names(module: str) -> dict[str, str]:
    found: dict[str, str] = {}
    root = shared(module)
    for book in (module, *([root] if root else [])):
        for sub in MODEL_MODULES:
            try:
                loaded = importlib.import_module(f"{book}.model.{sub}")
            except ModuleNotFoundError:
                continue
            for name in vars(loaded):
                if not name.startswith("_"):
                    found.setdefault(name, f"model.{sub}")
    return found


def resolve(service: Service[Any], module: str) -> dict[str, str]:
    """Each name a decision may cite, and where it lives: an endpoint, record, screen, interaction,
    journey or action of the service, or a module-level name of the model's rules, lifecycle or
    cast modules. These are the names `explain` finds, plus the records and model names."""
    from ostler.book.search import actions_of

    found = model_names(module)
    found.update({r.__name__: "record" for r in service.records})
    found.update({a.__name__: "action" for a in actions_of(service, module)})
    found.update({e.__name__: "endpoint" for e in service.endpoints})
    found.update({i.__name__: "interaction" for i in service.interactions})
    found.update({j.__name__: "journey" for j in service.journeys})
    found.update({s.__name__: "screen" for s in service.screens})
    return found


def resolve_book(service: Service[Any], module: str) -> dict[str, str]:
    """The names a decision or question in the book's shared root may cite: those of every surface of the book."""
    found = resolve(service, module)
    for other in surfaces(module):
        if other != module:
            found = {**resolve(importlib.import_module(f"{other}.service").service, other), **found}
    return found


def naming(decisions: list[Decision], element: str) -> list[Decision]:
    return [d for d in decisions if element in d.elements]


def select(decisions: list[Decision], story: str | None = None, element: str | None = None) -> list[Decision]:
    return [d for d in decisions if (story is None or d.story == story) and (element is None or element in d.elements)]


def unexplained(service: Service[Any], module: str, kind: str | None = None) -> list[str]:
    named = {e for d in load(module) for e in d.elements}
    return [e.__name__ for k, e in kinds(service) if kind in (None, k) and e.__name__ not in named]


def cmd_decisions(service: Service[Any], args: Any) -> int:
    if args.unexplained:
        print("\n".join(unexplained(service, args.service, args.kind)))
        return 0
    for d in select(load(args.service), args.story, args.element):
        print(d.line())
    return 0
