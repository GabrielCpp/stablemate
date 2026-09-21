"""Every seed captured from a tracked tree still matches that tree."""

from __future__ import annotations

from pathlib import Path

import pytest
from paddock import loader, paths
from paddock.pointer import Pointer
from paddock.registry import Task

DATA = Path(__file__).parents[1]
SEEDS = DATA / "configs" / "seeds"

TASKS = loader.load_all(DATA)


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
    """The guard itself."""
    pointer.verify_tree(DATA / pointer.source)


@pytest.mark.parametrize("pointer", pointers(), ids=_ids(pointers()))
def test_a_seed_captured_from_a_tracked_app_says_so(pointer: Pointer) -> None:
    """A frozen fixture may not quietly become exempt."""
    app = DATA / "apps" / pointer.name
    if not (app / "defects.yml").is_file():
        return
    assert pointer.source == f"apps/{pointer.name}", (
        f"seed '{pointer.name}' is a frozen fixture with an answer key at {app}/defects.yml "
        f"but records source={pointer.source!r}; re-capture it from that directory"
    )


def test_the_data_directory_ships_tasks_at_all() -> None:
    """The mirror of the guard above: an empty loader would make the last test vacuous."""
    assert TASKS, f"no tasks under {paths.tasks_dir(DATA)}"


@pytest.mark.parametrize("item", TASKS, ids=[item.name for item in TASKS])
def test_a_task_names_a_seed_that_exists(item: Task) -> None:
    """A task's `seed=` is a string nothing resolves at declaration time."""
    pointer = paths.seed_pointer(DATA, item.seed)
    assert pointer.is_file(), (
        f"task '{item.name}' names seed={item.seed!r}, "
        f"but {pointer} does not exist — capture it, or fix the name"
    )
