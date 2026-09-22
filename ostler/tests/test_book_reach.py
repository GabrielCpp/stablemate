"""A service's `entries` page roots its book: `unreachable-node` and `ostler gc`."""

from __future__ import annotations

from pathlib import Path

from ostler import Ostler, doctor, scaffold
from ostler.cli import main
from ostler.model import load

from conftest import report_of, write


def _page(page_type: str, slug: str, body: str = "") -> str:
    return f"---\ntype: {page_type}\nslug: {slug}\ntitle: {slug}\n---\n# {slug}\n\n{body}"


def _write_book(repo: Path) -> Path:
    features_root = repo / "docs/features"
    write(features_root / "acme/entries.md", _page("entries", "entries", "- [cli](acme.md)\n"))
    write(features_root / "acme/acme.md", _page("cli", "acme", "See [links](concepts/link.md).\n"))
    write(features_root / "acme/concepts/link.md",
          _page("concept", "link", "A link [expires](expiry.md#rules) after a while.\n"))
    write(features_root / "acme/concepts/expiry.md", _page("concept", "expiry", "## Rules\n\nOne day.\n"))
    write(features_root / "acme/concepts/orphan.md", _page("concept", "orphan", "Nobody links here.\n"))
    write(features_root / "globex/concepts/loose.md", _page("concept", "loose", "No entries page.\n"))
    return features_root


def _unreachable(repo: Path) -> list[str]:
    report = doctor.run(load(repo))
    return sorted(finding.path for finding in report.findings if finding.code == "unreachable-node")


def test_a_page_no_link_path_reaches_is_unreachable(repo: Path):
    _write_book(repo)
    assert _unreachable(repo) == ["docs/features/acme/concepts/orphan.md"]


def test_a_link_in_concept_prose_makes_its_target_reachable(repo: Path):
    features_root = _write_book(repo)
    write(features_root / "acme/concepts/expiry.md",
          _page("concept", "expiry", "## Rules\n\nSee the [orphan](orphan.md).\n"))
    assert _unreachable(repo) == []


def test_a_service_with_no_entries_page_is_not_checked(repo: Path):
    features_root = _write_book(repo)
    (features_root / "acme/entries.md").unlink()
    assert _unreachable(repo) == []


def test_a_link_from_another_service_counts(repo: Path):
    features_root = _write_book(repo)
    write(features_root / "globex/entries.md", _page("entries", "entries", "- [acme](../acme/acme.md)\n"))
    write(features_root / "acme/concepts/link.md",
          _page("concept", "link", "See [loose](../../globex/concepts/loose.md).\n"))
    assert _unreachable(repo) == ["docs/features/acme/concepts/expiry.md",
                                  "docs/features/acme/concepts/orphan.md"]


def test_gc_lists_the_dead_pages_and_deletes_nothing_by_default(repo: Path, capsys):
    features_root = _write_book(repo)
    assert main(["-C", str(repo), "gc", "--json"]) == 0
    assert report_of(capsys) == {"deleted": False, "pages": ["docs/features/acme/concepts/orphan.md"]}
    assert (features_root / "acme/concepts/orphan.md").exists()


def test_gc_write_deletes_the_dead_pages_and_leaves_doctor_clean(repo: Path, capsys):
    features_root = _write_book(repo)
    assert main(["-C", str(repo), "gc", "--write"]) == 0
    assert "deleted: docs/features/acme/concepts/orphan.md" in capsys.readouterr().out
    assert not (features_root / "acme/concepts/orphan.md").exists()
    assert (features_root / "acme/concepts/expiry.md").exists()
    assert (features_root / "globex/concepts/loose.md").exists()
    assert _unreachable(repo) == []


def test_the_api_gc_reports_then_deletes(repo: Path):
    features_root = _write_book(repo)
    okf = Ostler(repo, use_index=False)
    assert okf.gc() == ["docs/features/acme/concepts/orphan.md"]
    assert okf.gc(write=True) == ["docs/features/acme/concepts/orphan.md"]
    assert not (features_root / "acme/concepts/orphan.md").exists()
    assert okf.gc() == []


def test_entries_scaffolds_at_the_service_root(repo: Path):
    res = scaffold.scaffold(load(repo), "entries", "entries", service="acme")
    assert res.ok, res.message
    assert res.paths == [repo / "docs/features/acme/entries.md"]
