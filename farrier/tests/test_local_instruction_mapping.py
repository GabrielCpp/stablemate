"""`localInstructions` aggregation: which sources go in, and which files come out.

An entry names skills (`skill`/`skills`), prompts (`prompt`/`prompts`), or both —
prompts are there so a procedure a repo wants *always loaded* stays one library
file rather than a hand-maintained fragment in every consuming repo's root
instructions. The aggregated text always lands in AGENTS.md, the one name every
harness reads natively; CLAUDE.md is generated beside it as an `@AGENTS.md`
pointer whenever the claude adapter is on, so the body is never written twice.

    ./.venv/bin/python -m pytest tests/test_local_instruction_mapping.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from farrier.install import main, render_expected, set_layers


def _library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    skill = root / "library" / "skills" / "stablemate" / "ostler" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: ostler\ndescription: x\n---\n\n# Ostler\n\nOstler rules.\n",
        encoding="utf-8",
    )
    prompt = root / "library" / "prompts" / "stablemate" / "commit.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(
        "---\ndescription: Commit and push\n---\n\n# Commit\n\n$ARGUMENTS\n\n"
        "Push as you go.\n",
        encoding="utf-8",
    )
    (root / "packs").mkdir()
    return root


def _repo(tmp_path: Path, mapping: str, codex: bool = False) -> Path:
    repo = tmp_path / "demo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(
        f"agents:\n  claude: true\n  codex: {str(codex).lower()}\n"
        "skills:\n  - stablemate/ostler\n"
        "prompts:\n  - stablemate/commit\n"
        "localInstructions:\n" + mapping,
        encoding="utf-8",
    )
    return repo


def _render(
    tmp_path: Path, mapping: str, codex: bool = False
) -> tuple[Path, dict[Path, str]]:
    root = _library(tmp_path)
    set_layers(root)
    repo = _repo(tmp_path, mapping, codex)
    from farrier.frontmatter import read_yaml

    return repo, render_expected(read_yaml(repo / "agents.yml"), repo)


def test_prompt_body_is_aggregated_after_the_skills(tmp_path):
    repo, outputs = _render(
        tmp_path,
        "  - skills: [demo-stablemate-ostler]\n"
        "    prompts: [demo-stablemate-commit]\n"
        '    paths: ["."]\n'
        "    includeReadme: false\n",
    )
    body = outputs[repo / "AGENTS.md"]
    assert body.index("Ostler rules.") < body.index("Push as you go.")
    # The prompt's own front matter never reaches the aggregated file.
    assert "description: Commit and push" not in body


def test_arguments_placeholder_is_dropped_when_aggregated(tmp_path):
    # Nothing substitutes `$ARGUMENTS` outside a slash-command invocation, so
    # aggregated it would be a literal dollar sign in every session's context.
    repo, outputs = _render(
        tmp_path,
        "  - prompts: [demo-stablemate-commit]\n"
        '    paths: ["."]\n'
        "    includeReadme: false\n",
    )
    assert "$ARGUMENTS" not in outputs[repo / "AGENTS.md"]
    # ...but the command itself still renders with it.
    assert "$ARGUMENTS" in outputs[repo / ".claude" / "commands" / "demo-stablemate-commit.md"]


def test_prompt_only_mapping_needs_no_skill(tmp_path):
    repo, outputs = _render(
        tmp_path,
        '  - prompt: demo-stablemate-commit\n    paths: ["."]\n    includeReadme: false\n',
    )
    assert "Push as you go." in outputs[repo / "AGENTS.md"]


def test_mapping_with_no_source_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _render(tmp_path, '  - paths: ["."]\n')
    assert "at least one source" in str(exc.value)


def test_claude_only_repo_still_writes_agents_md_plus_a_pointer(tmp_path):
    # The body goes where every harness looks, even when only Claude is enabled:
    # turning codex on later must not move a file or change what it says.
    repo, outputs = _render(
        tmp_path,
        '  - skill: demo-stablemate-ostler\n    paths: ["."]\n    includeReadme: false\n',
    )
    assert "Ostler rules." in outputs[repo / "AGENTS.md"]
    pointer = outputs[repo / "CLAUDE.md"]
    assert "@AGENTS.md" in pointer
    assert "Ostler rules." not in pointer


def test_codex_only_repo_gets_no_claude_pointer(tmp_path):
    root = _library(tmp_path)
    set_layers(root)
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: false\n  codex: true\n"
        "skills:\n  - stablemate/ostler\n"
        "localInstructions:\n"
        '  - skill: demo-stablemate-ostler\n    paths: ["."]\n    includeReadme: false\n',
        encoding="utf-8",
    )
    from farrier.frontmatter import read_yaml

    outputs = render_expected(read_yaml(repo / "agents.yml"), repo)
    assert "Ostler rules." in outputs[repo / "AGENTS.md"]
    assert repo / "CLAUDE.md" not in outputs


def _with_readme(tmp_path: Path) -> None:
    repo = tmp_path / "demo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "README.md").write_text("Local readme.\n", encoding="utf-8")


def test_readme_is_imported_when_claude_is_the_only_adapter(tmp_path):
    _with_readme(tmp_path)
    repo, outputs = _render(
        tmp_path, '  - skill: demo-stablemate-ostler\n    paths: ["."]\n', codex=False
    )
    # Claude can pull it in by reference, so the always-loaded file stays lean.
    assert "@README.md" in outputs[repo / "CLAUDE.md"]
    assert "Local readme." not in outputs[repo / "AGENTS.md"]


def test_readme_is_copied_when_another_adapter_reads_the_file(tmp_path):
    _with_readme(tmp_path)
    repo, outputs = _render(
        tmp_path, '  - skill: demo-stablemate-ostler\n    paths: ["."]\n', codex=True
    )
    # Codex has no import directive, so the body is copied — and Claude then gets
    # it through the pointer, which must not import it a second time.
    assert "Local readme." in outputs[repo / "AGENTS.md"]
    assert "@README.md" not in outputs[repo / "CLAUDE.md"]


def test_legacy_include_readme_spellings_still_map_onto_the_boolean(tmp_path):
    repo, outputs = _render(
        tmp_path,
        '  - skill: demo-stablemate-ostler\n    paths: ["."]\n    includeReadme: none\n',
    )
    assert "## Local README" not in outputs[repo / "AGENTS.md"]


def test_unknown_include_readme_value_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _render(
            tmp_path,
            '  - skill: demo-stablemate-ostler\n    paths: ["."]\n    includeReadme: maybe\n',
        )
    assert "includeReadme" in str(exc.value)


@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md"])
def test_source_resolves_either_generated_file_to_skill_and_prompt(
    tmp_path, capsys, name
):
    root = _library(tmp_path)
    repo = _repo(
        tmp_path,
        "  - skills: [demo-stablemate-ostler]\n"
        "    prompts: [demo-stablemate-commit]\n"
        '    paths: ["."]\n',
    )
    generated = repo / name
    generated.write_text("<!--\ngenerated by farrier\n-->\n\n# Body\n", encoding="utf-8")
    assert main(["source", str(generated), "--library", str(root)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        str((root / "library/skills/stablemate/ostler/SKILL.md").resolve()),
        str((root / "library/prompts/stablemate/commit.md").resolve()),
    ]
