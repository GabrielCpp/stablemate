"""`ostler book affected`: the plays a code change calls for, read from the diff and the book alone.

The walk has three steps. The diff gives the changed paths and the symbols in them, committed or not. The mention
map of the source gives every symbol that mentions a changed one, and the `source=` pointers of the book give the
elements that name any of them. The elements give the calls and journeys to play. Every changed path lands in
exactly one of mapped, uncovered or ignored, and every place the walk could not narrow is named. A hunk with no
symbol stays a widened list. A fallback, where the book cannot name a list at all, makes the plan the whole book."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from ostler._vendor.stablemate_core import config as core_config
from ostler.book.played import carriers
from ostler.book.service import Service
from ostler.book.mentions import Mentions, same_symbol
from ostler.book.sources import changed_parts, changed_in_tree, file_of, git, head_of, ignored, sourced, traced_in, verified_at
from ostler.book.touching import touches

NONE, PARTIAL, WHOLE = "none", "partial", "whole"

NOT_COMPUTED = (
    "dependent books: the gateways, web apps and services that call or read this book",
    "configuration: environment variables, feature flags, secrets",
    "data: migrations, seeded or reference data",
    "code in other repositories: pointers written as repo://<member>/<path>",
)


@dataclass(frozen=True)
class Pointer:
    element: type
    kind: str
    path: str
    symbol: str | None


@dataclass
class Chain:
    path: str
    function: str
    element: str
    kind: str
    plays: list[str]
    via: str = "direct"


@dataclass
class Affected:
    service: str
    base: str
    head: str
    dirty: bool
    plan: str = NONE
    only: list[str] = field(default_factory=list)
    journeys: list[str] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)
    uncovered: list[dict[str, str]] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    fallbacks: list[dict[str, str]] = field(default_factory=list)
    widened: list[dict[str, Any]] = field(default_factory=list)
    mapped: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    not_computed: list[str] = field(default_factory=lambda: list(NOT_COMPUTED))

    def command(self, module: str) -> str:
        if self.plan == NONE:
            return "nothing to play"
        if self.plan == WHOLE:
            return f"ostler book run {module}"
        if not self.only:
            return "nothing mapped to a play"
        return f"ostler book run {module} --only {','.join(self.only)}"


def pointers(service: Service[Any], app_root: str) -> list[Pointer]:
    member = core_config.repository_name(Path(app_root))
    found: list[Pointer] = []
    for kind, element in sourced(service):
        for pointer in cast(Any, element).source:
            traced = traced_in(pointer, member)
            if traced is not None:
                found.append(Pointer(element, kind, file_of(traced), traced.split("::", 1)[1] if "::" in traced else None))
    return found


def calls_of(service: Service[Any], element: type, kind: str) -> set[str] | None:
    """The calls whose plays an element's change can alter, or None where the book cannot narrow them."""
    if kind == "record":
        return None
    if kind == "action":
        direct, outside = carriers(service, element.__name__)
        return {*direct, *outside} or None
    if kind == "screen":
        return {i.__name__ for i in service.interactions if i.screen is element} or None
    return {element.__name__}


