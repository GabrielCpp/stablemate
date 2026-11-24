from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from _books import write_book
from workhorse._vendor.stablemate_core import books, config as core_config

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


def milestone_folder(repo: Path, slug: str = "account-access") -> Path:
    """The folder of milestone *slug* for the code checkout *repo*, under its product in the artifacts folder."""
    home = books.milestones_home(repo)
    assert home is not None
    return home / slug


def milestone_key(repo: Path, slug: str = "account-access") -> str:
    """The `milestone.md` of *slug*, relative to the artifacts folder."""
    path = milestone_folder(repo, slug) / "milestone.md"
    return path.relative_to(core_config.resolve_artifacts_dir()).as_posix()


def write_milestone(
    root: Path,
    slug: str = "account-access",
    *,
    status: str = "approved",
    epics: Sequence[str] = (),
) -> Path:
    """Write a ready milestone folder for the checkout *root* and return its `milestone.md`."""
    path = milestone_folder(root, slug) / "milestone.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = "epics: []\n" if not epics else "epics:\n" + "".join(f"- {e}\n" for e in epics)
    path.write_text(
        f"---\ntype: milestone\ntitle: Account access\nstatus: {status}\n{listed}---\n{BODY}",
        encoding="utf-8",
    )
    write_book(root, "account")
    return path
