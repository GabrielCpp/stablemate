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


def test_a_property_the_type_does_not_declare_is_clean(repo: Path) -> None:
    """No record key declares a vocabulary yet, and an undeclared vocabulary is checked by nothing.

    `_check_entry_properties` skips one for the same reason: a key adopts the check by writing
    its vocabulary down, and until then every book's every property would be a finding about the
    check's arrival rather than about the book.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book("media: `application/json`", "schema: AccountList"))
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
