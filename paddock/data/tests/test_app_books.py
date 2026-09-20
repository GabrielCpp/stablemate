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
ran. `doctor.run` returns early at its one profile gate for any profile but `full`, so a
book with no epics is graded on a strict subset of the checks. Every app here now carries
a story layer and so runs `full`, but that is a property of the corpus today, not one this
gate asserts — `test_census_corpus.py` is where it is asserted. This gate makes the checks
that *do* run visible; it does not make them complete.

The same tree-derived shape catches a second, unrelated way a book goes silent: it can be
clean and still be reachable by nothing outside its own directory. `globex` was that too —
the tree's only two-service fixture, and for its whole life no task named it and no test
here gated it, so a round never ran against it and nothing would have said so. That is the
same corpus-membership bug as the doctor/fmt gap above, one level up: there the *set of
gates* was a list a book could be left off of; here the *set of tasks* and the *set of
integrity tests* are each a list an app directory could be left off of, with nothing
relating either list back to the tree of apps. So those two are tree-derived as well:

* **a registered task** — a module under `paddock/data/tasks/` whose `task()` call
  declares `seed=` as this app's directory name, loaded and validated the same way
  `paddock list` and a real round load it. Not a filename convention
  (`<app>_qa.py`): the seed is the field a round actually keys off to find the app's
  materialized tree, and a task module that got the filename right and the `seed=`
  wrong would pass a naming check and still refuse to run.
* **an integrity test module** — `test_<app>_app.py` beside this file, on the model of
  `test_seat_booking_app.py`: the tests that catch rot specific to one fixture (a stale
  manifest, a materialization that stops producing a diff, an answer-key row nothing
  can score) rather than the tree-wide checks above.

Neither gate claims the task or the test module it finds is *complete* — `globex` has no
stories or answer key yet, so its own task and integrity test are necessarily thinner than
the five apps with a full frozen-app corpus. What each gate catches is the same class of
silence the corpus-membership pattern always produces: an app with a book and nothing
outside its own directory holding a line to it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from paddock import loader

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


#: Every seed a task in the tree declares, loaded the way `paddock list` and a real round
#: load them — not a scan of task *filenames* for an app's name inside them. A task's seed
#: is what `paddock.registry.task()` actually declared, validated by the same import a
#: round runs through, so this is the one field that is actually load-bearing for "does a
#: round run against this app" rather than a naming convention that only looks like it.
REGISTERED_SEEDS = frozenset(item.seed for item in loader.load_all(DATA))


@pytest.mark.parametrize("app", APP_BOOKS, ids=_app_id)
def test_the_app_has_a_registered_task(app: Path) -> None:
    """An app book with no task pointed at it is a fixture a round never runs against.

    `globex` shipped its whole book — three surfaces, screens, flows, an `http` node per
    service — with no task in `paddock/data/tasks/` ever declaring `seed="globex"`. Nothing
    failed: `paddock list` simply never printed it, and a book that no round reaches cannot
    fail a round either. This is that silence, gated at the one field a round keys off.
    """
    assert app.name in REGISTERED_SEEDS, (
        f"no task in {DATA / 'tasks'} declares seed={app.name!r} — {app.name} ships a book "
        "that nothing runs a round against"
    )


@pytest.mark.parametrize("app", APP_BOOKS, ids=_app_id)
def test_the_app_has_an_integrity_test_module(app: Path) -> None:
    """An app with no `test_<app>_app.py` has no gate on the ways its fixture rots silently.

    `test_seat_booking_app.py`'s own docstring names three of those ways: a stale manifest,
    a materialization that stops producing a worktree diff, an answer-key row nothing can
    score. Those are fixture-specific, not tree-wide, which is why they live in a module per
    app rather than as a third parametrized gate here — but the *existence* of that module
    is exactly as tree-derived as everything else in this file.
    """
    expected = Path(__file__).parent / f"test_{app.name.replace('-', '_')}_app.py"
    assert expected.is_file(), (
        f"{app.name} has no {expected.name} — its book (and, once it has one, its answer "
        "key) can rot with nothing here to notice"
    )
