"""Setup shared by the tests that run `farrier install --repo` against a temporary folder."""

from pathlib import Path

from farrier import cli
from farrier._vendor.stablemate_core.schema import HomeConfig
from farrier.install import main, set_layers


def configured(
    monkeypatch, library: Path, tmp_path: Path, skill: str = "demo/plain"
) -> Path:
    """A folder whose agents.yml selects the library's one skill."""
    monkeypatch.setattr(cli, "resolve_library_dir", lambda _cli: library)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(cli, "load_home_config", lambda: HomeConfig())
    set_layers(library)
    root = tmp_path / "demo"
    root.mkdir()
    (root / "agents.yml").write_text(
        f"agents:\n  claude: true\nskills:\n  - {skill}\n", encoding="utf-8"
    )
    return root


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills"
    skills.mkdir(parents=True)
    (skills / "review.md").write_text(
        "---\nname: review\ndescription: Review.\n---\n\nReview.\n", encoding="utf-8"
    )
    (skills / "ship.md").write_text(
        "---\nname: ship\ndescription: Ship.\n---\n\nThen {{ skill_command('review') }}.\n",
        encoding="utf-8",
    )
    prompts = library / "library" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "go.md").write_text(
        "---\ndescription: Go.\n---\n\nGo ahead.\n", encoding="utf-8"
    )
    (library / "packs").mkdir()
    return library


def install(tmp_path: Path, config: str, *extra: str) -> tuple[int, Path]:
    library = (
        make_library(tmp_path)
        if not (tmp_path / "agents").exists()
        else tmp_path / "agents"
    )
    repo = tmp_path / "acme"
    repo.mkdir(exist_ok=True)
    (repo / "agents.yml").write_text(config, encoding="utf-8")
    code = main(["install", "--repo", str(repo), "--library", str(library), *extra])
    return code, repo


def shipped(repo: Path) -> str:
    return (repo / ".agents/skills/acme-ship/SKILL.md").read_text(encoding="utf-8")
