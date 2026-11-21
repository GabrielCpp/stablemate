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
from ostler.book.bookdiff import BookDiff, book_diff
from ostler.book.change import Reading, change_in, parent_of
from ostler.book.played import carriers
from ostler.book.reach import arrivals
from ostler.book.service import Service
from ostler.book.mentions import Mentions, same_symbol
from ostler.book.sources import changed_in_tree, changed_parts, file_of, git, head_of, ignored, sourced, story_commits, traced_in, verified_at
from ostler.book.touching import touches

NONE, EMPTY, PARTIAL, WHOLE = "none", "empty", "partial", "whole"
UNJUDGED_CAP = 50
DIRECT_CAP = 20
NOT_JUDGED_CAP = 20
CAUSE_CAP = 3

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
    whole: bool = False
    reason: str = ""
    only: list[str] = field(default_factory=list)
    journeys: list[str] = field(default_factory=list)
    by_journey: list[str] = field(default_factory=list)
    direct_journeys: list[str] = field(default_factory=list)
    direct_only: list[str] = field(default_factory=list)
    reached: dict[str, Any] = field(default_factory=lambda: {"calls": 0, "journeys": 0, "causes": []})
    diff: dict[str, Any] = field(default_factory=dict)
    chains: list[Chain] = field(default_factory=list)
    uncovered: list[dict[str, str]] = field(default_factory=list)
    unplayed: list[dict[str, str]] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    fallbacks: list[dict[str, str]] = field(default_factory=list)
    widened: list[dict[str, Any]] = field(default_factory=list)
    mapped: list[str] = field(default_factory=list)
    unused: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    story: str = ""
    commits: list[str] = field(default_factory=list)
    owed: list[str] = field(default_factory=list)
    not_computed: list[str] = field(default_factory=lambda: list(NOT_COMPUTED))

    def command(self, module: str) -> str:
        if self.plan == NONE:
            return "nothing to play"
        if self.plan == EMPTY:
            return "nothing to play: the changed files select no play"
        runs = []
        if self.direct_journeys:
            runs.append(f"ostler book run {module} --partial {' '.join(f'--journey {t!r}' for t in self.direct_journeys)}")
        if self.direct_only:
            runs.append(f"ostler book run {module} --only {','.join(self.direct_only)}")
        if runs:
            return "\n".join(runs)
        if self.plan == WHOLE:
            return f"ostler book run {module}"
        runs = [f"ostler book run {module} --only {','.join(self.only)}"] if self.only else []
        if self.by_journey:
            runs.append(f"ostler book run {module} --partial {' '.join(f'--journey {t!r}' for t in self.by_journey)}")
        return "\n".join(runs) or "nothing mapped to a play"


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
    """The calls whose plays an element's change can alter, an empty set where no call reaches it, or None where the book cannot narrow them."""
    if kind in ("record", "event"):
        return None
    if kind == "action":
        direct, outside = carriers(service, element.__name__)
        return {*direct, *outside}
    if kind == "screen":
        return {i.__name__ for i in service.interactions if i.screen is element} | {i.__name__ for i in arrivals(service, cast(Any, element))}
    return {element.__name__}


def short_of(app_root: str, *revs: str) -> list[str]:
    return [git(app_root, "rev-parse", "--short", rev).strip() for rev in revs]


def short_parent(app_root: str, commit: str) -> str:
    parent = parent_of(app_root, commit)
    try:
        return short_of(app_root, parent)[0]
    except subprocess.CalledProcessError:
        return parent[:7]


