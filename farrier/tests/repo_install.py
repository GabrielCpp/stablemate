"""Setup shared by the tests that run `farrier install --repo` against a temporary folder."""

from pathlib import Path

from farrier import cli
from farrier._vendor.stablemate_core.schema import HomeConfig
from farrier.install import set_layers


def configured(monkeypatch, library: Path, tmp_path: Path, skill: str = "demo/plain") -> Path:
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
