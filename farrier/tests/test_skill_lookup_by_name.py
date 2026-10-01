"""A skill is addressable by its library name, its folder name, and nothing else."""
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


def test_the_library_name_resolves(tmp_path):
    source = _overlay_source(tmp_path)
    assert _renderer(tmp_path, source).skill_source("acme-developer") is source


@pytest.mark.parametrize(
    "name", ["developer", "projects/acme/acme-developer", "does-not-exist"]
)
def test_any_other_key_misses(tmp_path, name):
    source = _overlay_source(tmp_path)
    with pytest.raises(SystemExit):
        _renderer(tmp_path, source).skill_source(name)
