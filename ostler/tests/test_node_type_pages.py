"""The 17 node-type documentation pages joined back to `registry.declared_keys`.

These pages, not `registry.py`, are the copy a book author actually reads. Nothing joins them
to the registry today, so a key the registry starts recognizing can go undocumented on the page
that teaches it, and a page can keep teaching a key the registry has stopped recognizing —
either way silently, since no test reads both sides.

Two joins:

(i) the fenced key list under `bullet-grammar.md`'s "Keys that are normative on every type"
    heading against `registry.SHARED_NORMATIVE_KEYS` — the shared vocabulary's own single
    point of truth on the page side.
(ii) the fenced key list under `bullet-grammar.md`'s "Relation keys are legal on every type"
     heading against `registry.RELATION_KEYS`.
(iii) each node-type page's bullet-key table against `registry.declared_keys(type)`, minus the
      set that page is allowed to leave undocumented because `bullet-grammar.md` documents it
      centrally instead — a containment, not an equality, because relation keys are legal on
      every type and a page may document one whether or not that type's profile lists it.

Both exemption sets are parsed out of `bullet-grammar.md` itself, never hardcoded here: the
reason a key may be absent from a node-type page is literally "it is documented on the shared
page", so the exemption has to evaporate on its own the day someone deletes the section that
grants it, rather than silently outliving its justification. Joins (i) and (ii) are what keep
those parsed sets from drifting away from the registry they stand for.
"""

from __future__ import annotations

import re

from pathlib import Path

from ostler import registry

REFERENCES = (Path(__file__).resolve().parents[2]
              / "base-library/library/skills/ostler/okf/references")


def _bullet_grammar_text() -> str:
    """`bullet-grammar.md`'s own text, read from the **library source** under `base-library/`,
    never the `.claude/` copy `make agent-install` generates from it: a test that read the
    generated mirror would pass on a tree whose source had already drifted and only fail after
    somebody remembered to regenerate.
    """
    return (REFERENCES / "bullet-grammar.md").read_text()


def _fenced_shared_keys(text: str) -> set[str]:
    """The comma-separated key names inside the fenced block under "Keys that are normative on
    every type" — the page's own copy of `registry.SHARED_NORMATIVE_KEYS`.
    """
    [block] = re.findall(
        r"## Keys that are normative on every type\n\n.*?```\n(.*?)\n```", text, re.S)
    return {key.strip() for key in re.split(r"[,\n]", block) if key.strip()}


def _fenced_relation_keys(text: str) -> set[str]:
    """The comma-separated key names inside the fenced block under "Relation keys are legal on
    every type" — the page's own copy of `registry.RELATION_KEYS`.
    """
    [block] = re.findall(
        r"## Relation keys are legal on every type\n\n.*?```\n(.*?)\n```", text, re.S)
    return {key.strip() for key in re.split(r"[,\n]", block) if key.strip()}


def _per_key_section_keys(text: str) -> set[str]:
    """Every key with its own `## \\`key\\`` section — the shape `unspecified:` and
    `known-defect:` are documented in, prose rather than a table row on any node-type page.
    """
    return set(re.findall(r"^## `([a-z-]+)`", text, re.M))


def _node_type_page_keys(node_type: str) -> set[str]:
    """The backtick-quoted keys in the first column of `node_type`'s bullet-key table.

    Every page but `fixture.md` spells the cell `` `key` ``; `fixture.md` spells it `` `key:` ``,
    trailing colon included — the one page whose table has a different column shape from the
    rest. The trailing colon is optional here so that shape difference does not read as a
    missing key.
    """
    path = REFERENCES / "node-types" / f"{node_type}.md"
    return set(re.findall(r"^\|\s*`([a-z-]+):?`\s*\|", path.read_text(), re.M))


def test_the_shared_fenced_block_lists_every_shared_normative_key() -> None:
    """`bullet-grammar.md`'s fenced list and `registry.SHARED_NORMATIVE_KEYS` must name the
    same eight keys. Neither side is allowed to lead: a key added to the registry and not the
    page would leave every node-type page silently free to skip documenting it, and a key added
    to the page and not the registry would teach an author a key nothing actually recognizes.
    """
    parsed = _fenced_shared_keys(_bullet_grammar_text())
    assert parsed, "the shared-normative-keys fenced block parsed no keys at all"
    assert parsed == set(registry.SHARED_NORMATIVE_KEYS)


def test_the_relation_key_fenced_block_lists_every_relation_key() -> None:
    """`bullet-grammar.md`'s relation-key list and `registry.RELATION_KEYS` must name the same
    set. The list is what licenses a node-type page to carry a row for a key its own profile
    does not declare, so a key on the page and not in the registry would license a row for a
    bullet nothing reads, and a key in the registry and not on the page would make the join
    below reject a row that is in fact correct.
    """
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
    """Every node-type page's bullet-key table carries a row for every key `declared_keys` makes
    load-bearing on that type, and carries no row for anything else except a relation key.

    A key is only set aside for a type if that type's own profile does not also declare it
    itself: `endpoint`/`invocation` both declare `emits`/`consumes` on their own profile (with a
    note that they are normative only via the shared set), and both pages document that nuance
    with their own row — so those two rows stay required even though the *key itself* is also
    documented on the shared page. Subtracting the shared set unconditionally would let a page
    silently drop a row it is still supposed to carry.

    Relation keys are the one permitted extra, and the asymmetry is the registry's, not this
    test's: they work on every type (`LOAD_BEARING_KEYS` subtracts them, so `unknown-bullet`
    never fires on one), while `declared_keys` lists them per type only where that profile
    happened to name them — `detail` on `endpoint`, five of them on `component`. Requiring set
    equality would forbid a page from documenting a key that genuinely works there. Permitting
    *any* undeclared key instead would be no test at all, and `unknown_bullet_keys` cannot serve
    as the predicate either: it returns `[]` for a wholly invented key as readily as for a
    relation key, so a page teaching a meaningless bullet would pass.

    A key missing here is a bullet an author can type into a book that no page on the shelf
    told them existed.
    """
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
