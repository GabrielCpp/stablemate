"""One decision store: no module still builds the paths of the ADR store or the standing decision store."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import ids

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("ostler/ostler", "workflows/src", "paddock/paddock", "core/stablemate_core")
GONE = ("docs/adrs", "adr.md", "decisions add")
REFUSAL = "ostler/ostler/layout.py"


def modules() -> list[Path]:
    found = [path for package in PACKAGES for path in sorted((ROOT / package).rglob("*.py"))]
    assert found
    return found


def test_no_module_builds_a_path_of_the_adr_store_or_the_decisions_command() -> None:
    found = [
        f"{path.relative_to(ROOT)}: {text}"
        for path in modules()
        for text in GONE
        if text in path.read_text(encoding="utf-8")
    ]

    assert not found


def test_only_the_old_layout_refusal_names_docs_decisions() -> None:
    found = [
        path.relative_to(ROOT).as_posix()
        for path in modules()
        if "docs/decisions" in path.read_text(encoding="utf-8")
    ]

    assert found == [REFUSAL]


@pytest.mark.parametrize("slug", ["Shared Libs", "a_b", "a-", "a--b", "x" * 61, ""])
def test_a_slug_that_is_not_short_kebab_case_has_a_problem(slug: str) -> None:
    assert ids.slug_problem(slug)


@pytest.mark.parametrize("slug", ["ok", "shared-libs-live-in-libs", "x" * 60])
def test_a_short_kebab_slug_has_no_problem(slug: str) -> None:
    assert ids.slug_problem(slug) == ""
