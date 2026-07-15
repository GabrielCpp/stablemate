"""Repo-prefixed overlay skills stay addressable by their generic name.

Project overlay skills carry their repo prefix in the library
(`projects/acme/acme-developer`), so two projects can both ship a
"developer" overlay without colliding. Shared workflow prompts, however,
reference the overlay generically — `instruction_ref("developer")` — because
the same prompt renders for every repo. The lookup therefore falls back to
`<prefix>-<name>` when the generic name misses.

    ./.venv/bin/python -m pytest tests/test_skill_lookup_prefix_fallback.py
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from farrier.install import Renderer, Source


def _overlay_source(tmp_path: Path) -> Source:
    skill_file = (
        tmp_path
        / "library"
        / "skills"
        / "projects"
        / "acme"
        / "acme-developer"
        / "SKILL.md"
    )
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        textwrap.dedent(
            """\
            ---
            name: acme-developer
            description: "Acme developer workflow."
            ---

            # Acme Developer Workflow
            """
        ),
        encoding="utf-8",
    )
    return Source(
        kind="skill",
        path=skill_file,
        rel="projects/acme/acme-developer/SKILL.md",
        id="projects/acme/acme-developer",
    )


def _renderer(tmp_path: Path, source: Source) -> Renderer:
    return Renderer(tmp_path / "repo", "acme", {}, {}, [source], [])


def test_generic_name_falls_back_to_repo_prefixed_skill(tmp_path):
    source = _overlay_source(tmp_path)
    renderer = _renderer(tmp_path, source)
    assert renderer.optional_skill_source("developer") is source
    assert renderer.skill_source("developer") is source


def test_exact_prefixed_name_still_resolves(tmp_path):
    source = _overlay_source(tmp_path)
    renderer = _renderer(tmp_path, source)
    assert renderer.optional_skill_source("acme-developer") is source


def test_unknown_name_still_errors(tmp_path):
    source = _overlay_source(tmp_path)
    renderer = _renderer(tmp_path, source)
    assert renderer.optional_skill_source("does-not-exist") is None
    with pytest.raises(SystemExit):
        renderer.skill_source("does-not-exist")
