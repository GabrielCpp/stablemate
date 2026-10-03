"""`ostler edit carve-fragments`, the page size check, and how a fragment page is read and checked."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import doctor, fragment_carve, page_size
from ostler.cli import main
from ostler.model import load

from conftest import write

_PAGE = "docs/features/acme/concepts/ledger.md"
_LINKER = "docs/features/acme/concepts/budget.md"
_LIMIT = 2400
_PROSE = "The ledger keeps this rule for every entry it records, whichever account the entry lands in. " * 3


def _rule(n: int, link: str = "") -> list[str]:
    return [f"### rule-{n}", "", f"- rule: entries obey rule {n}", *([link] if link else []), "", _PROSE, ""]


def _ledger(rules: int = 8, chained: bool = False) -> str:
    lines = ["---", "type: concept", "title: Ledger", "---", "# Ledger", "", "- code: `app.py`", "",
             "## Rules", "", "Every rule the ledger enforces.", ""]
    for n in range(1, rules + 1):
        chain = chained and n < rules
        lines += _rule(n, f"- see [the next rule](#rule-{n + 1})" if chain or n == 4 else "")
    lines += ["## Notes", "", "The ledger is append-only.", ""]
    return "\n".join(lines)


def _budget() -> str:
    return "\n".join(["---", "type: concept", "title: Budget", "---", "# Budget", "",
                      "- extends: [the third rule](ledger.md#rule-3)", ""])


@pytest.fixture
def small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fragment_carve, "PAGE_SIZE_LIMIT", _LIMIT)
    monkeypatch.setattr(page_size, "PAGE_SIZE_LIMIT", _LIMIT)


def _book(repo: Path, rules: int = 8, chained: bool = False) -> Path:
    write(repo / _PAGE, _ledger(rules, chained))
    write(repo / _LINKER, _budget())
    write(repo / "app.py", "x = 1\n")
    return repo / _PAGE


def _findings(repo: Path, code: str) -> list[str]:
    return [f.path for f in doctor.run(load(repo)).findings if f.code == code]


def _fragments(page: Path) -> list[Path]:
    return sorted(page.parent.glob("ledger-rules*.md"))


def test_a_page_past_the_limit_is_reported(repo: Path, small_limit: None):
    _ = _book(repo)

    assert _findings(repo, "page-too-large") == [_PAGE]


def test_a_page_within_the_limit_is_left_as_it_is(repo: Path, small_limit: None):
    page = _book(repo, rules=2)

    plan = fragment_carve.carve_fragments(load(repo), _PAGE)

    assert not plan.error and plan.changes == []
    assert page.read_text(encoding="utf-8") == _ledger(2)


def test_a_page_past_the_limit_moves_its_largest_section_onto_fragments_that_fit(repo: Path, small_limit: None):
    page = _book(repo)

    plan = fragment_carve.carve_fragments(load(repo), _PAGE)
    assert not plan.error, plan.error
    plan.apply()

    fragments = _fragments(page)
    assert len(fragments) > 1
    assert all(f.stat().st_size <= _LIMIT for f in fragments)
    assert page.stat().st_size <= _LIMIT
    text = page.read_text(encoding="utf-8")
    assert "### rule-" not in text and "## Notes" in text and "Every rule the ledger enforces." in text
    assert all(f"]({f.name})" in text for f in fragments)


def test_subsections_that_link_each_other_land_on_the_same_fragment(repo: Path, small_limit: None):
    page = _book(repo)

    fragment_carve.carve_fragments(load(repo), _PAGE).apply()

    holding = [f for f in _fragments(page) if "### rule-4" in f.read_text(encoding="utf-8")]
    assert len(holding) == 1
    text = holding[0].read_text(encoding="utf-8")
    assert "### rule-5" in text and "](#rule-5)" in text


def test_subsections_linked_past_what_one_fragment_holds_are_split_and_their_links_follow(
        repo: Path, small_limit: None):
    page = _book(repo, chained=True)

    plan = fragment_carve.carve_fragments(load(repo), _PAGE)
    assert not plan.error, plan.error
    plan.apply()

    fragments = _fragments(page)
    assert len(fragments) > 1 and all(f.stat().st_size <= _LIMIT for f in fragments)
    texts = "\n".join(f.read_text(encoding="utf-8") for f in fragments)
    assert any(f"]({f.name}#rule-" in texts for f in fragments)
    assert _findings(repo, "broken-link") == []


def test_a_link_into_a_moved_subsection_follows_it(repo: Path, small_limit: None):
    page = _book(repo)

    fragment_carve.carve_fragments(load(repo), _PAGE).apply()

    [holding] = [f for f in _fragments(page) if "### rule-3" in f.read_text(encoding="utf-8")]
    assert f"]({holding.name}#rule-3)" in (repo / _LINKER).read_text(encoding="utf-8")


def test_a_check_locator_into_a_moved_subsection_follows_it(repo: Path, small_limit: None):
    page = _book(repo)
    write(repo / _LINKER, _budget() + '- verify: focusable(locator="ledger.md#rule-6")\n')

    fragment_carve.carve_fragments(load(repo), _PAGE).apply()

    [holding] = [f for f in _fragments(page) if "### rule-6" in f.read_text(encoding="utf-8")]
    assert f'locator="{holding.name}#rule-6"' in (repo / _LINKER).read_text(encoding="utf-8")


def test_a_same_page_check_locator_split_from_its_subsection_names_the_fragment(repo: Path, small_limit: None):
    page = _book(repo, chained=True)
    text = page.read_text(encoding="utf-8").replace("- see [the next rule](#rule-2)", '- verify: focusable(locator="#rule-8")')
    write(page, text)

    fragment_carve.carve_fragments(load(repo), _PAGE).apply()

    [holding] = [f for f in _fragments(page) if "### rule-8" in f.read_text(encoding="utf-8")]
    [citing] = [f for f in _fragments(page) if "rule 1\n" in f.read_text(encoding="utf-8")]
    assert citing != holding
    assert f'locator="{holding.name}#rule-8"' in citing.read_text(encoding="utf-8")


def test_a_carved_book_passes_the_size_and_fragment_checks(repo: Path, small_limit: None):
    _ = _book(repo)

    fragment_carve.carve_fragments(load(repo), _PAGE).apply()

    codes = {f.code for f in doctor.run(load(repo)).findings}
    assert not codes & {"page-too-large", "fragment-without-host", "fragment-of-fragment",
                        "unlisted-fragment", "missing-required-bullet", "unreachable-node"}


def test_a_fragments_sections_are_parented_to_its_host(repo: Path, small_limit: None):
    page = _book(repo)

    fragment_carve.carve_fragments(load(repo), _PAGE).apply()

    rel = _fragments(page)[0].relative_to(repo).as_posix()
    sections = [n for n in load(repo).ui_nodes if n.path.resolve() == (repo / rel).resolve() and n.kind != "file"]
    outer = [n for n in sections if not n.parent.startswith(rel)]
    assert [n.title for n in outer] == ["Rules"] and outer[0].parent == _PAGE


def test_a_subsection_too_large_for_any_fragment_refuses_the_carve(repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fragment_carve, "PAGE_SIZE_LIMIT", 700)
    page = _book(repo)

    plan = fragment_carve.carve_fragments(load(repo), _PAGE)

    assert "split it by hand" in plan.error
    assert page.read_text(encoding="utf-8") == _ledger()


def test_a_fragment_the_host_does_not_link_is_reported(repo: Path, small_limit: None):
    page = _book(repo)
    fragment_carve.carve_fragments(load(repo), _PAGE).apply()
    first = _fragments(page)[0]
    text = page.read_text(encoding="utf-8")
    _ = page.write_text(text.replace(f"- [{first.stem}]({first.name})\n", ""), encoding="utf-8")

    assert first.relative_to(repo).as_posix() in _findings(repo, "unlisted-fragment")


def test_a_fragment_with_no_host_is_reported(repo: Path):
    rel = "docs/features/acme/concepts/orphan.md"
    write(repo / rel, "\n".join(["---", "type: fragment", "title: Orphan", "---", "# Orphan", "",
                                 "- host: [gone](gone.md)", ""]))

    assert _findings(repo, "fragment-without-host") == [rel]


def test_a_fragment_hosted_by_a_fragment_is_reported(repo: Path):
    first = "docs/features/acme/concepts/one.md"
    second = "docs/features/acme/concepts/two.md"
    write(repo / first, "\n".join(["---", "type: fragment", "title: One", "---", "# One", "",
                                   "- host: [two](two.md)", ""]))
    write(repo / second, "\n".join(["---", "type: fragment", "title: Two", "---", "# Two", "",
                                    "- host: [one](one.md)", "", "- [one](one.md)", ""]))

    assert sorted(_findings(repo, "fragment-of-fragment")) == [first, second]


def test_the_cli_carves_a_page(repo: Path, small_limit: None, capsys: pytest.CaptureFixture[str]):
    page = _book(repo)

    assert main(["-C", str(repo), "edit", "carve-fragments", _PAGE, "--write"]) == 0

    assert "fragment page(s)" in capsys.readouterr().out
    assert _fragments(page)


def test_a_page_is_read_from_the_book_when_the_working_directory_holds_the_same_path(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, small_limit: None
):
    page = _book(repo)
    elsewhere = tmp_path / "elsewhere"
    write(elsewhere / _PAGE, "# not this book\n")
    monkeypatch.chdir(elsewhere)

    plan = fragment_carve.carve_fragments(load(repo), _PAGE)

    assert not plan.error, plan.error
    assert {change.path.resolve().parent for change in plan.changes} == {page.resolve().parent}
