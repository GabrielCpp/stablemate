"""The second cached product — a code file's symbol table, keyed on its bytes and its grammar."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import markdown, syntax
from ostler.cli import main

from conftest import entry_files, report_of, warm_index, write

GO_ALPHA = "package p\n\ntype Alpha struct{}\n\nfunc (a *Alpha) Handle() {}\n"
GO_BETA = "package p\n\ntype Beta struct{}\n"
GO_GAMMA = "package p\n\ntype Gamma struct{}\n"
GO_UNCITED = "package p\n\ntype Uncited struct{}\n"

CITATIONS = {
    "alpha-one": "src/alpha.go::Alpha",
    "alpha-two": "src/alpha.go::(*Alpha).Handle",
    "alpha-three": "src/alpha.go::Alpha",
    "beta-one": "src/beta.go::Beta",
    "beta-copy": "src/copy/beta.go::Beta",
    "gamma-one": "src/gamma.go::Gamma",
}


def concept_md(slug: str, ref: str) -> str:
    """A concept node carrying one `code:` bullet — the node type grounding is checked on."""
    return (f"---\ntype: concept\nslug: {slug}\ntitle: {slug}\n---\n"
            f"# {slug}\n\n- code: `{ref}`\n\nWhat this concept is for.\n")


@pytest.fixture
def code_book(repo: Path) -> Path:
    """`repo` plus a small Go tree and six citations into it."""
    write(repo / "src/alpha.go", GO_ALPHA)
    write(repo / "src/beta.go", GO_BETA)
    write(repo / "src/copy/beta.go", GO_BETA)
    write(repo / "src/gamma.go", GO_GAMMA)
    write(repo / "src/uncited.go", GO_UNCITED)
    for slug, ref in CITATIONS.items():
        write(repo / f"docs/features/concepts/{slug}.md", concept_md(slug, ref))
    return repo


def record_source_parses(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Every `(grammar, text)` the source front end was asked to read."""
    calls: list[tuple[str, str]] = []
    real = syntax.parse

    def parse(language: str, text: str):
        calls.append((language, text))
        return real(language, text)

    monkeypatch.setattr(syntax, "parse", parse)
    return calls


def parses_of(calls: list[tuple[str, str]], source: str) -> int:
    return sum(1 for _, text in calls if text == source)


def record_document_parses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every text handed to the markdown splitter — the *other* cached product's cost."""
    texts: list[str] = []
    real = markdown.split

    def split(text: str) -> markdown.MarkdownDoc:
        texts.append(text)
        return real(text)

    monkeypatch.setattr(markdown, "split", split)
    return texts


def record_reads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every path whose bytes were read through `pathlib`."""
    seen: list[Path] = []

    def instrument(name: str) -> None:
        real = getattr(Path, name)

        def wrapper(self, *args, **kwargs):
            seen.append(Path(self))
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, name, wrapper)

    instrument("read_text")
    instrument("read_bytes")
    return seen


def doctor_json(book: Path, *argv: str, capsys) -> dict:
    assert main(["-C", str(book), "doctor", "--json", *argv]) in (0, 1)
    return report_of(capsys)


def codes_of(report: dict) -> set[str]:
    return {f["code"] for f in report["findings"]}


def refs_for(report: dict, code: str) -> set[str]:
    return {f.get("ref", "") for f in report["findings"] if f["code"] == code}


def test_a_code_file_is_extracted_once_however_many_citations_point_at_it(
        code_book: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """Three citations into `alpha.go` cost exactly what one citation into `gamma.go` costs."""
    calls = record_source_parses(monkeypatch)

    doctor_json(code_book, capsys=capsys)

    assert parses_of(calls, GO_GAMMA), "the fixture never grounded anything at all"
    assert parses_of(calls, GO_ALPHA) == parses_of(calls, GO_GAMMA)


def test_the_same_bytes_at_two_paths_are_one_extraction(
        code_book: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """The key is the content sha and the grammar — the path is no part of it."""
    calls = record_source_parses(monkeypatch)

    doctor_json(code_book, capsys=capsys)

    assert parses_of(calls, GO_GAMMA), "the fixture never grounded anything at all"
    assert parses_of(calls, GO_BETA) == parses_of(calls, GO_GAMMA)


def test_a_second_process_extracts_nothing_it_already_has(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """The point of a *persistent* index: the warm run reads no source tree at all."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)
    reads = record_reads(monkeypatch)
    calls = record_source_parses(monkeypatch)

    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    re_extracted = {name for name, source in (("alpha.go", GO_ALPHA), ("beta.go", GO_BETA),
                                              ("gamma.go", GO_GAMMA))
                    if parses_of(calls, source)}
    assert not re_extracted, f"re-extracted against a warm index: {sorted(re_extracted)}"
    uncited = code_book / "src" / "uncited.go"
    assert not [p for p in reads if p.resolve() == uncited.resolve()], (
        "a warm run swept a file the book does not cite")
    assert report["index"]["hits"] > 0


