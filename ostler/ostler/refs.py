"""The ref grammars this package mints and reads, in one place."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ostler.markdown import leading_code_spans

_DIGEST_SUFFIX = re.compile(r"@([0-9a-f]{12})$")


@dataclass(frozen=True, slots=True)
class CodeRef:
    """A code citation, optionally qualified by its repository and/or stamped with a digest."""

    repository: str
    path: str
    symbol: str = ""
    digest: str | None = None


def parse_code_ref(value: str) -> CodeRef:
    """Parse a legacy or repository-qualified code reference, with an optional ``@digest``."""
    digest = None
    digest_match = _DIGEST_SUFFIX.search(value)
    if digest_match:
        digest = digest_match.group(1)
        value = value[: digest_match.start()]
    target, separator, symbol = value.partition("::")
    repository = ""
    path = target
    if target.startswith("repo://"):
        repository, slash, path = target.removeprefix("repo://").partition("/")
        if not slash or not repository or not path:
            msg = f"malformed repository-qualified code ref: {value!r}"
            raise ValueError(msg)
    return CodeRef(
        repository=repository,
        path=path.replace("\\", "/"),
        symbol=symbol if separator else "",
        digest=digest,
    )


def render_code_ref(ref: CodeRef) -> str:
    """Render a code reference in its canonical legacy or qualified form."""
    path = ref.path.replace("\\", "/")
    if ref.repository:
        if not path:
            msg = "malformed repository-qualified code ref: path must not be empty"
            raise ValueError(msg)
        target = f"repo://{ref.repository}/{path}"
    else:
        target = path
    rendered = f"{target}::{ref.symbol}" if ref.symbol else target
    return f"{rendered}@{ref.digest}" if ref.digest else rendered


TEST_DIRS = frozenset({"__tests__", "mocks", "test", "tests"})
TEST_SUFFIXES = (
    "_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py", "Test.php",
)
TEST_PREFIXES = ("test_",)
TEST_FILES = ("conftest.py",)


def is_test_source(path: str) -> bool:
    """Whether a repo-relative source path is a test, a test double or a test fixture file."""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    return (bool(TEST_DIRS.intersection(parts[:-1])) or name.endswith(TEST_SUFFIXES)
            or name.startswith(TEST_PREFIXES) or name in TEST_FILES)


def normalize_ref(value: str) -> str:
    """Strip the decoration a single ``code:`` target may carry (backticks, commas, space)."""
    return value.strip().strip("`, ").strip()


def bare_targets(value: str) -> list[tuple[str, int, int]]:
    """Split *value* on commas into targets, each as ``(text, start, end)`` into *value*."""
    out: list[tuple[str, int, int]] = []
    start = 0
    for chunk in value.split(","):
        out.append((chunk, start, start + len(chunk)))
        start += len(chunk) + 1
    return out


def code_refs(value: Any) -> list[str]:
    """Every target a ``code:`` bullet cites, normalized and de-duplicated in order."""
    raw: list[str]
    if isinstance(value, list):
        raw = [str(item) for item in value]
    elif value:
        raw = [str(value)]
    else:
        return []

    out: list[str] = []
    for item in raw:
        parts = leading_code_spans(item) or [text for text, _, _ in bare_targets(item)]
        for part in parts:
            normalized = normalize_ref(part)
            if not normalized:
                continue
            try:
                normalized = render_code_ref(parse_code_ref(normalized))
            except ValueError:
                pass
            out.append(normalized)
    return list(dict.fromkeys(out))


def bullet_ref(node_id: str, key: str, index: int | None = None) -> str:
    """The address a finding names: a node, the bullet key, and *which* occurrence of it."""
    anchor = f"{node_id}#{key}"
    return anchor if index is None else f"{anchor}:{index}"


def collision_ref(node_id: str, collision: Mapping[str, Any]) -> str:
    """The address of *one collision a node takes part in*, not of the node."""
    others = "+".join(sorted(o.rpartition("#")[2] for o in collision["nodes"] if o != node_id))
    parts = [collision["screen"], collision["role"], collision["name"] or "", others]
    return f"{node_id}#" + ":".join(parts)


def strip_digest(ref: str) -> str:
    """A citation's identity with any stamped ``@digest`` dropped, rendered back canonically."""
    try:
        return render_code_ref(replace(parse_code_ref(ref), digest=None))
    except ValueError:
        return ref


def ref_path(ref: str) -> str:
    """The file part of a normalized ``path::symbol`` ref (the whole ref when it has none)."""
    try:
        return parse_code_ref(ref).path
    except ValueError:
        return ref.partition("::")[0]


__all__ = [
    "CodeRef",
    "TEST_DIRS",
    "bare_targets",
    "bullet_ref",
    "code_refs",
    "collision_ref",
    "is_test_source",
    "normalize_ref",
    "parse_code_ref",
    "ref_path",
    "render_code_ref",
    "strip_digest",
]
