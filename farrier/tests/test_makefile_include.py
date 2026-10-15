"""farrier wires the generated launcher into an existing root Makefile."""
from __future__ import annotations

from farrier.install import (
    LAUNCHER_AGENTS_MK,
    MAKEFILE_INCLUDE_END,
    MAKEFILE_INCLUDE_MARKER,
    ensure_makefile_include,
)

EXISTING = "help: ## Show this help\n\t@echo hi\n\ntest: ## Run tests\n\tpytest\n"


def test_appends_include_block_and_preserves_existing(tmp_path):
    mk = tmp_path / "Makefile"
    mk.write_text(EXISTING, encoding="utf-8")

    assert ensure_makefile_include(tmp_path) is True
    text = mk.read_text(encoding="utf-8")

    assert text.startswith(EXISTING)
    assert text.index("help:") < text.index("-include")
    assert f"-include {LAUNCHER_AGENTS_MK}" in text


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


def test_noop_when_dash_include_already_present(tmp_path):
    mk = tmp_path / "Makefile"
    mk.write_text(EXISTING + f"\n-include {LAUNCHER_AGENTS_MK}\n", encoding="utf-8")
    assert ensure_makefile_include(tmp_path) is False
    assert mk.read_text(encoding="utf-8") == EXISTING + f"\n-include {LAUNCHER_AGENTS_MK}\n"


def test_upgrades_an_old_managed_block(tmp_path):
    mk = tmp_path / "Makefile"
    old = (
        f"{MAKEFILE_INCLUDE_MARKER}\n"
        "# old text\n"
        f"include {LAUNCHER_AGENTS_MK}\n"
        f"{MAKEFILE_INCLUDE_END}\n"
    )
    mk.write_text(EXISTING + "\n" + old + "\nafter:\n\t@true\n", encoding="utf-8")

    assert ensure_makefile_include(tmp_path) is True
    text = mk.read_text(encoding="utf-8")

    assert text.startswith(EXISTING)
    assert text.endswith("\nafter:\n\t@true\n")
    assert f"-include {LAUNCHER_AGENTS_MK}" in text
    assert f"\ninclude {LAUNCHER_AGENTS_MK}" not in text
    assert text.count(MAKEFILE_INCLUDE_MARKER) == 1
    assert ensure_makefile_include(tmp_path) is False


def test_leaves_a_users_own_bare_include_alone(tmp_path):
    mk = tmp_path / "Makefile"
    mine = EXISTING + f"\ninclude {LAUNCHER_AGENTS_MK}\n"
    mk.write_text(mine, encoding="utf-8")

    assert ensure_makefile_include(tmp_path) is False
    assert mk.read_text(encoding="utf-8") == mine
