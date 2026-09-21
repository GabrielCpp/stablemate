"""farrier wires the generated launcher into an existing root Makefile."""
from __future__ import annotations

from farrier.install import (
    LAUNCHER_AGENTS_MK,
    ensure_makefile_include,
)

EXISTING = "help: ## Show this help\n\t@echo hi\n\ntest: ## Run tests\n\tpytest\n"


def test_appends_include_block_and_preserves_existing(tmp_path):
    mk = tmp_path / "Makefile"
    mk.write_text(EXISTING, encoding="utf-8")

    assert ensure_makefile_include(tmp_path) is True
    text = mk.read_text(encoding="utf-8")

    assert text.startswith(EXISTING)
    assert text.index("help:") < text.index("include")
    assert f"include {LAUNCHER_AGENTS_MK}" in text


def test_is_idempotent(tmp_path):
    mk = tmp_path / "Makefile"
    mk.write_text(EXISTING, encoding="utf-8")

    assert ensure_makefile_include(tmp_path) is True
    once = mk.read_text(encoding="utf-8")
    assert ensure_makefile_include(tmp_path) is False
    assert mk.read_text(encoding="utf-8") == once
    assert once.count(f"include {LAUNCHER_AGENTS_MK}") == 1


def test_noop_when_include_already_present(tmp_path):
    mk = tmp_path / "Makefile"
    mk.write_text(EXISTING + f"\ninclude {LAUNCHER_AGENTS_MK}\n", encoding="utf-8")
    assert ensure_makefile_include(tmp_path) is False


def test_noop_when_no_makefile(tmp_path):
    assert ensure_makefile_include(tmp_path) is False
    assert not (tmp_path / "Makefile").exists()
