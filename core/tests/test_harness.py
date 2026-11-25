"""The registry holds each harness once and answers for every capability."""

from __future__ import annotations

import dataclasses

import pytest

from stablemate_core import harness
from stablemate_core.harness import HarnessSpec, Support, Surface
from stablemate_core.schema import HARNESSES as MANIFEST_HARNESSES

CAPABILITIES = ("extra_dirs", "compaction", "subagents", "confinement", "transcript")


def test_the_names_are_unique() -> None:
    assert len(set(harness.names())) == len(harness.names())


@pytest.mark.parametrize("name", harness.names())
def test_spec_returns_the_spec_of_that_name(name: str) -> None:
    assert harness.spec(name).name == name


def test_an_unknown_name_lists_the_valid_ones() -> None:
    with pytest.raises(ValueError) as caught:
        harness.spec("nope")
    assert "nope" in str(caught.value)
    for name in harness.names():
        assert name in str(caught.value)


@pytest.mark.parametrize("spec", harness.HARNESSES, ids=lambda spec: spec.name)
def test_a_spec_with_a_repo_layout_claims_repo_skills(spec: HarnessSpec) -> None:
    assert (spec.repo is not None) == (Surface.REPO_SKILLS in spec.surfaces)


@pytest.mark.parametrize("spec", harness.HARNESSES, ids=lambda spec: spec.name)
@pytest.mark.parametrize("capability", CAPABILITIES)
def test_every_capability_is_a_support(spec: HarnessSpec, capability: str) -> None:
    assert isinstance(getattr(spec, capability), Support)


def test_the_capabilities_are_every_support_field() -> None:
    fields = {
        field.name
        for field in dataclasses.fields(HarnessSpec)
        if field.type in (Support, "Support")
    }
    assert fields == set(CAPABILITIES)


def test_the_manifest_names_are_the_repo_harnesses_in_registry_order() -> None:
    assert MANIFEST_HARNESSES == tuple(spec.name for spec in harness.repo_harnesses())
    assert MANIFEST_HARNESSES == ("claude", "codex", "copilot", "antigravity", "pi")


def test_the_registry_renders_repo_harnesses_in_this_order() -> None:
    assert [spec.name for spec in harness.repo_harnesses()] == [
        "claude",
        "codex",
        "copilot",
        "antigravity",
        "pi",
    ]


def test_the_registry_lists_home_harnesses_in_this_order() -> None:
    assert [spec.name for spec in harness.home_harnesses()] == [
        "claude",
        "codex",
        "copilot",
        "opencode",
        "antigravity",
        "pi",
    ]


def test_antigravity_is_a_farrier_target_the_workhorse_never_offers() -> None:
    antigravity = harness.spec("antigravity")

    assert antigravity.workhorse is False
    assert antigravity.workhorse_reason
    assert "antigravity" not in [spec.name for spec in harness.workhorse_harnesses()]


def test_pi_shares_the_agents_skill_folder_and_compacts_through_rpc() -> None:
    pi = harness.spec("pi")

    assert pi.workhorse is True
    assert pi.skill_ref == "path"
    assert pi.repo is not None
    codex = harness.spec("codex")
    assert codex.repo is not None and codex.home is not None
    assert pi.repo.skills == codex.repo.skills
    assert pi.repo.prompts == ".pi/prompts"
    assert pi.home is not None
    assert pi.home.dir == codex.home.dir
    assert pi.home.root_file == ".pi/agent/AGENTS.md"
    assert Surface.AGENTS not in pi.surfaces
    assert pi.compaction.level is harness.Level.NATIVE
    assert pi.subagents.level is harness.Level.NONE
    assert pi.confinement.level is harness.Level.NONE
