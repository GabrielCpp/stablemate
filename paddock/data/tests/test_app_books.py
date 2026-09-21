"""Every app book in this tree is clean and canonical, with the list derived from the tree."""

from __future__ import annotations

from pathlib import Path

import pytest
from paddock import loader

DATA = Path(__file__).parents[1]

APP_BOOKS = sorted(
    path.parents[1] for path in (DATA / "apps").glob("*/docs/features") if path.is_dir()
)


def _app_id(app: Path) -> str:
    return app.name


def test_the_tree_has_app_books_to_gate() -> None:
    """A glob that silently matches nothing would make every test below vacuously green."""
    assert APP_BOOKS, f"no app book found under {DATA / 'apps'}"


@pytest.mark.parametrize("app", APP_BOOKS, ids=_app_id)
def test_doctor_is_clean(app: Path) -> None:
    """0 errors and 0 warnings — see this module's docstring for why warnings count."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    report = Ostler(app).doctor().data
    assert report["errors"] == 0, report["findings"]
    assert report["warnings"] == 0, report["findings"]


@pytest.mark.parametrize("app", APP_BOOKS, ids=_app_id)
def test_the_book_is_already_canonical(app: Path) -> None:
    """`ostler fmt` must have nothing to say about an app book, or the score is unreadable."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    unformatted = Ostler(app).fmt(check=True)
    assert not unformatted, f"run `ostler fmt` in {app}: {unformatted}"


REGISTERED_SEEDS = frozenset(item.seed for item in loader.load_all(DATA))


@pytest.mark.parametrize("app", APP_BOOKS, ids=_app_id)
def test_the_app_has_a_registered_task(app: Path) -> None:
    """An app book with no task pointed at it is a fixture a round never runs against."""
    assert app.name in REGISTERED_SEEDS, (
        f"no task in {DATA / 'tasks'} declares seed={app.name!r} — {app.name} ships a book "
        "that nothing runs a round against"
    )


@pytest.mark.parametrize("app", APP_BOOKS, ids=_app_id)
def test_the_app_has_an_integrity_test_module(app: Path) -> None:
    """An app with no `test_<app>_app.py` has no gate on the ways its fixture rots silently."""
    expected = Path(__file__).parent / f"test_{app.name.replace('-', '_')}_app.py"
    assert expected.is_file(), (
        f"{app.name} has no {expected.name} — its book (and, once it has one, its answer "
        "key) can rot with nothing here to notice"
    )
