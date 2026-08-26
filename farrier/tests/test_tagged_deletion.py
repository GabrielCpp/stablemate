"""farrier deletes what it generated, and refuses to overwrite what it did not.

The installer used to prune by location: every file under `.claude/skills/` and its
siblings was removed before each render, on the assumption that anything living there
was farrier's. A hand-written skill kept next to the generated ones vanished on the
next install with nothing to notice. Ownership is read off the file now — the
`metadata.generated_by: farrier` block, or the DO-NOT-EDIT comment on the files that
cannot carry front matter — and these tests are what keeps it that way.
"""

from pathlib import Path

import pytest

from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills"
    skills.mkdir(parents=True)
    (skills / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nBody.\n", encoding="utf-8"
    )
    (skills / "cache.md").write_text(
        "---\nname: cache\ndescription: Another skill.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (library / "library" / "prompts").mkdir(parents=True)
    (library / "packs").mkdir()
    return library


def install(repo: Path, library: Path, config: str) -> int:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(config, encoding="utf-8")
    return main(["install", "--repo", str(repo), "--library", str(library)])


BOTH = "agents:\n  claude: true\nskills:\n  - db\n  - cache\n"
ONE = "agents:\n  claude: true\nskills:\n  - db\n"

HANDWRITTEN = "---\nname: mine\ndescription: Hand written.\n---\n\nMine.\n"


def test_a_hand_written_skill_survives_an_install(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, ONE) == 0

    mine = repo / ".claude/skills/mine/SKILL.md"
    mine.parent.mkdir()
    mine.write_text(HANDWRITTEN, encoding="utf-8")

    assert install(repo, library, ONE) == 0

    assert mine.read_text(encoding="utf-8") == HANDWRITTEN


def test_a_deselected_skill_is_still_removed(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, BOTH) == 0
    assert (repo / ".claude/skills/acme-cache/SKILL.md").is_file()

    assert install(repo, library, ONE) == 0

    # The whole directory goes, not just the SKILL.md — a folder left behind is what
    # --check would then report as a stray nobody can render away.
    assert not (repo / ".claude/skills/acme-cache").exists()
    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()


def test_an_untagged_file_at_an_output_path_aborts_the_whole_install(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    repo.mkdir()
    held = repo / ".claude/skills/acme-db/SKILL.md"
    held.parent.mkdir(parents=True)
    held.write_text(HANDWRITTEN, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, ONE)

    message = str(excinfo.value)
    assert ".claude/skills/acme-db/SKILL.md" in message
    # Nothing was written: the refusal happens before the first delete, so the repo is
    # exactly as the operator left it and their file is still theirs to rename.
    assert held.read_text(encoding="utf-8") == HANDWRITTEN
    assert not (repo / ".claude/commands").exists()


def test_every_conflict_is_reported_not_just_the_first(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    repo.mkdir()
    for name in ["acme-db", "acme-cache"]:
        path = repo / ".claude/skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(HANDWRITTEN, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, BOTH)

    message = str(excinfo.value)
    assert ".claude/skills/acme-db/SKILL.md" in message
    assert ".claude/skills/acme-cache/SKILL.md" in message


def test_a_hand_written_skill_is_not_reported_as_drift(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, ONE) == 0
    (repo / ".claude/skills/mine").mkdir()
    (repo / ".claude/skills/mine/SKILL.md").write_text(HANDWRITTEN, encoding="utf-8")

    # `extra` means "farrier generated this and no longer would". Somebody else's file
    # is not that, and reporting it would fail --check with nothing to fix.
    assert main(["install", "--repo", str(repo), "--library", str(library), "--check"]) == 0


def test_a_stale_generated_skill_is_still_reported_as_drift(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, BOTH) == 0

    (repo / "agents.yml").write_text(ONE, encoding="utf-8")

    assert main(["install", "--repo", str(repo), "--library", str(library), "--check"]) == 1


def test_a_generated_skills_untagged_script_goes_with_it(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    scripts = library / "library" / "skills" / "cache" / "scripts"
    scripts.mkdir(parents=True)
    (library / "library" / "skills" / "cache" / "SKILL.md").write_text(
        "---\nname: cache\ndescription: Another skill.\n---\n\nBody.\n", encoding="utf-8"
    )
    (library / "library" / "skills" / "cache.md").unlink()
    (scripts / "run.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    repo = tmp_path / "acme"

    assert install(repo, library, BOTH) == 0
    # A script runs byte-for-byte as written and carries no marker of its own; it is
    # owned through the SKILL.md bundling it.
    assert (repo / ".claude/skills/acme-cache/scripts/run.sh").is_file()

    assert install(repo, library, ONE) == 0

    assert not (repo / ".claude/skills/acme-cache").exists()


ROOT_CONFIG = "agents:\n  copilot: true\nskills:\n  - db\nroots:\n  - acme\n"


def test_a_root_instruction_file_is_marked_and_reinstallable(tmp_path: Path) -> None:
    """The generated copilot root carries a banner, so farrier owns it on the next pass.

    It is a verbatim render with no front matter to stamp. Unmarked, ownership — which
    reads the file, not the path — would take farrier's own output for hand-written
    instructions and refuse to install over it, which is a repo that can be installed
    once and never again.
    """
    library = make_library(tmp_path)
    roots = library / "library" / "roots"
    roots.mkdir(parents=True)
    (roots / "acme.md").write_text("# Acme\n\nHouse rules.\n", encoding="utf-8")
    repo = tmp_path / "acme"

    assert install(repo, library, ROOT_CONFIG) == 0
    generated = repo / ".github/copilot-instructions.md"
    assert "generated by farrier" in generated.read_text(encoding="utf-8")
    assert "House rules." in generated.read_text(encoding="utf-8")

    assert install(repo, library, ROOT_CONFIG) == 0
    assert main(["install", "--repo", str(repo), "--library", str(library), "--check"]) == 0


def test_a_hand_written_root_instruction_file_aborts_the_install(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    roots = library / "library" / "roots"
    roots.mkdir(parents=True)
    (roots / "acme.md").write_text("# Acme\n\nHouse rules.\n", encoding="utf-8")
    repo = tmp_path / "acme"
    (repo / ".github").mkdir(parents=True)
    (repo / ".github/copilot-instructions.md").write_text("Mine.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, ROOT_CONFIG)

    assert ".github/copilot-instructions.md" in str(excinfo.value)


def test_a_root_source_with_front_matter_keeps_its_fence_on_line_one(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    roots = library / "library" / "roots"
    roots.mkdir(parents=True)
    (roots / "acme.md").write_text(
        "---\napplyTo: '**'\n---\n\n# Acme\n", encoding="utf-8"
    )
    repo = tmp_path / "acme"

    assert install(repo, library, ROOT_CONFIG) == 0

    text = (repo / ".github/copilot-instructions.md").read_text(encoding="utf-8")
    assert text.startswith("---\napplyTo: '**'\n---\n")
    assert "generated by farrier" in text


LOCAL_CONFIG = (
    "agents:\n  claude: true\n"
    "skills:\n  - db\n"
    "localInstructions:\n"
    "  - skill: acme-db\n"
    "    paths:\n"
    '      - "."\n'
)


def test_the_aggregated_agents_md_can_be_regenerated(tmp_path: Path) -> None:
    """AGENTS.md carries no banner on purpose, which makes the second install the
    interesting one: ownership is judged by reading the file, and there is nothing in
    this one to read. It has to be recognised as farrier's anyway, or the installer
    reads back its own output as a hand-written rules file and refuses outright —
    leaving `farrier install` permanently broken in every repo that maps one.
    """
    library = make_library(tmp_path)
    repo = tmp_path / "acme"

    assert install(repo, library, LOCAL_CONFIG) == 0
    assert (repo / "AGENTS.md").is_file()

    assert install(repo, library, LOCAL_CONFIG) == 0


def test_a_hand_written_agents_md_is_still_overwritten(tmp_path: Path) -> None:
    """The cost of the exemption above, stated so it is a decision and not a surprise:
    a repo that hand-wrote AGENTS.md before adopting farrier and then maps that
    directory loses it. The CLAUDE.md pointer beside it is refused instead — it carries
    a banner, so it is judged by the ordinary rule.
    """
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("Mine.\n", encoding="utf-8")

    assert install(repo, library, LOCAL_CONFIG) == 0

    assert (repo / "AGENTS.md").read_text(encoding="utf-8") != "Mine.\n"