def walk(service: Service[Any], app_root: str, base: str, head: str) -> Affected:
    assert service.app is not None
    app = service.app
    tracked, untracked = changed_in_tree(app_root, base, app.roots)
    held, loose = changed_in_tree(app_root, "HEAD", service.app.roots)
    found = Affected(service.name, base, head, dirty=bool(held or loose))
    named: dict[str, list[Pointer]] = {}
    everything = pointers(service, app_root)
    for pointer in everything:
        named.setdefault(pointer.path, []).append(pointer)
    journeys: dict[str, list[str]] = {}
    called: set[str] = set()
    titled: set[str] = set()

    def journeys_of(call: str) -> list[str]:
        if call not in journeys:
            journeys[call] = [j.title() for j in service.journeys if touches(service, j, frozenset({call}))]
        return journeys[call]

    def fall(path: str, why: str) -> None:
        if {"path": path, "why": why} not in found.fallbacks:
            found.fallbacks.append({"path": path, "why": why})

    def widen(path: str, why: str, targets: list[Pointer]) -> None:
        elements = sorted({p.element.__name__ for p in targets})
        for entry in found.widened:
            if entry["path"] == path and entry["why"] == why:
                entry["elements"] = sorted({*entry["elements"], *elements})
                return
        found.widened.append({"path": path, "why": why, "elements": elements})

    def chain(path: str, function: str, element: Pointer, because: str = "", via: str = "direct") -> None:
        calls = calls_of(service, element.element, element.kind)
        name = element.element.__name__
        followed = element.kind == "record" and via != "direct"
        if calls is None and not followed:
            why = because or (f"record {name} changed" if element.kind == "record" else f"{element.kind} {name} reaches no call of the book")
            fall(path, f"{why}: the whole book")
        wanted = sorted(calls or ())
        called.update(wanted)
        titles = list(dict.fromkeys(t for c in wanted for t in journeys_of(c)))
        titled.update(titles)
        plays = [*wanted, *titles]
        found.chains.append(Chain(path, function, name, element.kind, plays, via))

    order = {p.element: i for i, p in reversed(list(enumerate(everything)))}
    mentions: list[Mentions] = []

    def reached(path: str, function: str) -> dict[type, tuple[Pointer, str]]:
        if not mentions:
            mentions.append(Mentions(app_root, app.roots, app.ignore))
        found_in = mentions[0].closure(path, function)
        hits: dict[type, tuple[Pointer, str]] = {}
        for p in named.get(path, []):
            if p.symbol is None or same_symbol(function, p.symbol):
                hits[p.element] = (p, "direct")
        for index, label in found_in.items():
            node = mentions[0].nodes[index]
            for p in named.get(node.path, []):
                if p.element not in hits and (p.symbol is None or (node.name and same_symbol(node.name, p.symbol))):
                    hits[p.element] = (p, f"through {label}" if label else "direct")
        return hits

    for path in sorted({*tracked, *untracked}):
        if ignored(path, service.app.ignore):
            found.ignored.append(path)
            continue
        namers = named.get(path, [])
        if path in untracked:
            functions, unattributed, imports = set(), [[]], False
        else:
            functions, unattributed, imports = changed_parts(app_root, base, path, tree=True, dotted=True, types=True)
        if imports:
            found.imports.append(path)
        if not (functions or unattributed or imports):
            unattributed = [[]]
        for function in sorted(functions):
            hits = reached(path, function)
            if not hits:
                found.uncovered.append({"path": path, "function": function})
            for element, (pointer, via) in sorted(hits.items(), key=lambda item: order[item[0]]):
                chain(path, function, pointer, via=via)
        if unattributed:
            if not namers:
                found.uncovered.append({"path": path, "function": ""})
                continue
            widen(path, "a changed hunk has no definition line: every element naming the file is affected", namers)
            for element in {p.element: p for p in namers}.values():
                chain(path, "", element, f"record {element.element.__name__} names the file and a changed hunk has no definition line")
    left = {u["path"] for u in found.uncovered}
    found.mapped = sorted({*(c.path for c in found.chains), *found.imports} - left)
    if not (found.chains or found.uncovered):
        found.plan = NONE
    elif found.fallbacks:
        found.plan = WHOLE
    else:
        found.plan = PARTIAL
    found.only = sorted(called)
    found.journeys = [j.title() for j in service.journeys if j.title() in titled]
    return found


def show(found: Affected, module: str) -> list[str]:
    lines = [f"affected {module}: {found.base}..{found.head}" + (" and the uncommitted work" if found.dirty else ""),
             f"plan: {found.plan}"]
    if found.ignored:
        lines += [f"ignored ({len(found.ignored)}):", *(f"  {p}" for p in found.ignored)]
    if found.fallbacks:
        lines += ["fallbacks:", *(f"  {f['path']}: {f['why']}" for f in found.fallbacks)]
    if found.widened:
        lines.append("widened:")
        for w in found.widened:
            lines.append(f"  {w['path']}: {w['why']}: {', '.join(w['elements'])}")
    if found.imports:
        lines += ["imports (only import lines changed, nothing to play):", *(f"  {p}" for p in found.imports)]
    if found.chains:
        lines.append("chains:")
        for c in found.chains:
            lines.append(f"  {c.path}{'::' + c.function if c.function else ' (file)'} -> {c.element} ({c.kind}, {c.via}) -> {', '.join(c.plays) or ('no play of its own' if c.kind == 'record' and c.via != 'direct' else 'the whole book')}")
    if found.uncovered:
        lines += ["uncovered (no element names them; judge them by hand):",
                  *(f"  {u['path']}{'::' + u['function'] if u['function'] else ''}" for u in found.uncovered)]
    lines.append("not computed: " + "; ".join(found.not_computed))
    return lines


def cmd_affected(service: Service[Any], module: str, app_root: str, since: str | None, package_dir: str, out: str) -> int:
    if service.app is None:
        print(f"{service.name} declares no app")
        return 2
    verified = since or verified_at(service, package_dir)
    if verified is None:
        print("not verified: give --since <commit>, or write the commit with 'verified'")
        return 2
    try:
        base = git(app_root, "rev-parse", "--short", verified).strip()
        found = walk(service, app_root, base, head_of(app_root))
    except subprocess.CalledProcessError as wrong:
        print(f"git could not read {app_root} from {verified}: {(wrong.stderr or '').strip()}")
        return 2
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{service.name}-affected.json")
    with open(path, "w") as f:
        json.dump(asdict(found), f, indent=2)
        f.write("\n")
    for line in show(found, module):
        print(line)
    print(f"written: {path}")
    print(found.command(module))
    return 1 if found.uncovered else 0
