"""Which symbols of an app mention which, read from its source text alone.

Each defined symbol (function, method, type, constant, variable) has an extent, the lines of its definition, and a
symbol mentions another when the other's bare name is a whole identifier in that extent. Matching is by name, so two
symbols that share a bare name are both followed. A file whose extents cannot be read with confidence is one unit."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass

from ostler.book.sources import BLOCK_OPEN, NOT_NAMES, TYPES, defined, entry_of, git, ignored, read

SOURCE = (".go", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".svelte")
TESTS = re.compile(r"_test\.go$|(?:^|/)test_[^/]*\.py$|_test\.py$|\.(?:test|spec)\.[jt]sx?$|(?:^|/)(?:tests?|__tests__)/")
WORD = re.compile(r"\w+")
STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`[^`]*`")
CLOSER = re.compile(r"^[)}\]]+[;,]?$")
CONTINUES = ("=", "|", "&", "=>")
NOT_CALLS = {"return", "await", "new", "throw", "yield", "typeof", "delete", "void", "else", "case"}


def same_symbol(changed: str, pointed: str) -> bool:
    """Whether a changed symbol is the one a pointer names. Where both give their type, the whole name must be
    equal, so `Service.Get` is not `Server.Get`; where either gives none, the last name decides."""
    if changed == pointed:
        return True
    if "." in changed and "." in pointed:
        return False
    return changed.rsplit(".", 1)[-1] == pointed.rsplit(".", 1)[-1]


@dataclass(frozen=True)
class Node:
    path: str
    name: str
    is_type: bool = False

    @property
    def bare(self) -> str:
        return self.name.rsplit(".", 1)[-1]


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def balance(line: str, hash_comments: bool = False) -> int:
    bare = STRING.sub('""', line)
    bare = re.sub(r"#.*$" if hash_comments else r"//.*$", "", bare)
    return sum(bare.count(c) for c in "({[") - sum(bare.count(c) for c in ")}]")


def definitions(path: str, lines: list[str]) -> list[tuple[int, str]]:
    go = path.endswith(".go")
    python = path.endswith(".py")
    found: list[tuple[int, str]] = []
    state: str | None = None
    for i, line in enumerate(lines):
        name: str | None
        if go:
            opened = BLOCK_OPEN.match(line)
            if opened:
                state = opened.group(1)
                continue
            if line.startswith(")"):
                state = None
                continue
            if state == "import":
                continue
            if state:
                name = entry_of(line)
            elif line[:1] in ("", " ", "\t"):
                continue
            else:
                name = defined(line, dotted=True, types=True)
        else:
            name = defined(line, types=True)
            if name is None and not python and line[:1] in (" ", "\t") and line.rstrip().endswith("{"):
                loose = defined(line, loose=True, types=True)
                if loose and loose not in NOT_NAMES and line.split()[0] not in NOT_CALLS:
                    name = loose
        if name and name not in NOT_NAMES:
            found.append((i, name))
    return found


def declares_type(line: str, name: str) -> bool:
    for pattern in TYPES:
        m = pattern.match(line)
        if m:
            return m.group(1) == name
    return False


def extent_end(lines: list[str], start: int, python: bool) -> int | None:
    """The last line of the definition that starts at `start`, or None where it never closes."""
    indent = indent_of(lines[start])
    depth = balance(lines[start], python)
    if python:
        end = start
        for j in range(start + 1, len(lines)):
            line = lines[j]
            if depth > 0:
                depth += balance(line, True)
                end = j
            elif not line.strip():
                continue
            elif indent_of(line) <= indent:
                break
            else:
                end = j
        return end
    if depth <= 0 and not lines[start].rstrip().endswith(CONTINUES):
        return start
    for j in range(start + 1, len(lines)):
        if indent_of(lines[j]) == indent and CLOSER.match(lines[j].strip()):
            return j
    return None


class Mentions:
    """The mention map of one app, built once from the working tree."""

    def __init__(self, app_root: str, roots: tuple[str, ...], ignore: tuple[str, ...]) -> None:
        self.nodes: list[Node] = []
        self.by_path: dict[str, list[int]] = {}
        self.by_word: dict[str, list[int]] = {}
        listed = git(app_root, "ls-files", "--cached", "--others", "--exclude-standard", "--", *roots).splitlines()
        for path in sorted(set(listed)):
            if path.endswith(SOURCE) and not ignored(path, ignore) and not TESTS.search(path):
                self.add(path, read(app_root, path).splitlines())

    def add(self, path: str, lines: list[str]) -> None:
        python = path.endswith(".py")
        defs = definitions(path, lines)
        ends = [extent_end(lines, i, python) for i, _ in defs]
        words = [frozenset(WORD.findall(line)) for line in lines]
        unreadable = any(e is None for e in ends) or (not python and sum(balance(line) for line in lines) != 0)
        masked = list(words)
        extents: list[frozenset[str]] = []
        for i, name in defs:
            bare = name.rsplit(".", 1)[-1]
            masked[i] = frozenset(WORD.findall(re.sub(rf"\b{re.escape(bare)}\b", "", lines[i], count=1)))
        for (i, _), end in zip(defs, ends):
            last = i if end is None else end
            extents.append(frozenset().union(masked[i], *words[i + 1:last + 1]))
        every = frozenset().union(*words)
        entries = [(name, every if unreadable else extent) for (_, name), extent in zip(defs, extents)]
        entries.append(("", every if unreadable else frozenset().union(*masked)))
        kinds = [False if unreadable else declares_type(lines[i], name) for i, name in defs] + [False]
        for (name, mentioned), is_type in zip(entries, kinds):
            index = len(self.nodes)
            self.nodes.append(Node(path, name, is_type))
            self.by_path.setdefault(path, []).append(index)
            for word in mentioned:
                self.by_word.setdefault(word, []).append(index)

    def closure(self, path: str, symbol: str) -> dict[int, str]:
        """The nodes a change to `symbol` of `path` reaches, each with the symbol it was reached through, empty
        for the changed symbol itself."""
        reached: dict[int, str] = {}
        for index in self.by_path.get(path, ()):
            node = self.nodes[index]
            if node.name and same_symbol(symbol, node.name):
                reached[index] = ""
        bare = symbol.rsplit(".", 1)[-1]
        queue = deque([(bare, symbol)])
        done = {bare}
        while queue:
            word, label = queue.popleft()
            for index in self.by_word.get(word, ()):
                node = self.nodes[index]
                if index in reached or node.is_type:
                    continue
                reached[index] = label
                if node.name and node.bare not in done:
                    done.add(node.bare)
                    queue.append((node.bare, node.name))
        return reached