def walk(service: Service[Any], app_root: str, reading: Reading, head: str, book: Path | None = None, module: str = "") -> Affected:
    assert service.app is not None
    app = service.app
    change = change_in(app_root, reading, app.roots)
    tracked, untracked = sorted(change.spans), change.untracked
    held, loose = changed_in_tree(app_root, "HEAD", service.app.roots)
    if reading.story:
        base = reading.since or (short_parent(app_root, change.commits[0]) if change.commits else "")
    else:
        base = reading.base
    found = Affected(service.name, base, head, dirty=bool(held or loose))
    if reading.story:
        found.story = reading.story
        found.commits = short_of(app_root, *change.commits)
    owned = book_diff(service, book, module, reading) if book is not None else BookDiff()
    direct: set[str] = set()
    named: dict[str, list[Pointer]] = {}
    everything = pointers(service, app_root)
    for pointer in everything:
        named.setdefault(pointer.path, []).append(pointer)
    journeys: dict[str, list[str]] = {}
    called: set[str] = set()
    titled: set[str] = set()
    ranked_journeys: list[str] = []
    ranked_calls: dict[int, list[str]] = {2: [], 3: []}
    caused: dict[str, tuple[set[str], set[str]]] = {}

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

    def chain(path: str, function: str, element: Pointer, because: str = "", via: str = "direct", rank: int = 0, cause: str = "") -> None:
        if element.kind == "journey":
            title = cast(Any, element.element).title()
            titled.add(title)
            direct.add(title)
            if rank:
                ranked_journeys.append(title)
            else:
                caused.setdefault(cause, (set(), set()))[1].add(title)
            found.chains.append(Chain(path, function, element.element.__name__, element.kind, [title], via))
            return
        calls = calls_of(service, element.element, element.kind)
        name = element.element.__name__
        followed = element.kind == "record" and via != "direct"
        if calls is None and not followed:
            why = because or (f"record {name} changed" if element.kind == "record" else f"{element.kind} {name} reaches no call of the book")
            fall(path, f"{why}: the whole book")
        if calls is not None and not calls and not any(u["element"] == name and u["kind"] == element.kind for u in found.unplayed):
            found.unplayed.append({"element": name, "kind": element.kind, "path": path})
        wanted = sorted(calls or ())
        called.update(wanted)
        titles = list(dict.fromkeys(t for c in wanted for t in journeys_of(c)))
        titled.update(titles)
        plays = [*wanted, *titles]
        if rank:
            ranked_calls[rank].extend(wanted)
        else:
            reached_calls, reached_titles = caused.setdefault(cause, (set(), set()))
            reached_calls.update(wanted)
            reached_titles.update(titles)
        found.chains.append(Chain(path, function, name, element.kind, plays, via))

    order = {p.element: i for i, p in reversed(list(enumerate(everything)))}
    mentions: list[Mentions] = []

    def hits_of(path: str, function: str) -> dict[type, tuple[Pointer, str]]:
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
            span = change.spans[path]
            functions, unattributed, imports = changed_parts(app_root, span.old, path, tree=span.new is None, until=span.new, dotted=True, types=True)
        if imports:
            found.imports.append(path)
        if not (functions or unattributed or imports):
            unattributed = [[]]
        for function in sorted(functions):
            hits = hits_of(path, function)
            if not hits:
                found.uncovered.append({"path": path, "function": function})
            for element, (pointer, via) in sorted(hits.items(), key=lambda item: order[item[0]]):
                chain(path, function, pointer, via=via, rank=3 if via == "direct" else 0, cause="" if via == "direct" else f"{path}::{function}")
        if unattributed:
            if not namers:
                found.uncovered.append({"path": path, "function": ""})
                continue
            widen(path, "a changed hunk has no definition line: every element naming the file is affected", namers)
            for element in {p.element: p for p in namers}.values():
                chain(path, "", element, f"record {element.element.__name__} names the file and a changed hunk has no definition line", rank=3)
    for hit in owned.hits:
        if hit.element is None:
            fall(hit.path, hit.why)
        else:
            rank = 0 if hit.used else 1 if hit.kind == "journey" else 2
            cause = f"book {hit.path}:{hit.used}" if hit.used else ""
            chain(f"book {hit.path}", hit.name, Pointer(hit.element, hit.kind, hit.path, None), rank=rank, cause=cause)
    left = {u["path"] for u in found.uncovered}
    found.mapped = sorted({*(c.path for c in found.chains if not c.path.startswith("book ")), *found.imports} - left)
    unjudged = sorted({*owned.unjudged, *outside_roots(app_root, reading, [*tracked, *untracked], book, owned)})
    found.diff = {"app_files": len({*tracked, *untracked}), "book_files": len(owned.files),
                  "not_computed": {"count": len(unjudged), "paths": unjudged[:UNJUDGED_CAP]}}
    found.not_computed += owned.notes
    found.unused = owned.unused
    if found.fallbacks:
        found.plan = WHOLE
    elif found.uncovered or called or direct:
        found.plan = PARTIAL
    elif found.chains or unjudged or owned.files:
        found.plan = EMPTY
    else:
        found.plan = NONE
    found.whole = found.plan == WHOLE
    found.owed = list(dict.fromkeys(f["why"] for f in found.fallbacks))
    found.reason = "; ".join(found.owed)
    found.only = sorted(called)
    found.journeys = [j.title() for j in service.journeys if j.title() in titled]
    by_calls = {t for c in called for t in journeys_of(c)}
    found.by_journey = [t for t in found.journeys if t in direct and t not in by_calls]
    found.direct_journeys = list(dict.fromkeys(ranked_journeys))
    found.direct_only = list(dict.fromkeys([*ranked_calls[2], *ranked_calls[3]]))
    named_calls = set(found.direct_only)
    played = {*found.direct_journeys, *(t for c in found.direct_only for t in journeys_of(c))}
    causes: list[dict[str, Any]] = [{"cause": k, "calls": len(c - named_calls), "journeys": len(t - played)} for k, (c, t) in caused.items()]
    found.reached = {"calls": len(set(found.only) - named_calls),
                     "journeys": len([t for t in found.journeys if t not in played]),
                     "causes": sorted((c for c in causes if c["calls"] or c["journeys"]), key=lambda c: (-c["calls"], -c["journeys"], c["cause"]))}
    return found


def outside_roots(app_root: str, reading: Reading, inside: list[str], book: Path | None, owned: BookDiff) -> list[str]:
    """The changed files of the app's repository that sit under no root and are not the book's own."""
    change = change_in(app_root, reading, (".",))
    tracked, untracked = sorted(change.spans), change.untracked
    held = {os.path.normpath(os.path.join(app_root, p)) for p in inside}
    own = {os.path.normpath(os.path.join(str(book), p)) for p in owned.files} if book is not None else set()
    return [p for p in sorted({*tracked, *untracked}) if os.path.normpath(os.path.join(app_root, p)) not in held | own]


