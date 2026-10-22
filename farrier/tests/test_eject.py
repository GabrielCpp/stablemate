"""`farrier eject`: a generated skill or a library policy becomes the repo's own."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from farrier.frontmatter import frontmatter_mapping
from farrier.install import main
from farrier.ownership import is_generated

SKILL = (
    "---\nname: db\ndescription: Database rules.\ntags: [data]\n---\n\n"
    "# Database\n\nUse the pool.\n"
)
OSTLER = (
    "---\nname: ostler\ndescription: Ostler rules.\n---\n\n"
    "# Ostler\n\nOstler rules.\n\nSee {{ skill_path('db') }}.\n"
)
POLICY = (
    "---\nname: house-rules\ndescription: Standing rules.\n---\n\n"
    "# House rules\n\nCommit as you go.\n"
)


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills" / "stablemate"
    (skills / "db").mkdir(parents=True)
    (skills / "db" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (skills / "db" / "references").mkdir()
    (skills / "db" / "references" / "pool.md").write_text(
        "# Pool\n\nSize it.\n", encoding="utf-8"
    )
    (skills / "db" / "scripts").mkdir()
    (skills / "db" / "scripts" / "run.sh").write_text(
        "#!/bin/sh\necho hi\n", encoding="utf-8"
    )
    (skills / "ostler").mkdir()
    (skills / "ostler" / "SKILL.md").write_text(OSTLER, encoding="utf-8")
    (skills / "cache.md").write_text(
        "---\nname: cache\ndescription: Cache rules.\n---\n\nCache.\n", encoding="utf-8"
    )
    policies = library / "library" / "policies" / "stablemate"
    policies.mkdir(parents=True)
    (policies / "house-rules.md").write_text(POLICY, encoding="utf-8")
    (policies / "linking.md").write_text(
        "---\nname: linking\ndescription: Links.\n---\n\nSee {{ skill_path('db') }}.\n",
        encoding="utf-8",
    )
    (library / "library" / "prompts").mkdir(parents=True)
    packs = library / "packs"
    packs.mkdir()
    (packs / "core.yml").write_text(
        "skills:\n  - stablemate/db\n  - stablemate/cache\n", encoding="utf-8"
    )
    return library


def run(repo: Path, library: Path, *args: str) -> int:
    return main([*args, "--repo", str(repo), "--library", str(library)])


def install(repo: Path, library: Path, config: str) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(config, encoding="utf-8")
    assert run(repo, library, "install") == 0


def check(repo: Path, library: Path) -> int:
    return run(repo, library, "install", "--check")


def selected_in(repo: Path) -> dict:
    return yaml.safe_load((repo / "agents.yml").read_text(encoding="utf-8"))


def test_the_strip_inverts_the_renderer_and_keeps_everything_else(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, "agents:\n  claude: true\nskills:\n  - stablemate/db\n")
    folder = repo / ".claude/skills/acme-db"
    generated = (folder / "SKILL.md").read_text(encoding="utf-8")
    asset = (folder / "references/pool.md").read_text(encoding="utf-8")
    script = (folder / "scripts/run.sh").read_text(encoding="utf-8")

    assert run(repo, library, "eject", "acme-db") == 0

    stripped = (folder / "SKILL.md").read_text(encoding="utf-8")
    head, rest = generated.split("metadata:\n", 1)
    tail = rest[rest.index("  tags:") :]
    assert stripped == head + "metadata:\n" + tail
    assert frontmatter_mapping(stripped)["metadata"] == {"tags": ["data"]}
    assert (folder / "references/pool.md").read_text(
        encoding="utf-8"
    ) == "# Pool\n\nSize it.\n"
    assert "<!--" in asset
    assert (folder / "scripts/run.sh").read_text(encoding="utf-8") == script
    assert not any(is_generated(p) for p in folder.rglob("*") if p.is_file())


def test_the_strip_drops_the_metadata_block_when_nothing_else_is_in_it(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, "agents:\n  claude: true\nskills:\n  - stablemate/cache\n")

    assert run(repo, library, "eject", "acme-cache") == 0

    stripped = (repo / ".claude/skills/acme-cache/SKILL.md").read_text(encoding="utf-8")
    assert stripped == (
        '---\nname: acme-cache\ndescription: "Cache rules."\n---\n\nCache.\n'
    )


def test_a_literal_entry_is_removed_and_its_comments_stay(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = (
        "# repo agents\nagents:\n  claude: true  # the only one\n\n"
        "skills:\n  # data\n  - stablemate/db   # the pool rules\n  - stablemate/cache\n"
        "# end\n"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-db") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == (
        "# repo agents\nagents:\n  claude: true  # the only one\n\n"
        "skills:\n  # data\n  - stablemate/cache\n# end\n"
    )
    assert check(repo, library) == 0


def test_a_glob_is_replaced_by_the_literals_it_still_matches(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = (
        "agents:\n  claude: true\n"
        "skills:\n  - stablemate/cache\n  - 'stablemate/d*'\n  - stablemate/o*\n"
        "# tail comment\n"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-ostler") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == (
        "agents:\n  claude: true\n"
        "skills:\n  - stablemate/cache\n  - 'stablemate/d*'\n# tail comment\n"
    )
    assert run(repo, library, "eject", "acme-db") == 0
    assert (repo / "agents.yml").read_text(encoding="utf-8") == (
        "agents:\n  claude: true\nskills:\n  - stablemate/cache\n# tail comment\n"
    )
    assert check(repo, library) == 0


def test_a_glob_that_matches_several_keeps_the_others_as_literals(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(
        repo,
        library,
        "agents:\n  claude: true\nskills:\n  - 'stablemate/*'   # all of them\n",
    )

    assert run(repo, library, "eject", "acme-ostler") == 0

    text = (repo / "agents.yml").read_text(encoding="utf-8")
    assert text == (
        "agents:\n  claude: true\nskills:\n  - stablemate/cache\n  - stablemate/db\n"
    )
    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()
    assert (repo / ".claude/skills/acme-ostler/SKILL.md").is_file()
    assert check(repo, library) == 0


def test_a_skill_selected_only_by_a_pack_is_excluded(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = "agents:\n  claude: true  # one\npacks:\n  - core  # the lot\n"
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-db") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == (
        config + "exclude:\n  skills:\n    - stablemate/db\n"
    )
    assert check(repo, library) == 0
    assert (repo / ".claude/skills/acme-cache/SKILL.md").is_file()


def test_an_existing_exclude_list_gains_the_skill(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = (
        "agents:\n  claude: true\npacks:\n  - core\n"
        "exclude:\n  # nothing yet\n  prompts:\n    - nope\n"
        "  skills:\n    - stablemate/ostler  # kept out\n"
        "vars:\n  a: 1\n"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-db") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == config.replace(
        "    - stablemate/ostler  # kept out\n",
        "    - stablemate/ostler  # kept out\n    - stablemate/db\n",
    )
    assert check(repo, library) == 0


def test_an_exclude_without_skills_gains_the_key(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = (
        "agents:\n  claude: true\npacks:\n  - core\n"
        "exclude:\n  prompts:\n    - nope\n"
        "vars:\n  a: 1\n"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-db") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == config.replace(
        "    - nope\n", "    - nope\n  skills:\n    - stablemate/db\n"
    )
    assert check(repo, library) == 0


def test_a_flow_style_skills_list_aborts_before_anything_is_written(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = "agents:\n  claude: true\nskills: [stablemate/db, stablemate/cache]\n"
    install(repo, library, config)
    folder = repo / ".claude/skills/acme-db/SKILL.md"
    before = folder.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        run(repo, library, "eject", "acme-db")

    assert "flow style" in str(excinfo.value)
    assert folder.read_text(encoding="utf-8") == before
    assert (repo / "agents.yml").read_text(encoding="utf-8") == config


def test_two_real_copies_are_refused_until_one_harness_links(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = "agents:\n  claude: true\n  codex: true\nskills:\n  - stablemate/db\n"
    install(repo, library, config)

    with pytest.raises(SystemExit) as excinfo:
        run(repo, library, "eject", "acme-db")

    assert "skills_from" in str(excinfo.value)
    assert is_generated(repo / ".claude/skills/acme-db/SKILL.md")
    assert (repo / "agents.yml").read_text(encoding="utf-8") == config


def test_the_linked_harness_keeps_a_valid_symlink_after_the_eject(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = (
        "agents:\n  claude: true\n  codex:\n    skills_from: claude\n"
        "skills:\n  - stablemate/db\n"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-db") == 0

    link = repo / ".agents/skills/acme-db"
    assert os.readlink(link) == "../../.claude/skills/acme-db"
    assert (link / "SKILL.md").is_file()
    assert check(repo, library) == 0
    assert run(repo, library, "install") == 0
    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()
    assert not is_generated(repo / ".claude/skills/acme-db/SKILL.md")


def test_an_install_after_the_eject_leaves_the_folder_alone(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, "agents:\n  claude: true\nskills:\n  - stablemate/db\n")
    assert run(repo, library, "eject", "acme-db") == 0
    ejected = (repo / ".claude/skills/acme-db/SKILL.md").read_text(encoding="utf-8")

    assert run(repo, library, "install") == 0

    assert (repo / ".claude/skills/acme-db/SKILL.md").read_text(
        encoding="utf-8"
    ) == ejected
    assert (repo / ".claude/skills/acme-db/references/pool.md").is_file()


def test_an_unknown_name_lists_what_can_be_ejected(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(
        repo,
        library,
        "agents:\n  claude: true\nskills:\n  - stablemate/db\n"
        "localInstructions:\n  - policy: house-rules\n    paths: ['.']\n",
    )

    with pytest.raises(SystemExit) as excinfo:
        run(repo, library, "eject", "nope")

    message = str(excinfo.value)
    assert "acme-db" in message
    assert "house-rules" in message


LOCAL = (
    "agents:\n  claude: true\nskills:\n  - stablemate/db\n  - stablemate/ostler\n"
    "localInstructions:\n  - skills: [db, ostler]\n    paths: ['.']\n    includeReadme: false\n"
    "    claudeMd: false\n"
)


def test_local_instructions_embed_the_ejected_skill_as_before(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, LOCAL)
    before = (repo / "AGENTS.md").read_text(encoding="utf-8")

    assert run(repo, library, "eject", "acme-db") == 0

    assert check(repo, library) == 0
    assert run(repo, library, "install") == 0
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == before


def test_source_of_an_instruction_file_names_the_hand_written_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, LOCAL)
    assert run(repo, library, "eject", "acme-db") == 0
    capsys.readouterr()

    assert main(["source", str(repo / "AGENTS.md"), "--library", str(library)]) == 0

    printed = capsys.readouterr().out.splitlines()
    assert str(repo / ".claude/skills/acme-db/SKILL.md") in printed
    assert any(line.endswith("ostler/SKILL.md") for line in printed)


def test_a_library_skill_wins_over_a_hand_written_folder_of_the_same_name(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, LOCAL)
    mine = repo / ".claude/skills/db/SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("---\nname: db\n---\n\nHand written.\n", encoding="utf-8")

    assert run(repo, library, "install") == 0

    assert "Use the pool." in (repo / "AGENTS.md").read_text(encoding="utf-8")


def test_a_skill_in_neither_place_is_still_an_error(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    with pytest.raises(SystemExit) as excinfo:
        install(
            repo,
            library,
            "agents:\n  claude: true\nskills:\n  - stablemate/db\n"
            "localInstructions:\n  - skill: missing\n    paths: ['.']\n",
        )
    assert "missing" in str(excinfo.value)


POLICY_CONFIG = (
    "agents:\n  claude: true\n"
    "skills:\n  - stablemate/db\n"
    "# where the rules go\n"
    "localInstructions:\n"
    "  - policy: house-rules  # always\n"
    "    paths: ['.']\n"
    "    includeReadme: false\n"
)


def instruction_entry(repo: Path, index: int = 0) -> dict:
    return selected_in(repo)["localInstructions"][index]


def test_a_policy_moves_into_an_empty_text(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(repo, library, POLICY_CONFIG)

    assert run(repo, library, "eject", "house-rules") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == (
        POLICY_CONFIG.replace(
            "  - policy: house-rules  # always\n    paths: ['.']\n",
            "  - paths: ['.']\n",
        )
        + "    text: |\n      # House rules\n\n      Commit as you go.\n"
    )
    assert run(repo, library, "install") == 0
    assert check(repo, library) == 0
    assert "Commit as you go." in (repo / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "existing",
    [
        "    text: |\n      Local note.\n\n      Second paragraph.\n",
        '    text: "Local note.\\n\\nSecond paragraph."\n',
        "    text: >\n      Local note.\n\n      Second paragraph.\n",
        "    text: Local note.\n",
    ],
)
def test_a_policy_is_prepended_to_whatever_text_exists(
    tmp_path: Path, existing: str
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = POLICY_CONFIG + existing + "vars:\n  a: 1\n"
    install(repo, library, config)
    old = instruction_entry(repo)["text"]

    assert run(repo, library, "eject", "house-rules") == 0

    entry = instruction_entry(repo)
    assert "policy" not in entry
    assert (
        entry["text"]
        == "# House rules\n\nCommit as you go.\n\n" + old.strip("\n") + "\n"
    )
    assert selected_in(repo)["vars"] == {"a": 1}
    assert run(repo, library, "install") == 0
    assert check(repo, library) == 0


def test_a_policy_leaves_the_other_policies_of_the_entry(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = (
        "agents:\n  claude: true\nskills:\n  - stablemate/db\n"
        "localInstructions:\n"
        "  - policies:\n      - house-rules\n      - linking   # second\n"
        "    paths: ['.']\n    includeReadme: false\n"
        "  - policies: [linking, house-rules]\n    paths: ['.']\n    includeReadme: false\n"
        "  - skill: db\n    paths: ['.']\n"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "house-rules") == 0

    text = (repo / "agents.yml").read_text(encoding="utf-8")
    assert "  - policies:\n      - linking   # second\n" in text
    assert "policies: [linking]\n" in text
    assert instruction_entry(repo, 2) == {"skill": "db", "paths": ["."]}
    assert instruction_entry(repo, 0)["text"].startswith("# House rules")
    assert instruction_entry(repo, 1)["text"].startswith("# House rules")
    assert run(repo, library, "install") == 0
    assert check(repo, library) == 0


def test_the_policy_is_rendered_with_the_entrys_own_paths(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    (repo / "pkg").mkdir(parents=True)
    config = (
        "agents:\n  claude: true\nskills:\n  - stablemate/db\n"
        "localInstructions:\n  - policy: linking\n    paths: [pkg]\n    includeReadme: false\n"
    )
    install(repo, library, config)
    before = (repo / "pkg/AGENTS.md").read_text(encoding="utf-8")

    assert run(repo, library, "eject", "linking") == 0

    assert instruction_entry(repo)["text"] == before
    assert "../.claude/skills/acme-db/SKILL.md" in before


def test_a_policy_that_renders_differently_per_path_is_refused(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    (repo / "pkg").mkdir(parents=True)
    config = (
        "agents:\n  claude: true\nskills:\n  - stablemate/db\n"
        "localInstructions:\n  - policy: linking\n    paths: [., pkg]\n    includeReadme: false\n"
    )
    install(repo, library, config)

    with pytest.raises(SystemExit) as excinfo:
        run(repo, library, "eject", "linking")

    assert "renders differently" in str(excinfo.value)
    assert (repo / "agents.yml").read_text(encoding="utf-8") == config


def test_a_skill_folder_name_beats_a_policy_of_the_same_name(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = POLICY_CONFIG.replace("house-rules", "acme-db")
    (library / "library" / "policies" / "stablemate" / "acme-db.md").write_text(
        POLICY, encoding="utf-8"
    )
    install(repo, library, config)

    assert run(repo, library, "eject", "acme-db") == 0

    assert not is_generated(repo / ".claude/skills/acme-db/SKILL.md")
    assert "policy: acme-db" in (repo / "agents.yml").read_text(encoding="utf-8")


def test_eject_reinstalls_the_user_library_into_the_given_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    config = tmp_path / "stablemate.toml"
    config.write_text(
        'config_version = 1\n\n[user_library.claude]\nskills = ["stablemate/cache"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    repo = tmp_path / "acme"
    home = tmp_path / "home"
    install(repo, library, "agents:\n  claude: true\nskills:\n  - stablemate/db\n")

    assert main(
        ["eject", "acme-db", "--repo", str(repo), "--library", str(library),
         "--home", str(home)]
    ) == 0

    assert (home / ".claude/skills/cache/SKILL.md").is_file()


def test_a_reference_to_an_ejected_skill_by_its_installed_name_still_resolves(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    skills = library / "library" / "skills" / "stablemate"
    (skills / "acme-auth.md").write_text(
        "---\nname: acme-auth\ndescription: Auth.\n---\n\nAuth.\n", encoding="utf-8"
    )
    (skills / "web.md").write_text(
        "---\nname: web\ndescription: Web.\n---\n\n"
        "Read {{ skill_link('acme-auth') }}.\n"
        "{% if has_skill('acme-auth') %}Auth is installed.{% endif %}\n",
        encoding="utf-8",
    )
    repo = tmp_path / "acme"
    install(
        repo,
        library,
        "agents:\n  claude: true\nskills:\n  - stablemate/acme-auth\n  - stablemate/web\n",
    )
    web = repo / ".claude/skills/acme-web/SKILL.md"
    before = web.read_text(encoding="utf-8")
    assert "[acme-auth](../acme-auth/SKILL.md)" in before
    assert "Auth is installed." in before

    assert run(repo, library, "eject", "acme-auth") == 0

    assert web.read_text(encoding="utf-8") == before
    assert check(repo, library) == 0


def test_a_hand_written_skill_embedded_in_an_instruction_file_keeps_its_links(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    skills = library / "library" / "skills" / "stablemate"
    (skills / "ostler" / "SKILL.md").write_text(
        "---\nname: ostler\ndescription: Ostler rules.\n---\n\n# Ostler\n\n"
        "Also [db]({{ skill_path('db') }}), [cache][c], ![pic]({{ skill_path('db') }}) and "
        "`[code](keep.md)`, [site](https://example.com/x), [home](~/x.md) and "
        "[top](#top).\n\n[c]: {{ skill_path('db') }}\n\n```\n[fenced](keep.md)\n```\n",
        encoding="utf-8",
    )
    repo = tmp_path / "acme"
    (repo / "web").mkdir(parents=True)
    config = (
        "agents:\n  claude: true\nskills:\n  - stablemate/db\n  - stablemate/ostler\n"
        "localInstructions:\n  - skills: [ostler]\n    paths: ['.', web]\n"
        "    includeReadme: false\n    claudeMd: false\n"
    )
    install(repo, library, config)
    roots = [repo / "AGENTS.md", repo / "web/AGENTS.md"]
    before = [path.read_text(encoding="utf-8") for path in roots]
    assert "[db](.claude/skills/acme-db/SKILL.md)" in before[0]
    assert "[db](../.claude/skills/acme-db/SKILL.md)" in before[1]

    assert run(repo, library, "eject", "acme-ostler") == 0

    for path, text in zip(roots, before, strict=True):
        after = path.read_text(encoding="utf-8")
        assert after.split("-->", 1)[-1] == text.split("-->", 1)[-1]
    assert "`[code](keep.md)`" in roots[0].read_text(encoding="utf-8")
    assert "[fenced](keep.md)" in roots[0].read_text(encoding="utf-8")


def test_ejecting_the_last_selected_skill_removes_the_bare_key(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    install(
        repo,
        library,
        "agents:\n  claude: true\n# the skills\nskills:\n  - stablemate/db\npacks: []\n",
    )

    assert run(repo, library, "eject", "acme-db") == 0

    assert (repo / "agents.yml").read_text(encoding="utf-8") == (
        "agents:\n  claude: true\n# the skills\npacks: []\n"
    )


def test_a_tag_search_still_finds_an_ejected_skill(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    skills = library / "library" / "skills" / "stablemate"
    (skills / "ops.md").write_text(
        "---\nname: ops\ndescription: Ops.\ntags: [runbook, other]\n---\n\nOps.\n",
        encoding="utf-8",
    )
    (skills / "qa.md").write_text(
        "---\nname: qa\ndescription: QA.\n---\n\n"
        "Runbooks: {{ find_by_tags('runbook') | default('none') }}\n",
        encoding="utf-8",
    )
    repo = tmp_path / "acme"
    install(
        repo,
        library,
        "agents:\n  claude: true\nskills:\n  - stablemate/ops\n  - stablemate/qa\n",
    )
    qa = repo / ".claude/skills/acme-qa/SKILL.md"
    before = qa.read_text(encoding="utf-8")
    assert "[acme-ops](../acme-ops/SKILL.md)" in before

    assert run(repo, library, "eject", "acme-ops") == 0

    assert qa.read_text(encoding="utf-8") == before
