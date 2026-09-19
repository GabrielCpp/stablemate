"""A numbered list item is prose, and a bullet filed beneath one is invisible to the node.

`_check_undeclared_container_properties` catches a container key that merely looks like a bullet
the type forgot to declare — the fallback that flattens its children is the same fallback either
way, but a key spelled like prose never had a chance of being read as one of the type's own
bullets, so a normative claim or a `verify:` check buried under it is invisible for a different
reason than a misplaced one is. See `_check_prose_buried_bullets` and `_prose_burial_keys`
(doctor.py).
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

ENDPOINT_PATH = "docs/features/acme/server.md"


def _endpoint_book_with(container_key: str, *children: str) -> str:
    body = "\n".join(f"  - {child}" for child in children)
    return f"""---
type: server
title: Acme accounts
---
# Acme accounts

## Endpoints

### list-accounts
- method: GET
- path: /api/accounts
- {container_key}:
{body}
- authorization: an adjuster reads every account on file.
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def test_a_prose_container_burying_a_normative_claim_is_reported(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book_with(
        "when the account is missing the lookup still runs",
        "consistency: a missing account never raises before the lookup completes",
        "verify: omits(subject=\"lookup error\", text=\"KeyError\")"))
    found = _findings(repo, "prose-buried-bullet")
    assert [(f.severity, f.ref) for f in found] == [("error", "consistency,verify")]
    assert "`consistency:`" in found[0].message and "`verify:`" in found[0].message
    assert "not a key" in found[0].message
    assert found[0].suggestion is not None and "consistency:" in found[0].suggestion


def test_a_prose_container_with_nothing_normative_buried_is_silent(repo: Path) -> None:
    """The large legitimate population — an aside, a definition-list idiom — stays unreported.

    `status`/`errors` are neither `SHARED_NORMATIVE_KEYS` nor a `verify`-shaped check key, so a
    prose container that only ever buries them mints no obligation this check has to surface.
    """
    write(repo / ENDPOINT_PATH, _endpoint_book_with(
        "when the account is missing", "status: 404", "errors: no such account"))
    assert _findings(repo, "prose-buried-bullet") == []


def test_a_declared_multiword_key_is_never_reported(repo: Path) -> None:
    """`consistency rule` is `SHARED_NORMATIVE_KEYS`' own multi-word spelling — declared on every
    type — so using it as a container never reads as burial no matter what it nests."""
    write(repo / ENDPOINT_PATH, _endpoint_book_with(
        "consistency rule", "consistency: a second, nested claim", "verify: omits(subject=\"x\", text=\"y\")"))
    assert _findings(repo, "prose-buried-bullet") == []


def test_this_code_and_misnested_bullet_never_both_fire_on_the_same_child(repo: Path) -> None:
    """The two are gated by opposite readings of `_BULLET_KEY_SPELLING`, so one container can
    never trip both: a key-ish undeclared container (`request:`) is `misnested-bullet`'s, and a
    prose-shaped one (this test's) is this code's — never the same finding twice."""
    write(repo / ENDPOINT_PATH, _endpoint_book_with(
        "when the account is missing the lookup still runs",
        "consistency: a missing account never raises before the lookup completes",
        "verify: omits(subject=\"lookup error\", text=\"KeyError\")"))
    assert _findings(repo, "prose-buried-bullet") != []
    assert _findings(repo, "misnested-bullet") == []
