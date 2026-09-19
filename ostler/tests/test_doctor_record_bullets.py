"""A `record=True` key holds one thing with named properties, and doctor reads its children.

The three container grammars differ in what a *child* is: `nested` alone makes every descendant
a claim, `entries` makes a direct child a thing that has claims, and `record` makes a direct
child a named property of the one thing the key states. `response:` on an endpoint is the third
shape, and under the first its `- media:`/`- body:` children flattened into strings that still
carried their own `key:` prefix, unread by anything. See `BulletKey` (registry.py),
`_records_from_bullets` (model.py) and `_check_record_properties` (doctor.py).
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, registry
from ostler.model import UINode, load

from conftest import write

ENDPOINT_PATH = "docs/features/acme/server.md"


def _endpoint_book(*response_children: str) -> str:
    body = "\n".join(f"  - {child}" for child in response_children)
    return f"""---
type: server
title: Acme accounts
---
# Acme accounts

## Endpoints

### list-accounts
- method: GET
- path: /api/accounts
- response:
{body}
- authorization: an adjuster reads every account on file.
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _endpoint(repo: Path) -> UINode:
    return next(n for n in load(repo).ui_nodes if n.type == "endpoint")


def test_a_records_children_are_read_as_named_properties(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book("media: `application/json`", "body: `{}`"))
    assert _endpoint(repo).records == {
        "response": {"media": "`application/json`", "body": "`{}`"}}


def test_a_body_carrying_colons_stays_one_property(repo: Path) -> None:
    """The delimiter occurs inside the text it delimits, which is why the fold is backtick-aware.

    This is the shape that made the flatten unrecoverable: splitting `"body: {\"a\": 1}"` back
    into a key and a value has to pick a colon, and every JSON body a book writes there has
    several.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book('body: `{"seats": [{"id": str}]}`'))
    assert _endpoint(repo).records["response"] == {
        "body": '`{"seats": [{"id": str}]}`'}


def test_meta_still_holds_the_flat_subtree(repo: Path) -> None:
    """Declaring the key changes nothing `meta` said, so no existing reader moves under it."""
    write(repo / ENDPOINT_PATH, _endpoint_book("media: `application/json`"))
    assert _endpoint(repo).meta["response"] == "media: `application/json`"


def test_a_property_spelled_like_a_bullet_key_is_reported(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book("media: `application/json`", "status: 200 OK"))
    found = _findings(repo, "misnested-bullet")
    assert [(f.severity, f.ref) for f in found] == [("error", "response:status")]
    assert "`status:`" in found[0].message
    assert found[0].suggestion is not None and "- status:" in found[0].suggestion


def test_an_aliased_bullet_key_is_reported_too(repo: Path) -> None:
    """`error:` is a second spelling of `errors:`, so nesting it loses the same claim."""
    write(repo / ENDPOINT_PATH, _endpoint_book("error: 404 when no such account"))
    assert [f.ref for f in _findings(repo, "misnested-bullet")] == ["response:error"]


def test_a_property_spelled_like_no_bullet_key_is_never_misnested(repo: Path) -> None:
    """`misnested-bullet` fires only for a child spelled like a node bullet key.

    `schema` matches no bullet key of `endpoint`, so nesting it under `response:` cannot be read
    as stealing a claim from the node — that reading is `unknown-record-property`'s job now that
    `response:` declares a vocabulary (see the tests below), not this arm's.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book("media: `application/json`", "schema: AccountList"))
    assert _findings(repo, "misnested-bullet") == []


def test_a_property_outside_the_declared_vocabulary_is_reported(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book("media: `application/json`", "schema: AccountList"))
    found = _findings(repo, "unknown-record-property")
    assert [(f.severity, f.ref) for f in found] == [("error", "response:schema")]
    assert "`schema:`" in found[0].message
    assert found[0].suggestion is not None and "media:" in found[0].suggestion


def test_each_declared_property_is_clean(repo: Path) -> None:
    for child in ("media: `application/json`", "body: `{}`", "notes: idempotent",
                  "field: `ok`; type boolean; required"):
        write(repo / ENDPOINT_PATH, _endpoint_book(child))
        assert _findings(repo, "unknown-record-property") == []


