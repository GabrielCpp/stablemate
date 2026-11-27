"""The functions of an app that put a message on a transport, found from the app's own call graph: every
function under the book's roots whose calls reach an EventBridge, SNS, SQS, Kinesis or Firehose send, through
the app's shared packages and its libraries alike. Whatever the message is, a protobuf, a struct or a map, the
send is what makes it an event the service puts out."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler.book.service import Service

CALLGRAPH = "golang.org/x/tools/cmd/callgraph@v0.53.0"
FORMAT = "{{.Caller}}\t{{.Callee}}\t{{.Description}}\t{{.Filename}}"
TRANSPORT = re.compile(
    r"github\.com/aws/aws-sdk-go(?:-v2)?/service/(?:eventbridge|sns|sqs|kinesis|firehose)\.(?:Client|EventBridge|SNS|SQS|Kinesis|Firehose)\)"
    r"\.(?:PutEvents|Publish|PublishBatch|SendMessage|SendMessageBatch|PutRecord|PutRecords|PutRecordBatch)(?:WithContext)?$"
)
CLOSURE = re.compile(r"\$\d+(?:\$\d+)*")
METHOD = re.compile(r"^\(\*?(?P<package>[^()]+)\.(?P<type>\w+)(?:\[.*\])?\)\.(?P<name>\w+)$")
FUNCTION = re.compile(r"^(?P<package>[^()\[]+)\.(?P<name>\w+)(?:\[.*\])?$")


@dataclass(frozen=True)
class Publish:
    path: str
    symbol: str
    via: str

    @property
    def name(self) -> str:
        return self.symbol.rsplit(".", 1)[-1]


@dataclass
class Publishes:
    found: list[Publish] = field(default_factory=list)
    unread: str = ""


def module_of(app_root: str) -> str | None:
    try:
        text = Path(app_root, "go.mod").read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.search(r"^module\s+(\S+)", text, re.M)
    return found.group(1) if found else None


def split(node: str) -> tuple[str, str] | None:
    """The package and the `Type.method` or function name of a call-graph node."""
    method = METHOD.match(node)
    if method:
        return method["package"], f"{method['type']}.{method['name']}"
    function = FUNCTION.match(node)
    return (function["package"], function["name"]) if function else None


def under(package: str, module: str, roots: tuple[str, ...]) -> bool:
    if not package.startswith(module + "/"):
        return False
    folder = package.removeprefix(module + "/")
    return any(folder == root.rstrip("/") or folder.startswith(root.rstrip("/") + "/") for root in roots)


def short(node: str, module: str) -> str:
    return node.replace(module + "/", "")


def edges(lines: list[str]) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Caller to callees, with a closure folded into the function that defines it and calls through a function
    value left out: a function value carries no type that says where it goes, so following it joins every callback
    to every caller of the library that runs it."""
    out: dict[str, set[str]] = defaultdict(set)
    where: dict[str, str] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 4 or "dynamic function call" in parts[2]:
            continue
        caller, callee = CLOSURE.sub("", parts[0]), CLOSURE.sub("", parts[1])
        where.setdefault(caller, parts[3])
        if caller != callee:
            out[caller].add(callee)
    return out, where


def reaching(out: dict[str, set[str]]) -> set[str]:
    back: dict[str, set[str]] = defaultdict(set)
    for caller, callees in out.items():
        for callee in callees:
            back[callee].add(caller)
    found = {node for node in back if TRANSPORT.search(node)}
    stack = list(found)
    while stack:
        for caller in back[stack.pop()]:
            if caller not in found:
                found.add(caller)
                stack.append(caller)
    return found


