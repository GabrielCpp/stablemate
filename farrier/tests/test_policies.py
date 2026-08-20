"""Policies: library text that only ever lands in a generated AGENTS.md.

A policy is a standing rule an agent has to know *before* it knows it needs one, so
it is aggregated into the always-loaded instruction file. What makes it a kind of its
own rather than a skill that happens to be aggregated is what it does **not** cost: a
skill pays twice here — its body is fully resident in AGENTS.md *and* its name and
description still sit in the skill index the agent carries every turn, advertising
something nobody can usefully invoke. A policy is never installed, so there is no
second charge.

The invariant the tests below pin: a policy is reachable from `agents.yml`
localInstructions and from nowhere else, ever.

    ./.venv/bin/python -m pytest tests/test_policies.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from farrier._vendor.stablemate_core import discovery
from farrier.frontmatter import mapping_policy_names, read_yaml
from farrier.install import main, render_expected, set_layers

POLICY = (
    "---\nname: house-rules\ndescription: This repo's standing rules.\n---\n\n"
    "# House rules\n\nCommit as you go.\n"
)


def _library(tmp_path: Path, policies: dict[str, str] | None = None) -> Path:
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
    for rel, text in (policies or {"stablemate/house-rules": POLICY}).items():
        path = root / "library" / "policies" / f"{rel}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (root / "packs").mkdir()
    return root


def _repo(tmp_path: Path, mapping: str) -> Path:
    repo = tmp_path / "demo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\n  codex: false\n"
        "skills:\n  - stablemate/ostler\n"
        "prompts:\n  - stablemate/commit\n"
        "localInstructions:\n" + mapping,
        encoding="utf-8",
    )
    return repo


def _render(
    tmp_path: Path, mapping: str, policies: dict[str, str] | None = None
) -> tuple[Path, dict[Path, str]]:
    root = _library(tmp_path, policies)
    set_layers(root)
    repo = _repo(tmp_path, mapping)
    return repo, render_expected(read_yaml(repo / "agents.yml"), repo)


FULL_MAPPING = (
    "  - policies: [house-rules]\n"
    "    skills: [demo-ostler]\n"
    "    prompts: [demo-commit]\n"
    '    paths: ["."]\n'
    "    includeReadme: false\n"
)


def test_policy_body_is_aggregated_before_skills_and_prompts(tmp_path):
    # Standing rules above the procedures that run under them.
    repo, outputs = _render(tmp_path, FULL_MAPPING)
    body = outputs[repo / "AGENTS.md"]
    assert body.index("Commit as you go.") < body.index("Ostler rules.")
    assert body.index("Ostler rules.") < body.index("Push as you go.")


def test_policy_front_matter_never_reaches_the_generated_file(tmp_path):
    # The `description:` argues why the text deserves to be resident forever. It is a
    # review bar for the author, not a line for the agent to read every turn.
    repo, outputs = _render(tmp_path, FULL_MAPPING)
    assert "This repo's standing rules." not in outputs[repo / "AGENTS.md"]


def test_a_policy_is_installed_nowhere(tmp_path):
    """The invariant. A policy that reached any output path would be a skill again."""
    repo, outputs = _render(tmp_path, FULL_MAPPING)
    generated = {path for path in outputs if path.name not in ("AGENTS.md", "CLAUDE.md")}
    assert not [path for path in generated if "house-rules" in path.as_posix()]
    assert not [
        path for path in generated if "Commit as you go." in str(outputs[path])
    ]


def test_a_policy_is_named_by_bare_basename_with_no_prefix(tmp_path):
    # `demo-` is this repo's install prefix, and every installed skill carries it. A
    # policy has no installed name to prefix, so the name in agents.yml is the name on
    # disk — and the prefixed spelling must not quietly work as an alias.
    with pytest.raises(SystemExit) as exc:
        _render(
            tmp_path,
            '  - policies: [demo-house-rules]\n    paths: ["."]\n'
            "    includeReadme: false\n",
        )
    assert "Unknown policy reference: demo-house-rules" in str(exc.value)


def test_the_namespaced_id_also_resolves(tmp_path):
    repo, outputs = _render(
        tmp_path,
        '  - policies: [stablemate/house-rules]\n    paths: ["."]\n'
        "    includeReadme: false\n",
    )
    assert "Commit as you go." in outputs[repo / "AGENTS.md"]


def test_unknown_policy_names_the_ones_that_exist(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _render(
            tmp_path,
            '  - policies: [house-roles]\n    paths: ["."]\n    includeReadme: false\n',
        )
    message = str(exc.value)
    assert "Unknown policy reference: house-roles" in message
    assert "house-rules" in message


def test_one_basename_in_two_namespaces_is_ambiguous(tmp_path):
    # The reference in a repo's config could not say which was meant, and silently
    # picking one puts the wrong rules in every turn's context.
    with pytest.raises(SystemExit) as exc:
        _render(
            tmp_path,
            '  - policies: [house-rules]\n    paths: ["."]\n    includeReadme: false\n',
            policies={"stablemate/house-rules": POLICY, "acme/house-rules": POLICY},
        )
    message = str(exc.value)
    assert "Ambiguous policy name" in message
    assert "acme/house-rules.md" in message
    assert "stablemate/house-rules.md" in message


def test_singular_policy_key_works_like_the_plural(tmp_path):
    repo, outputs = _render(
        tmp_path,
        '  - policy: house-rules\n    paths: ["."]\n    includeReadme: false\n',
    )
    assert "Commit as you go." in outputs[repo / "AGENTS.md"]


def test_policy_only_mapping_is_a_complete_mapping(tmp_path):
    repo, outputs = _render(
        tmp_path,
        '  - policies: [house-rules]\n    paths: ["."]\n    includeReadme: false\n',
    )
    assert "Commit as you go." in outputs[repo / "AGENTS.md"]
    assert "Ostler rules." not in outputs[repo / "AGENTS.md"]


def test_a_mapping_selecting_nothing_still_names_policies(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _render(tmp_path, '  - paths: ["."]\n')
    assert "`policy`/`policies`" in str(exc.value)


def test_policy_bodies_render_templates(tmp_path):
    repo, outputs = _render(
        tmp_path,
        '  - policies: [house-rules]\n    paths: ["."]\n    includeReadme: false\n',
        policies={
            "stablemate/house-rules": "---\nname: house-rules\ndescription: x\n---\n\n"
            "Rules for {{ repo.name }}.\n"
        },
    )
    assert "Rules for demo." in outputs[repo / "AGENTS.md"]


def test_an_overlay_policy_shadows_the_base_one(tmp_path, monkeypatch):
    base = _library(tmp_path / "base")
    overlay = tmp_path / "overlay"
    shadow = overlay / "library" / "policies" / "stablemate" / "house-rules.md"
    shadow.parent.mkdir(parents=True)
    shadow.write_text(
        "---\nname: house-rules\ndescription: x\n---\n\nOverlay rules.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(discovery.BASE_DIR_ENV, str(base))
    set_layers(overlay)
    repo = _repo(
        tmp_path,
        '  - policies: [house-rules]\n    paths: ["."]\n    includeReadme: false\n',
    )
    outputs = render_expected(read_yaml(repo / "agents.yml"), repo)
    assert "Overlay rules." in outputs[repo / "AGENTS.md"]
    assert "Commit as you go." not in outputs[repo / "AGENTS.md"]


@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md"])
def test_source_resolves_a_generated_file_back_to_its_policy(tmp_path, capsys, name):
    # `farrier source` answers "which file do I edit" — and for a policy that is the
    # only question there is, since there is no installed copy to open instead.
    root = _library(tmp_path)
    repo = _repo(
        tmp_path,
        "  - policies: [house-rules]\n"
        "    skills: [demo-ostler]\n"
        '    paths: ["."]\n',
    )
    generated = repo / name
    generated.write_text("<!--\ngenerated by farrier\n-->\n\n# Body\n", encoding="utf-8")
    assert main(["source", str(generated), "--library", str(root)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        str((root / "library/policies/stablemate/house-rules.md").resolve()),
        str((root / "library/skills/stablemate/ostler/SKILL.md").resolve()),
    ]


def test_mapping_policy_names_reads_both_spellings():
    assert mapping_policy_names({"policies": ["a", "b"]}) == ["a", "b"]
    assert mapping_policy_names({"policy": "a"}) == ["a"]
    assert mapping_policy_names({"skills": ["a"]}) == []