def test_a_property_repeated_under_one_record_is_clean(repo: Path) -> None:
    """A response describes its body one field per bullet, so `field:` occurs many times.

    The value of a repeated property is a list rather than a string, and this arm reads the
    property *names*, so the shape a real book writes has to be clean here for the vocabulary
    to be usable at all — a check that admitted `field:` once and reported the second one would
    hold every schema-bearing response in error.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book(
        "media: `application/json`",
        "field: `ok`; type boolean; required",
        "field: `count`; type integer; required"))
    assert _findings(repo, "unknown-record-property") == []
    assert _endpoint(repo).records["response"]["field"] == [
        "`ok`; type boolean; required", "`count`; type integer; required"]


def test_a_property_spelled_like_a_bullet_key_is_not_also_unknown(repo: Path) -> None:
    """One child, one finding: `misnested-bullet` and `unknown-record-property` never both fire.

    `error` is a bullet key of `endpoint` (an alias of `errors`), so nesting it under
    `response:` is reported as `misnested-bullet` — it must not also be reported as an
    out-of-vocabulary property, even though `error` is not in `response:`'s vocabulary either.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book("error: 404 when no such account"))
    assert [f.ref for f in _findings(repo, "misnested-bullet")] == ["response:error"]
    assert _findings(repo, "unknown-record-property") == []


def _endpoint_book_with(container_key: str, *children: str) -> str:
    body = "\n".join(f"  - {child}" for child in children)
    return f"""---
type: server
title: Acme accounts
---
# Acme accounts

## Endpoints

### list-accounts
- {container_key}:
{body}
- authorization: an adjuster reads every account on file.
"""


def test_a_bullet_key_buried_under_an_undeclared_container_is_reported(repo: Path) -> None:
    """`request:` is not a bullet key `endpoint` declares, so its `method:`/`path:` children
    fall back to the flat-subtree grammar and land in `meta["request"]` as strings — not as the
    top-level `method:`/`path:` bullets the type actually grades against. One finding per buried
    child, so each can be closed on its own.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book_with("request", "method: GET", "path: /api/accounts"))
    found = _findings(repo, "misnested-bullet")
    assert [(f.severity, f.ref) for f in found] == [
        ("error", "request:method"), ("error", "request:path")]
    assert "request" in found[0].message and "not a key" in found[0].message
    assert all(f.suggestion is not None and f.fixable for f in found)


def test_the_buried_child_key_is_absent_from_top_level_meta(repo: Path) -> None:
    """A finding on this branch names a genuinely invisible claim, not a duplicated one.

    If `method:`/`path:` also appeared at the node's own top level, the child key would not be
    buried — it would be duplicated, which is the too-wide signal this branch must not produce.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book_with("request", "method: GET", "path: /api/accounts"))
    node = _endpoint(repo)
    assert "method" not in node.meta
    assert "path" not in node.meta


def test_a_child_spelled_like_no_bullet_key_does_not_widen_the_container(repo: Path) -> None:
    """A container key that never happens to bury a declared spelling stays unreported."""
    write(repo / ENDPOINT_PATH, _endpoint_book_with("request", "protocol: HTTP/1.1"))
    assert _findings(repo, "misnested-bullet") == []


def test_a_declared_container_is_not_also_read_by_this_branch(repo: Path) -> None:
    """`response:` is declared and `record=True`, so `_check_record_properties` owns it already;
    this branch only ever looks at keys `endpoint` never wrote down."""
    write(repo / ENDPOINT_PATH, _endpoint_book("status: 200"))
    found = _findings(repo, "misnested-bullet")
    assert [f.ref for f in found] == ["response:status"]


def test_a_prose_parent_spelled_like_no_bullet_key_never_fires(repo: Path) -> None:
    """The key-ish clause is load-bearing: without it, a numbered-list item whose 'key' is a
    sentence of prose would be misread as a container bullet, and the promote-to-top-level
    remedy would be wrong advice for it — that shape belongs to a different finding entirely.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book_with(
        "when the account is missing", "status: 404", "errors: no such account"))
    assert _findings(repo, "misnested-bullet") == []


def test_no_bullet_key_is_both_entries_and_record() -> None:
    """The two say different things about one child, so a key that set both would have no shape."""
    both = [(uitype.name, key.key)
            for uitype in registry.UI_TYPES
            for key in uitype.bullet_keys if key.entries and key.record]
    assert both == []


def test_every_container_key_is_nested() -> None:
    """`entries` and `record` both refine what a nested child *is*, and neither implies nesting."""
    flat = [(uitype.name, key.key)
            for uitype in registry.UI_TYPES
            for key in uitype.bullet_keys if (key.entries or key.record) and not key.nested]
    assert flat == []
