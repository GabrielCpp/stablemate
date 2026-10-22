from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

BODY = """# Account access

## Outcome

Account holders can access and recover their account.

## Release Boundary

The milestone is complete when sign-in and recovery pass end to end.

## User Journeys

### Sign in

- services: account

An account holder signs in, then recovers access.

## Architecture Decisions

Firebase owns authentication.

## Constraints

Existing account data remains readable.

## Acceptance

Sign-in and recovery pass end to end.

## Non-Goals

Profile editing is excluded.
"""


def write_milestone(
    root: Path,
    slug: str = "account-access",
    *,
    status: str = "approved",
    epics: Sequence[str] = (),
) -> str:
    """Write a ready milestone folder under *root* and return its repo-relative `milestone.md`."""
    relative = f"docs/milestones/{slug}/milestone.md"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = "epics: []\n" if not epics else "epics:\n" + "".join(f"- {e}\n" for e in epics)
    path.write_text(
        f"---\ntype: milestone\ntitle: Account access\nstatus: {status}\n{listed}---\n{BODY}",
        encoding="utf-8",
    )
    (root / "docs/services/account").mkdir(parents=True, exist_ok=True)
    return relative
