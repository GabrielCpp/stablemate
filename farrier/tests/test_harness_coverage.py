"""Each farrier table that names harnesses covers exactly the harnesses that claim its surface."""

from __future__ import annotations

from typing import Any

import pytest

from farrier._vendor.stablemate_core.harness import (
    HarnessSpec,
    Surface,
    home_harnesses,
    repo_harnesses,
    with_surface,
)
from farrier._vendor.stablemate_core.schema import Agents, UserLibraryTable
from farrier.agents import REPO_SKILL_DIRS
from farrier.home_agents import AGENT_DIALECTS
from farrier.home_entries import MCP_DIALECTS, SETTINGS_FILES
from farrier.home_guards import GUARD_DIALECTS
from farrier.renderer import USER_HARNESS_DIRS, USER_ROOT_FILES
from farrier.user_library import HARNESSES as USER_LIBRARY_HARNESSES

COVERAGE: dict[Surface, dict[str, Any]] = {
    Surface.GUARDS: GUARD_DIALECTS,
    Surface.AGENTS: AGENT_DIALECTS,
    Surface.MCP: MCP_DIALECTS,
    Surface.SETTINGS: SETTINGS_FILES,
    Surface.HOME_ROOT: USER_HARNESS_DIRS,
    Surface.REPO_SKILLS: REPO_SKILL_DIRS,
}


@pytest.mark.parametrize("surface", COVERAGE)
def test_each_table_covers_exactly_the_harnesses_that_claim_the_surface(surface: Surface) -> None:
    claimed = {spec.name for spec in with_surface(surface)}
    assert set(COVERAGE[surface]) == claimed


def test_the_home_root_files_cover_exactly_the_harnesses_that_claim_home_root() -> None:
    assert set(USER_ROOT_FILES) == {spec.name for spec in with_surface(Surface.HOME_ROOT)}


def test_the_agents_model_has_one_field_per_repo_harness() -> None:
    assert set(Agents.model_fields) == {spec.name for spec in repo_harnesses()}


def test_the_user_library_table_has_one_field_per_home_harness() -> None:
    assert set(UserLibraryTable.model_fields) - {"template"} == {
        spec.name for spec in home_harnesses()
    }


def test_the_user_library_harnesses_are_the_home_harnesses_in_this_order() -> None:
    assert set(USER_LIBRARY_HARNESSES) == {spec.name for spec in home_harnesses()}
    assert USER_LIBRARY_HARNESSES == ("claude", "codex", "copilot", "opencode")


@pytest.mark.parametrize("spec", repo_harnesses(), ids=lambda spec: spec.name)
def test_each_agents_field_names_the_folder_it_renders_into(spec: HarnessSpec) -> None:
    assert spec.repo is not None
    description = Agents.model_fields[spec.name].description or ""
    assert spec.repo.skills in description
