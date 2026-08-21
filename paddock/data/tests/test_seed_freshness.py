"""Every seed captured from a tracked tree still matches that tree.

A round does not materialize from `data/apps/<app>/`. It materializes from the unpacked
seed zip (`_frozenapp.run_round` → `materialize(run.repo, …)`), while the answer key is
read from the tracked tree on purpose — a ruler that travelled inside the thing being
measured would measure nothing. That split is right, and it is also how a fixture edit
disappears: repair the book, commit it, and every trial keeps facing the previous content
with the new key held against it. Nothing about the run looks wrong; the score is just no
longer about the fixture in the repo.

So the pointer records the source tree's own content hash at capture, and this recomputes
it. Seeds captured from outside the data directory — a greenfield capture taken from a
live session's workdir — record no `source` and are skipped here: there is no in-tree
tree for them to have drifted from, which makes them exempt by construction rather than
by a list of exceptions somebody has to maintain.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from paddock.pointer import Pointer

DATA = Path(__file__).parents[1]
SEEDS = DATA / "seeds"


def pointers() -> list[Pointer]:
    return [Pointer.load(path) for path in sorted(SEEDS.glob("*.toml"))]


def in_tree() -> list[Pointer]:
    return [pointer for pointer in pointers() if pointer.source]


def _ids(rows: list[Pointer]) -> list[str]:
    return [row.name for row in rows]


def test_the_data_directory_ships_seeds_at_all() -> None:
    """A glob that silently matched nothing would make every test below vacuous."""
    assert pointers(), f"no seed pointers under {SEEDS}"


@pytest.mark.parametrize("pointer", in_tree(), ids=_ids(in_tree()))
def test_an_in_tree_seed_points_at_a_directory_that_exists(pointer: Pointer) -> None:
    source = DATA / pointer.source
    assert source.is_dir(), f"seed '{pointer.name}' names {pointer.source}, which is not a directory"


@pytest.mark.parametrize("pointer", in_tree(), ids=_ids(in_tree()))
def test_an_in_tree_seed_matches_the_tree_it_was_captured_from(pointer: Pointer) -> None:
    """The guard itself. `verify_tree` raises with the re-capture command in its message."""
    pointer.verify_tree(DATA / pointer.source)


@pytest.mark.parametrize("pointer", pointers(), ids=_ids(pointers()))
def test_a_seed_captured_from_a_tracked_app_says_so(pointer: Pointer) -> None:
    """A frozen fixture may not quietly become exempt.

    `source` is empty for a legitimately out-of-tree capture, so the field alone cannot
    tell an exemption from an omission. An app directory carrying the answer key is the
    tell: if `apps/<name>/defects.yml` exists, the seed of that name is a frozen fixture
    and has to be pinned to it.
    """
    app = DATA / "apps" / pointer.name
    if not (app / "defects.yml").is_file():
        return
    assert pointer.source == f"apps/{pointer.name}", (
        f"seed '{pointer.name}' is a frozen fixture with an answer key at {app}/defects.yml "
        f"but records source={pointer.source!r}; re-capture it from that directory"
    )