def frontier(lines: list[str], module: str, roots: tuple[str, ...], app_root: str) -> list[Publish]:
    """Each function under the roots that calls, outside the roots, something that reaches a transport."""
    out, where = edges(lines)
    reach = reaching(out)
    found: list[Publish] = []
    for caller in sorted(reach):
        parts = split(caller)
        if parts is None or not under(parts[0], module, roots):
            continue
        outside = sorted(c for c in out[caller] if c in reach and not under((split(c) or ("", ""))[0], module, roots))
        if outside:
            path = os.path.relpath(where.get(caller, ""), app_root) if where.get(caller) else parts[0].removeprefix(module + "/")
            found.append(Publish(path, parts[1], short(outside[0], module)))
    return found


def cache_file(app_root: str, roots: tuple[str, ...]) -> Path | None:
    head = subprocess.run(["git", "-C", app_root, "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", app_root, "status", "--porcelain", "--", "*.go", "go.mod", "go.sum"], capture_output=True, text=True)
    if head.returncode != 0 or dirty.stdout.strip():
        return None
    key = hashlib.sha256("\n".join([CALLGRAPH, head.stdout.strip(), *roots]).encode()).hexdigest()[:24]
    return Path(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")) / "ostler" / "publishes" / f"{key}.tsv"


def call_graph(app_root: str, roots: tuple[str, ...]) -> tuple[list[str], str]:
    cached = cache_file(app_root, roots)
    if cached is not None and cached.exists():
        return cached.read_text(encoding="utf-8").splitlines(), ""
    go = shutil.which("go")
    if go is None:
        return [], "go is not on PATH, so the app's call graph was not read: install Go to list what it publishes"
    packages = [f"./{root.strip('/')}/..." for root in roots]
    done = subprocess.run([go, "run", CALLGRAPH, "-algo=vta", f"-format={FORMAT}", *packages], cwd=app_root, capture_output=True, text=True)
    if done.returncode != 0:
        tail = "\n".join(done.stderr.strip().splitlines()[-5:])
        return [], f"the app's call graph could not be built ({' '.join(packages)}):\n{tail}"
    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(done.stdout, encoding="utf-8")
    return done.stdout.splitlines(), ""


def publishes(app_root: str, roots: tuple[str, ...]) -> Publishes:
    module = module_of(app_root)
    if module is None:
        return Publishes()
    go_roots = tuple(r for r in roots if any(Path(app_root, r).rglob("*.go")))
    if not go_roots:
        return Publishes()
    lines, unread = call_graph(app_root, go_roots)
    return Publishes(unread=unread) if unread else Publishes(frontier(lines, module, go_roots, app_root))


def emitted_by(service: Service[Any]) -> set[tuple[str, str]]:
    """The `(file, name)` of every pointer an action that emits names in its source."""
    from ostler.book.sources import actions, file_of, symbol_of

    named: set[tuple[str, str]] = set()
    for action in actions(service):
        if getattr(action, "emits", ()):
            for pointer in getattr(action, "source", ()):
                symbol = symbol_of(pointer)
                if symbol:
                    named.add((file_of(pointer), symbol))
    return named


def unemitted(service: Service[Any], app_root: str) -> Publishes:
    """The publishing functions no action that emits names, and no ignore pattern leaves out."""
    from ostler.book.sources import ignored

    assert service.app is not None
    found = publishes(app_root, service.app.roots)
    named = emitted_by(service)
    left = [p for p in found.found if (p.path, p.name) not in named and not ignored(f"{p.path}::{p.symbol}", service.app.ignore)
            and not ignored(f"{p.path}::{p.name}", service.app.ignore) and not ignored(p.path, service.app.ignore)]
    return Publishes(left, found.unread)


def untapped(service: Service[Any]) -> list[str]:
    """The events the book's actions emit when no environment names a delivery that taps them."""
    from ostler.book.sources import actions

    emitted = [f"{event.name} ({action.__name__})" for action in actions(service) for event in getattr(action, "emits", ())]
    environments = getattr(service, "environments", {}) or {}
    if not emitted or any(getattr(env, "delivery", None) is not None for env in environments.values()):
        return []
    return emitted
