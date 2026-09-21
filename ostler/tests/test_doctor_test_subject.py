"""`code:` cites the product: a node grounded only in test source is a `test-subject`."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import refs
from ostler.cli import main

from conftest import report_of, write

GO = "package p\n\ntype Real struct{}\n\ntype MockReal struct{}\n"


def concept_md(slug: str, *targets: str) -> str:
    bullets = "".join(f"- code: `{target}`\n" for target in targets)
    return (f"---\ntype: concept\nslug: {slug}\ntitle: {slug}\n---\n"
            f"# {slug}\n\n{bullets}\nWhat this concept is for.\n")


def codes_for(capsys: pytest.CaptureFixture[str], repo: Path, slug: str) -> set[str]:
    main(["-C", str(repo), "doctor", "--json"])
    return {finding["code"] for finding in report_of(capsys)["findings"]
            if finding.get("path") == f"docs/features/concepts/{slug}.md"}


@pytest.mark.parametrize("path", [
    "internal/mocks/real.go", "src/__tests__/real.ts", "svc/real_test.go", "web/real.spec.tsx",
    "pkg/test_real.py", "pkg/conftest.py", "app/RealTest.php",
])
def test_test_sources_are_recognised(path: str) -> None:
    assert refs.is_test_source(path)


@pytest.mark.parametrize("path", ["internal/real.go", "src/contest.py", "web/testing-page.tsx"])
def test_product_sources_are_not(path: str) -> None:
    assert not refs.is_test_source(path)


def test_node_citing_only_test_source_is_a_test_subject(
        repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo / "internal/mocks/real.go", GO)
    write(repo / "internal/real_test.go", GO)
    write(repo / "docs/features/concepts/mock-real.md",
          concept_md("mock-real", "internal/mocks/real.go::MockReal", "internal/real_test.go::Real"))

    codes = codes_for(capsys, repo, "mock-real")

    assert "test-subject" in codes
    assert "code-cites-test" not in codes


def test_node_mixing_product_and_test_source_drops_the_test_citation(
        repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo / "internal/real.go", GO)
    write(repo / "internal/real_test.go", GO)
    write(repo / "docs/features/concepts/real.md",
          concept_md("real", "internal/real.go::Real", "internal/real_test.go::Real"))

    codes = codes_for(capsys, repo, "real")

    assert "code-cites-test" in codes
    assert "test-subject" not in codes


def test_node_citing_product_source_is_clean(
        repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo / "internal/real.go", GO)
    write(repo / "docs/features/concepts/real.md", concept_md("real", "internal/real.go::Real"))

    assert not {"test-subject", "code-cites-test"} & codes_for(capsys, repo, "real")
