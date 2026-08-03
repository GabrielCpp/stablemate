"""The install prefix is the repo directory's name, and nothing else can set it.

`agents.yml` used to accept `repo.prefix` / `repo.name` as an override. That made the
*names of the generated files* a function of a committed config value rather than of the
checkout, so the same `agents.yml` rendered a different file set in a clone under a
different directory name — and the workflow kit, which keys a repo by its directory,
disagreed with the skills installed into it. The prefix is derived now; these tests are
what keeps it that way.
"""

from pathlib import Path

import pytest

from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nBody.\n", encoding="utf-8"
    )
    (library / "library" / "prompts").mkdir(parents=True)
    (library / "packs").mkdir()
    return library


def install(repo: Path, library: Path, config: str) -> int:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(config, encoding="utf-8")
    return main(["install", "--repo", str(repo), "--library", str(library)])


AGENTS = "agents:\n  claude: true\nskills:\n  - demo/db\n"


def test_the_prefix_is_the_repo_directory_name(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"

    assert install(repo, library, AGENTS) == 0

    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()


def test_a_directory_name_is_kebab_cased_into_the_prefix(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "Acme_Web App"

    assert install(repo, library, AGENTS) == 0

    assert (repo / ".claude/skills/acme-web-app-db/SKILL.md").is_file()


@pytest.mark.parametrize("key", ["name", "prefix"])
def test_agents_yml_cannot_override_the_prefix(tmp_path: Path, key: str) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"

    assert install(repo, library, f"repo:\n  {key}: globex\n" + AGENTS) == 0

    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()
    assert not (repo / ".claude/skills/globex-db").exists()


def test_other_repo_keys_still_reach_the_template_context(tmp_path: Path) -> None:
    """Only `name`/`prefix`/`root` are reserved; `repo:` is still a passthrough."""
    library = make_library(tmp_path)
    (library / "library" / "skills" / "demo" / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nMail {{ repo.support_email }}.\n",
        encoding="utf-8",
    )
    repo = tmp_path / "acme"

    assert install(repo, library, "repo:\n  support_email: team@example.com\n" + AGENTS) == 0

    body = (repo / ".claude/skills/acme-db/SKILL.md").read_text(encoding="utf-8")
    assert "Mail team@example.com." in body
