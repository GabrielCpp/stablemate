"""`farrier source <generated-file>` resolves a generated skill/command back to its
editable library source path.

A generated adapter carries a machine-independent `metadata.source` (anchored at
`library/`). `farrier source` joins it under the library root resolved exactly as
`install` does, so an agent can go from a generated `.claude/skills/**/SKILL.md`
to the editable source of truth using only the file's front matter.

    ./.venv/bin/python -m pytest tests/test_source_command.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from farrier.install import frontmatter_metadata, main


def _library(tmp_path: Path) -> Path:
    """A minimal but valid library root (must contain library/ and packs/)."""
    root = tmp_path / "agents"
    src = root / "library" / "skills" / "stablemate" / "ostler" / "SKILL.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\nname: ostler\n---\n\n# Ostler\n", encoding="utf-8")
    (root / "packs").mkdir()
    return root


def _generated(tmp_path: Path, source_rel: str) -> Path:
    dest = tmp_path / "repo" / ".claude" / "skills" / "stablemate-ostler" / "SKILL.md"
    dest.parent.mkdir(parents=True)
    dest.write_text(
        "---\n"
        "name: stablemate-ostler\n"
        'description: "x"\n'
        "metadata:\n"
        "  generated_by: farrier\n"
        f"  source: {source_rel}\n"
        '  resolve: "farrier source .claude/skills/stablemate-ostler/SKILL.md"\n'
        '  do_not_edit: "..."\n'
        "---\n\n# Ostler\n",
        encoding="utf-8",
    )
    return dest


def test_frontmatter_metadata_reads_nested_block(tmp_path):
    gen = _generated(tmp_path, "library/skills/stablemate/ostler/SKILL.md")
    meta = frontmatter_metadata(gen.read_text(encoding="utf-8"))
    assert meta["source"] == "library/skills/stablemate/ostler/SKILL.md"
    assert meta["generated_by"] == "farrier"


def test_frontmatter_metadata_empty_without_block(tmp_path):
    plain = tmp_path / "plain.md"
    plain.write_text("# not generated\n", encoding="utf-8")
    assert frontmatter_metadata(plain.read_text(encoding="utf-8")) == {}


def test_source_resolves_to_library_file(tmp_path, capsys):
    root = _library(tmp_path)
    gen = _generated(tmp_path, "library/skills/stablemate/ostler/SKILL.md")
    rc = main(["source", str(gen), "--library", str(root)])
    assert rc == 0
    printed = capsys.readouterr().out.strip()
    assert printed == str(
        (root / "library/skills/stablemate/ostler/SKILL.md").resolve()
    )


def test_source_errors_without_metadata(tmp_path):
    root = _library(tmp_path)
    plain = tmp_path / "plain.md"
    plain.write_text("# not generated\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["source", str(plain), "--library", str(root)])
    assert "metadata.source" in str(exc.value)


def test_source_errors_when_library_lacks_the_source(tmp_path):
    root = _library(tmp_path)
    gen = _generated(tmp_path, "library/skills/does/not/exist/SKILL.md")
    with pytest.raises(SystemExit) as exc:
        main(["source", str(gen), "--library", str(root)])
    assert "does not exist under the library" in str(exc.value)