def capped(names: list[str], cap: int) -> str:
    return ", ".join(names[:cap]) + (f", and {len(names) - cap} more" if len(names) > cap else "")


def header(found: Affected, module: str) -> str:
    named = f"story {found.story}, {len(found.commits)} commit{'s' if len(found.commits) != 1 else ''}, {found.commits[0]} to {found.commits[-1]}" if found.story and found.commits else f"{found.base}..{found.head}"
    return f"affected {module}: {named}" + (" and the uncommitted work" if found.dirty else "")


def reached_line(found: Affected) -> str:
    r = found.reached
    line = f"reached beyond that: {r['calls']} calls, {r['journeys']} journeys"
    if r["causes"]:
        line += "; top causes: " + ", ".join(f"{c['cause']} ({c['calls']} calls, {c['journeys']} journeys)" for c in r["causes"][:CAUSE_CAP])
    return line


def show(found: Affected, module: str) -> list[str]:
    lines = [header(found, module),
             f"plan: {found.plan}" + (f", {sum(found.diff[k] for k in ('app_files', 'book_files')) + found.diff['not_computed']['count']} changed files select no play" if found.plan == EMPTY else "")]
    lines.append(f"direct journeys ({len(found.direct_journeys)}): {capped(found.direct_journeys, DIRECT_CAP)}" if found.direct_journeys else "direct journeys: none")
    lines.append(f"direct calls ({len(found.direct_only)}): {capped(found.direct_only, DIRECT_CAP)}" if found.direct_only else "direct calls: none")
    lines.append(reached_line(found))
    if found.fallbacks:
        more = len(found.owed) - 1
        lines.append(f"owed to a whole play ({len(found.owed)}): {found.owed[0]}" + (f", and {more} more, listed under fallbacks" if more > 0 else ""))
    lines.append(f"changed: {found.diff['app_files']} app files, {found.diff['book_files']} book files, {found.diff['not_computed']['count']} not judged")
    lines.append(f"calls ({len(found.only)}): {capped(found.only, DIRECT_CAP)}" if found.only else "calls: none")
    lines.append(f"journeys ({len(found.journeys)}): {capped(found.journeys, DIRECT_CAP)}" if found.journeys else "journeys: none")
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
        unplayed = {(u["element"], u["kind"]) for u in found.unplayed}
        for c in found.chains:
            lines.append(f"  {c.path}{(':' if c.path.startswith('book ') else '::') + c.function if c.function else ' (file)'} -> {c.element} ({c.kind}, {c.via}) -> {', '.join(c.plays) or ('no play of its own' if c.kind == 'record' and c.via != 'direct' else 'no play reaches it' if (c.element, c.kind) in unplayed else 'the whole book')}")
    if found.unused:
        lines += ["changed and used by nothing:", *(f"  {u}" for u in found.unused)]
    if found.uncovered:
        lines += ["uncovered (no element names them; judge them by hand):",
                  *(f"  {u['path']}{'::' + u['function'] if u['function'] else ''}" for u in found.uncovered)]
    if found.unplayed:
        lines += ["unplayed (the book states them and no play reaches them):", *(f"  {u['kind']} {u['element']}" for u in found.unplayed)]
    lines.append("not computed: " + "; ".join(found.not_computed))
    paths = found.diff["not_computed"]["paths"]
    if paths:
        lines += ["not judged (outside every root, or not Python in the book):", *(f"  {p}" for p in paths[:NOT_JUDGED_CAP])]
        if found.diff["not_computed"]["count"] > NOT_JUDGED_CAP:
            lines.append(f"  and {found.diff['not_computed']['count'] - NOT_JUDGED_CAP} more")
    return lines


def book_root_of(package_dir: str, module: str) -> Path | None:
    here = Path(package_dir).resolve()
    parts = module.split(".")
    return here.parents[len(parts) - 1] if len(parts) >= 2 and len(here.parents) > len(parts) - 1 else None


def cmd_affected(service: Service[Any], module: str, app_root: str, since: str | None, package_dir: str, out: str, story: str | None = None) -> int:
    if service.app is None:
        print(f"{service.name} declares no app")
        return 2
    verified = since or (None if story else verified_at(service, package_dir))
    if verified is None and not story:
        print("not verified: give --since <commit>, or write the commit with 'verified'")
        return 2
    try:
        if story:
            bound = git(app_root, "rev-parse", "--short", since).strip() if since else None
            if not story_commits(app_root, story, bound):
                print(f"no commit reachable from HEAD{f' after {bound}' if bound else ''} in {app_root} carries the trailer 'Story: {story}'")
                return 2
            reading = Reading(story=story, since=bound)
        else:
            reading = Reading(base=git(app_root, "rev-parse", "--short", str(verified)).strip())
        found = walk(service, app_root, reading, head_of(app_root), book_root_of(package_dir, module), module)
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
    return 1 if found.uncovered or found.plan == EMPTY else 0
