"""Every app book in this tree is clean and canonical, with the list derived from the tree.

The same two gates used to be spelled once per app, by hand, in each
`test_<app>_app.py`. That made the set of gated books a *list* — and a list only covers
what somebody remembered to add to it. `globex` was never added: it is the app the QA
harness actually drives a browser and an HTTP client against, and for its whole life
`make -C paddock test` ran neither `doctor` nor `fmt --check` over its book. Two genuine
defects in its `flow` nodes were authored, measured and repaired without one gate here
saying a word.

So the enumeration is the tree: an app directory with a `docs/features/` in it *is* an
app book, and the next one to land is gated the day it lands rather than the day someone
remembers this file. What the two gates are for:

* **doctor** — 0 errors *and* 0 warnings. Warnings count where they would not in a
  working repo: `undeclared-obligation` and `compound-normative-bullet` are both
  warnings, and both describe a book that cannot be used as an answer key — the first
  leaves a bullet nothing has to verify, the second a bullet two different verdicts can
  both honestly claim.
* **fmt** — a non-canonical fixture buries the book diff a scored round is read from. A
  trial's QA lane edits the book, and the diff between the authored book and the one the
  trial ends with is the evidence for whether the obligations moved while they were being
  measured. When the fixture is not canonical the run converges on the canonical shape on
  its way past, and 3 lines of real change arrive inside 89 lines of bullet reordering.
  That is not hypothetical — it is what the first scored round did.

What this file deliberately does **not** claim: that a clean `doctor` means every checker
ran. `globex` is the tree's only `exploration`-profile book, and `doctor.run` returns
early for any profile but `full` (`doctor.py:180`), so the whole fixture tier — including
`_check_fixture_call_args`, which reads exactly the bullets those two defects were in —
is never entered for it. This gate makes the checks that *do* run visible; it does not
make them complete.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DATA = Path(__file__).parents[1]

#: Every app that ships a book, in tree order. A directory, not a literal list.
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