def test_the_grounding_verdicts_are_the_same_warm_as_cold(
        code_book: Path, tmp_path: Path, index_home: Path, capsys):
    """A reused symbol set answers every citation the freshly-extracted one answers."""
    directory = tmp_path / "index"
    write(code_book / "src/gamma.go", "package p\n\ntype Renamed struct{}\n")
    warm_index(code_book, directory)

    cached = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)
    uncached = doctor_json(code_book, "--no-index", capsys=capsys)

    assert refs_for(cached, "missing-code-symbol") == {"src/gamma.go::Gamma"}
    assert refs_for(cached, "missing-code-symbol") == refs_for(uncached, "missing-code-symbol")
    assert cached["index"]["hits"] > 0


def test_a_grammar_version_bump_re_extracts_the_code_and_leaves_the_documents_served(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """The first key holding something that is not markdown content."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)

    unbumped_sources = record_source_parses(monkeypatch)
    unbumped_documents = record_document_parses(monkeypatch)
    doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)
    baseline_documents = len(unbumped_documents)
    assert not parses_of(unbumped_sources, GO_ALPHA), "the warm run must start from a real hit"

    monkeypatch.setattr(syntax, "grammar_version", lambda: "bumped-grammar")
    bumped_sources = record_source_parses(monkeypatch)
    bumped_documents = record_document_parses(monkeypatch)
    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert parses_of(bumped_sources, GO_ALPHA), "a new grammar must re-read the source"
    assert len(bumped_documents) == baseline_documents, (
        "the grammar bump disturbed the document-parse entries, which it has no part in")
    assert report["index"]["hits"] > 0


def test_a_symbol_removed_from_a_cited_file_is_reported_on_the_next_run(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """The stale answer this key exists to make impossible — while its neighbours stay warm."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)
    write(code_book / "src/alpha.go", "package p\n\ntype Moved struct{}\n")
    calls = record_source_parses(monkeypatch)

    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert refs_for(report, "missing-code-symbol") == {
        "src/alpha.go::Alpha", "src/alpha.go::(*Alpha).Handle"}
    assert not parses_of(calls, GO_GAMMA), "a file that did not change was extracted again"


def test_a_deleted_cited_file_dangles_on_the_next_run(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """A deletion is not a sha event: there are no bytes left to key on, so the file *set* is what answers here, and the entry left behind on disk may not speak for a file that is gone."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)
    (code_book / "src" / "alpha.go").unlink()
    calls = record_source_parses(monkeypatch)

    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert refs_for(report, "dangling-code-ref") == {
        "src/alpha.go::Alpha", "src/alpha.go::(*Alpha).Handle"}
    assert "missing-code-symbol" not in codes_of(report)
    assert not parses_of(calls, GO_GAMMA), "a file that did not change was extracted again"


def test_a_cold_run_extracts_the_cited_files_once_each_and_touches_no_others(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """Populated opportunistically, as documents point at code — never by walking the tree."""
    directory = tmp_path / "index"
    reads = record_reads(monkeypatch)
    calls = record_source_parses(monkeypatch)

    doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    uncited = code_book / "src" / "uncited.go"
    assert parses_of(calls, GO_GAMMA), "the cited files were not extracted either"
    assert parses_of(calls, GO_ALPHA) == parses_of(calls, GO_GAMMA), "one extraction per file"
    assert not [p for p in reads if p.resolve() == uncited.resolve()], "read an uncited file"
    assert not parses_of(calls, GO_UNCITED), "extracted an uncited file"


def verify(book: Path, directory: Path, capsys) -> str:
    code = main(["-C", str(book), "doctor", "--verify-index", "--index-dir", str(directory)])
    printed = capsys.readouterr().out
    assert code == 0, printed
    return printed


def test_verify_agrees_against_a_populated_index_and_extracts_only_for_the_cold_half(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """Both halves of verify run in one process — so the indexed half's saving is visible here."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)

    calls = record_source_parses(monkeypatch)
    doctor_json(code_book, "--no-index", capsys=capsys)
    one_run = parses_of(calls, GO_ALPHA)
    assert one_run, "an uncached run has to extract something for this to compare anything"

    calls.clear()
    assert "agree" in verify(code_book, directory, capsys)

    assert parses_of(calls, GO_ALPHA) == one_run
    assert entry_files(directory), "verify ran against an index that has nothing in it"


def test_verify_agrees_against_an_empty_index_and_leaves_the_symbols_behind(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """The cold state — and the indexed half has to leave the symbol tables on disk."""
    directory = tmp_path / "index"

    assert "agree" in verify(code_book, directory, capsys)
    assert entry_files(directory)

    calls = record_source_parses(monkeypatch)
    doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert not parses_of(calls, GO_ALPHA), "verify never indexed the symbols it extracted"


def test_verify_agrees_against_a_partially_stale_index(
        code_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch,
        capsys):
    """One code file edited, the rest warm — the state a working tree is in nearly all the time."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)
    write(code_book / "src/alpha.go", "package p\n\ntype Moved struct{}\n")

    assert "agree" in verify(code_book, directory, capsys)

    calls = record_source_parses(monkeypatch)
    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert "src/alpha.go::Alpha" in refs_for(report, "missing-code-symbol")
    assert not parses_of(calls, GO_GAMMA), "an unedited file was extracted again"


def test_a_book_that_grounds_stays_green_through_a_warm_run(
        code_book: Path, tmp_path: Path, index_home: Path, capsys):
    directory = tmp_path / "index"
    warm_index(code_book, directory)

    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert not (codes_of(report) & {"dangling-code-ref", "missing-code-symbol"})
    assert report["index"]["hits"] > 0


def test_an_index_free_run_still_grounds_everything(code_book: Path, index_home: Path, capsys):
    """`--no-index` is the escape hatch, and it may not change a verdict — only the cost."""
    report = doctor_json(code_book, "--no-index", capsys=capsys)

    assert not (codes_of(report) & {"dangling-code-ref", "missing-code-symbol"})
    assert report["index"] == {**report["index"], "hits": 0, "misses": 0}


def test_the_symbols_of_an_uncited_process_local_file_never_enter_the_index(
        code_book: Path, tmp_path: Path, index_home: Path, capsys):
    """A miss costs one extraction, not a sweep: the cold run writes only what it was asked for."""
    directory = tmp_path / "index"
    warm_index(code_book, directory)
    before = len(entry_files(directory))

    write(code_book / "docs/features/concepts/uncited-now.md",
          concept_md("uncited-now", "src/uncited.go::Uncited"))
    report = doctor_json(code_book, "--index-dir", str(directory), capsys=capsys)

    assert not (codes_of(report) & {"dangling-code-ref", "missing-code-symbol"})
    assert len(entry_files(directory)) > before, "the newly cited file was never indexed"
