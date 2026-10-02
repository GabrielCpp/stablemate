"""The install prefix is agents.yml's `repo.name` when set, else the repo directory's name."""

from pathlib import Path

from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills"
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


AGENTS = "agents:\n  claude: true\nskills:\n  - db\n"


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


def test_agents_yml_repo_name_sets_the_prefix_whatever_the_directory(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme-worktree"

    assert install(repo, library, "repo:\n  name: Globex_App\n" + AGENTS) == 0

    assert (repo / ".claude/skills/globex-app-db/SKILL.md").is_file()
    assert not (repo / ".claude/skills/acme-worktree-db").exists()


def test_a_named_repo_checks_clean_under_another_directory(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    config = "repo:\n  name: globex\n" + AGENTS
    clone = tmp_path / "globex"
    worktree = tmp_path / "feature-branch"

    assert install(clone, library, config) == 0
    assert install(worktree, library, config) == 0

    assert main(["install", "--repo", str(worktree), "--library", str(library), "--check"]) == 0
    assert sorted(p.name for p in (worktree / ".claude/skills").iterdir()) == ["globex-db"]


def test_agents_yml_repo_prefix_is_not_a_second_name(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"

    assert install(repo, library, "repo:\n  prefix: globex\n" + AGENTS) == 0

    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()
    assert not (repo / ".claude/skills/globex-db").exists()


def test_other_repo_keys_still_reach_the_template_context(tmp_path: Path) -> None:
    """Beyond `name`, `prefix` and `root`, `repo:` is a passthrough."""
    library = make_library(tmp_path)
    (library / "library" / "skills" / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nMail {{ repo.support_email }}.\n",
        encoding="utf-8",
    )
    repo = tmp_path / "acme"

    assert install(repo, library, "repo:\n  support_email: team@example.com\n" + AGENTS) == 0

    body = (repo / ".claude/skills/acme-db/SKILL.md").read_text(encoding="utf-8")
    assert "Mail team@example.com." in body
