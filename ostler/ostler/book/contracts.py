"""The calls a contract file lists: the rpcs of a `.proto` and the operations of an OpenAPI document."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
HOLES = re.compile(r"\{[^}]*\}")
SERVICE = re.compile(r"\bservice\s+(\w+)\s*\{")
PACKAGE = re.compile(r"\bpackage\s+([\w.]+)\s*;")
STREAMING = {"answer": "streams its answer", "request": "streams its request", "both": "streams its request and its answer"}
RPC = re.compile(r"\brpc\s+(\w+)\s*\(\s*(stream\s+)?[\w.]+\s*\)\s*returns\s*\(\s*(stream\s+)?[\w.]+\s*\)")


def rpc_of(endpoint: type) -> str:
    return str(getattr(endpoint, "rpc", ""))


@dataclass(frozen=True)
class Call:
    """One call a contract lists. `name` is how the book declares it, `key` is what an ignore pattern
    names after `::`, and `kind` is `""`, `"answer"`, `"request"` or `"both"`."""

    name: str
    key: str
    kind: str = ""
    prefixes: tuple[str, ...] = field(default=(), compare=False)

    def matches(self, method: str, path: str) -> bool:
        verb, _, route = self.name.partition(" ")
        if verb != method.upper():
            return False
        want = HOLES.sub("{}", path)
        return any(want == HOLES.sub("{}", prefix.rstrip("/") + route) for prefix in ("", *self.prefixes))


def blanked(text: str) -> str:
    """The text without comments and with each string literal emptied."""
    out: list[str] = []
    i = 0
    while i < len(text):
        two = text[i : i + 2]
        if two == "//":
            while i < len(text) and text[i] != "\n":
                i += 1
        elif two == "/*":
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            out.append(" ")
        elif text[i] in "\"'":
            quote = text[i]
            i += 1
            while i < len(text) and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append('""')
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def body_of(text: str, start: int) -> str:
    depth = 1
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if not depth:
            return text[start:i]
    return text[start:]


def proto_services(text: str) -> list[str]:
    """The `package.Service` names a proto declares."""
    clean = blanked(text)
    package = PACKAGE.search(clean)
    prefix = f"{package.group(1)}." if package else ""
    return [prefix + m.group(1) for m in SERVICE.finditer(clean)]


def proto_calls(text: str) -> list[Call]:
    clean = blanked(text)
    package = PACKAGE.search(clean)
    prefix = f"{package.group(1)}." if package else ""
    found: list[Call] = []
    for service in SERVICE.finditer(clean):
        for rpc in RPC.finditer(body_of(clean, service.end())):
            kind = "both" if rpc.group(2) and rpc.group(3) else "request" if rpc.group(2) else "answer" if rpc.group(3) else ""
            found.append(Call(f"{prefix}{service.group(1)}/{rpc.group(1)}", rpc.group(1), kind))
    return found


def is_openapi(text: str) -> bool:
    if "openapi" not in text and "swagger" not in text:
        return False
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    return isinstance(document, dict) and ("openapi" in document or "swagger" in document)


def openapi_calls(text: str) -> list[Call]:
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        return []
    prefixes = [str(document["basePath"]).rstrip("/")] if document.get("basePath") else []
    for server in document.get("servers") or []:
        route = re.sub(r"^\w+://[^/]*", "", str(server.get("url", ""))) if isinstance(server, dict) else ""
        if route.rstrip("/"):
            prefixes.append(route.rstrip("/"))
    found: list[Call] = []
    paths = document.get("paths")
    for path, item in (paths.items() if isinstance(paths, dict) else ()):
        for method in METHODS:
            if isinstance(item, dict) and method in item:
                found.append(Call(f"{method.upper()} {path}", f"{method.upper()} {path}", prefixes=tuple(prefixes)))
    return found


def parse(path: str, text: str) -> list[Call]:
    return proto_calls(text) if path.endswith(".proto") else openapi_calls(text)
