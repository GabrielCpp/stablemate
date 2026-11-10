"""The decisions a service settled, one markdown file each under `decisions/` beside the
service. The file names the Python elements it explains; the Python never names the file."""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from typing import Any

from ostler.book.service import Service

HEADER = ("story", "date", "elements")
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

    def first(self) -> str:
        text = " ".join(self.body.split())
        match = re.search(r"[.!?](\s|$)", text)
        return text[:match.start() + 1] if match else text

    def line(self) -> str:
        return f"{self.slug} (story {self.story}, {self.date}): {self.first()}"

    def lines(self) -> list[tuple[int, str]]:
        return [(self.offset + n, text) for n, text in enumerate(self.body.splitlines(), 1)]


def directory(module: str) -> str:
    return os.path.join(os.path.dirname(importlib.import_module(module).__file__ or ""), "decisions")


def parse(path: str) -> Decision:
    with open(path) as f:
        rows = f.read().splitlines()
    fields: dict[str, str] = {}
    n = 0
    while n < len(rows) and rows[n].strip():
        key, _, value = rows[n].partition(":")
        fields[key.strip()] = value.strip()
        n += 1
    body = "\n".join(rows[n + 1:]).strip("\n")
    elements = tuple(e.strip() for e in fields.get("elements", "").split(",") if e.strip())
    return Decision(os.path.basename(path).removesuffix(".md"), fields.get("story", ""), fields.get("date", ""),
                    elements, body, path, n + 1)


def load(module: str) -> list[Decision]:
    root = directory(module)
    if not os.path.isdir(root):
        return []
    return [parse(os.path.join(root, name)) for name in sorted(os.listdir(root)) if name.endswith(".md")]


def model_names(module: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for sub in MODEL_MODULES:
        try:
            loaded = importlib.import_module(f"{module}.model.{sub}")
        except ModuleNotFoundError:
            continue
        for name in vars(loaded):
            if not name.startswith("_"):
                found.setdefault(name, f"model.{sub}")
    return found


def resolve(service: Service[Any], module: str) -> dict[str, str]:
    """Each name a decision may cite, and where it lives: an endpoint of the service, one of
    its records, or a module-level name of the model's rules, lifecycle or cast modules."""
    found = model_names(module)
    found.update({r.__name__: "record" for r in service.records})
    found.update({e.__name__: "endpoint" for e in service.endpoints})
    return found


def naming(decisions: list[Decision], element: str) -> list[Decision]:
    return [d for d in decisions if element in d.elements]


def select(decisions: list[Decision], story: str | None = None, element: str | None = None) -> list[Decision]:
    return [d for d in decisions if (story is None or d.story == story) and (element is None or element in d.elements)]


def cmd_decisions(service: Service[Any], args: Any) -> int:
    for d in select(load(args.service), args.story, args.element):
        print(d.line())
    return 0
