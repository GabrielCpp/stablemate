"""The 17 node-type documentation pages joined back to `registry.declared_keys`."""

from __future__ import annotations

import re

from pathlib import Path

from ostler import registry

REFERENCES = (Path(__file__).resolve().parents[2]
              / "base-library/library/skills/ostler/okf/references")


def _bullet_grammar_text() -> str:
    """`bullet-grammar.md`'s own text, read from the **library source** under `base-library/`, never the `.claude/` copy `make agent-install` generates from it: a test that read the generated mirror would pass on a tree whose source had already drifted and only fail after somebody remembered to regenerate."""
    return (REFERENCES / "bullet-grammar.md").read_text()


def _fenced_shared_keys(text: str) -> set[str]:
    """The comma-separated key names inside the fenced block under "Keys that are normative on every type" — the page's own copy of `registry.SHARED_NORMATIVE_KEYS`."""
    [block] = re.findall(
        r"## Keys that are normative on every type\n\n.*?```\n(.*?)\n```", text, re.S)
    return {key.strip() for key in re.split(r"[,\n]", block) if key.strip()}


def _fenced_relation_keys(text: str) -> set[str]:
    """The comma-separated key names inside the fenced block under "Relation keys are legal on every type" — the page's own copy of `registry.RELATION_KEYS`."""
    [block] = re.findall(
        r"## Relation keys are legal on every type\n\n.*?```\n(.*?)\n```", text, re.S)
    return {key.strip() for key in re.split(r"[,\n]", block) if key.strip()}


def _per_key_section_keys(text: str) -> set[str]:
    """Every key with its own `## \\`key\\`` section — the shape `unspecified:` and
    `known-defect:` are documented in, prose rather than a table row on any node-type page.
    """
    return set(re.findall(r"^## `([a-z-]+)`", text, re.M))


def _node_type_page_keys(node_type: str) -> set[str]:
    """The backtick-quoted keys in the first column of `node_type`'s bullet-key table."""
    path = REFERENCES / "node-types" / f"{node_type}.md"
    return set(re.findall(r"^\|\s*`([a-z-]+):?`\s*\|", path.read_text(), re.M))


def test_the_shared_fenced_block_lists_every_shared_normative_key() -> None:
    """`bullet-grammar.md`'s fenced list and `registry.SHARED_NORMATIVE_KEYS` must name the same eight keys."""
    parsed = _fenced_shared_keys(_bullet_grammar_text())
    assert parsed, "the shared-normative-keys fenced block parsed no keys at all"
    assert parsed == set(registry.SHARED_NORMATIVE_KEYS)


def test_the_relation_key_fenced_block_lists_every_relation_key() -> None:
    """`bullet-grammar.md`'s relation-key list and `registry.RELATION_KEYS` must name the same set."""
    parsed = _fenced_relation_keys(_bullet_grammar_text())
    assert parsed, "the relation-keys fenced block parsed no keys at all"
    assert parsed == set(registry.RELATION_KEYS)


def _node_types() -> list[str]:
    return [t.name for t in registry.UI_TYPES if t.name != "untyped"]


def _centrally_documented_keys() -> tuple[set[str], set[str]]:
    text = _bullet_grammar_text()
    shared = _fenced_shared_keys(text)
    per_key = _per_key_section_keys(text)
    assert shared, "the shared-normative-keys fenced block parsed no keys at all"
    assert per_key, "no per-key `## `key`` sections were found on bullet-grammar.md"
    return shared, per_key


def test_every_node_type_page_lists_every_key_the_registry_declares() -> None:
    """Every node-type page's bullet-key table carries a row for every key `declared_keys` makes load-bearing on that type, and carries no row for anything else except a relation key."""
    shared, per_key = _centrally_documented_keys()
    exempt = shared | per_key
    relation = _fenced_relation_keys(_bullet_grammar_text())

    failures = []
    for node_type in _node_types():
        own_keys = {b.key for b in registry.UI_TYPES_BY_NAME[node_type].bullet_keys}
        required = registry.declared_keys(node_type) - ((exempt | relation) - own_keys)
        parsed = _node_type_page_keys(node_type)
        assert parsed, f"the `{node_type}` node-type page's table parsed no keys at all"
        missing = sorted(required - parsed)
        undocumentable = sorted(parsed - required - relation - exempt)
        if missing or undocumentable:
            failures.append(
                f"`{node_type}`: missing {missing}, documents-nothing {undocumentable}")
    assert not failures, "\n".join(failures)
