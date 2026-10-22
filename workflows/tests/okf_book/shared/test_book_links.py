from __future__ import annotations

from ostler.doctor import Report
from ostler.finding import Finding

from workhorse_workflows.okf_book.shared.book_links import inbound_broken, relinked, retargets_only

PAGE = "docs/services/other/guide/start.md"
TEXT = "See [old](../../ledger/old.md#totals), [same](../../ledger/old.md) and [kept](../../ledger/kept.md).\n"


def test_a_relink_points_each_link_on_the_old_page_at_the_new_one_and_keeps_its_anchor() -> None:
    text, changed = relinked("ledger", PAGE, TEXT, "old.md", "flows/new.md")

    assert changed == 2
    assert text == (
        "See [old](../../ledger/flows/new.md#totals), [same](../../ledger/flows/new.md) and [kept](../../ledger/kept.md).\n"
    )


def test_a_relink_from_an_anchor_moves_only_the_links_to_that_anchor_and_sets_the_new_one() -> None:
    text, changed = relinked("ledger", PAGE, TEXT, "old.md#totals", "kept.md#sums")

    assert changed == 1
    assert text.startswith("See [old](../../ledger/kept.md#sums), [same](../../ledger/old.md)")


def test_a_change_of_link_targets_into_the_book_is_a_retarget_and_any_other_change_is_not() -> None:
    retargeted, _ = relinked("ledger", PAGE, TEXT, "old.md", "kept.md")

    assert retargets_only("ledger", PAGE, TEXT, retargeted)
    assert not retargets_only("ledger", PAGE, TEXT, TEXT)
    assert not retargets_only("ledger", PAGE, TEXT, retargeted.replace("See", "Read"))
    assert not retargets_only("ledger", PAGE, TEXT, TEXT.replace("../../ledger/old.md", "../intro.md", 1))


def _dangling(path: str, href: str) -> Finding:
    return Finding(severity="error", code="dangling-link", message="dangling", ref=f"{path}:3:{href}", path=path, line=3)


def test_a_broken_link_from_another_book_into_the_book_is_the_books_to_retarget() -> None:
    inbound = _dangling(PAGE, "../../ledger/old.md")
    elsewhere = _dangling(PAGE, "../intro.md")
    own = _dangling("docs/services/ledger/kept.md", "old.md")
    report = Report(org="", profile="", findings=[inbound, elsewhere, own])

    found = inbound_broken(report, "ledger")

    assert [finding.ref for finding in found] == [inbound.ref]
    assert "`relink`" in found[0].suggestion
