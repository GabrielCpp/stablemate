"""The backend tables cover exactly the harnesses the registry says workhorse drives."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from workhorse._vendor.stablemate_core.harness import (
    HarnessSpec,
    Level,
    spec,
    workhorse_harnesses,
)
from workhorse.runner import transcript
from workhorse.runner.backends import operator_config_dirs
from workhorse.runner.backends.registry import _REGISTRY, get_backend


def test_the_backend_registry_holds_exactly_the_workhorse_harnesses() -> None:
    assert set(_REGISTRY) == {harness.name for harness in workhorse_harnesses()}


@pytest.mark.parametrize("harness", workhorse_harnesses(), ids=lambda harness: harness.name)
def test_a_backend_supports_compaction_when_its_spec_does_natively(harness: HarnessSpec) -> None:
    assert get_backend(harness.name).supports_compaction == (harness.compaction.level is Level.NATIVE)


@pytest.mark.parametrize("harness", workhorse_harnesses(), ids=lambda harness: harness.name)
def test_a_backend_supports_subagents_when_its_spec_does_natively(harness: HarnessSpec) -> None:
    assert get_backend(harness.name).supports_subagents == (harness.subagents.level is Level.NATIVE)


@pytest.mark.parametrize("harness", workhorse_harnesses(), ids=lambda harness: harness.name)
def test_a_backend_carries_the_name_of_its_spec(harness: HarnessSpec) -> None:
    assert get_backend(harness.name).name == spec(harness.name).name


@pytest.mark.parametrize("harness", workhorse_harnesses(), ids=lambda harness: harness.name)
def test_the_operator_config_dirs_are_the_ones_the_spec_names(
    harness: HarnessSpec, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(variable, raising=False)
    for directory in harness.config_dirs:
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    assert operator_config_dirs(harness.name) == tuple(tmp_path / d for d in harness.config_dirs)


def test_the_native_transcripts_are_the_session_stores() -> None:
    native = {h.name for h in workhorse_harnesses() if h.transcript.level is Level.NATIVE}
    assert set(transcript._STORES) == native


def test_the_emulated_transcripts_are_the_exporters() -> None:
    emulated = {h.name for h in workhorse_harnesses() if h.transcript.level is Level.EMULATED}
    assert set(transcript._EXPORTERS) == emulated


def test_the_backends_guide_names_exactly_the_workhorse_harnesses() -> None:
    guide = (Path(__file__).resolve().parents[1] / "docs" / "BACKENDS.md").read_text()
    listed = re.search(r"AGENT_CLI=\{([^}]*)\}", guide)
    assert listed is not None
    assert set(listed.group(1).split(",")) == {harness.name for harness in workhorse_harnesses()}
    intro = guide.split("choosing the backend (", 1)[1].split(")", 1)[0]
    assert set(re.findall(r"`(\w+)`", intro)) == {harness.name for harness in workhorse_harnesses()}
