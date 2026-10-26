"""The services and RPCs a folder of `.proto` files declares, read without a protobuf dependency."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PACKAGE = re.compile(r"\bpackage\s+([\w.]+)\s*;")
_SERVICE = re.compile(r"\bservice\s+(\w+)\s*\{")
_RPC = re.compile(
    r"\brpc\s+(\w+)\s*\(\s*(stream\s+)?([\w.]+)\s*\)\s*returns\s*\(\s*(stream\s+)?([\w.]+)\s*\)\s*([;{])")


@dataclass(frozen=True)
class Rpc:
    """One method of a service, with the message names as the file writes them."""

    name: str
    request: str
    response: str
    client_streaming: bool
    server_streaming: bool
    service: str = ""

    @property
    def full_name(self) -> str:
        """`package.Service/Method`, the name a gRPC call carries."""
        return f"{self.service}/{self.name}"


@dataclass(frozen=True)
class Service:
    """A service by its package-qualified name, with its RPCs in file order."""

    name: str
    rpcs: tuple[Rpc, ...]


@dataclass(frozen=True)
class Contract:
    """Every service the proto files under a folder declare, sorted by name."""

    services: tuple[Service, ...]

    def service(self, full_name: str) -> Service | None:
        """The service called *full_name*, or `None` when the contract has none."""
        return next((s for s in self.services if s.name == full_name), None)


def _strip_comments(text: str) -> str:
    """*text* with `//` and `/* */` comments blanked, string literals left whole."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            out.append(" ")
            i = n if j < 0 else j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _block_end(text: str, open_at: int) -> int:
    """The index just past the brace that closes the one at *open_at*, or `len(text)` when none does."""
    depth, i, n = 0, open_at, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            i = j
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _rpcs(body: str, service: str) -> list[Rpc]:
    out: list[Rpc] = []
    i = 0
    while (m := _RPC.search(body, i)) is not None:
        out.append(Rpc(m.group(1), m.group(3), m.group(5), m.group(2) is not None,
                       m.group(4) is not None, service))
        i = _block_end(body, m.end() - 1) if m.group(6) == "{" else m.end()
    return out


def _read_file(text: str) -> list[Service]:
    text = _strip_comments(text)
    package = _PACKAGE.search(text)
    prefix = f"{package.group(1)}." if package else ""
    out: list[Service] = []
    i = 0
    while (m := _SERVICE.search(text, i)) is not None:
        end = _block_end(text, m.end() - 1)
        name = f"{prefix}{m.group(1)}"
        out.append(Service(name, tuple(_rpcs(text[m.end():end], name))))
        i = end
    return out


def read_contract(folder: Path) -> Contract:
    """Every service declared by the `*.proto` files under *folder*; unreadable files are skipped."""
    services: list[Service] = []
    try:
        files = sorted(folder.rglob("*.proto"))
    except OSError:
        files = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        services.extend(_read_file(text))
    return Contract(tuple(sorted(services, key=lambda s: s.name)))
