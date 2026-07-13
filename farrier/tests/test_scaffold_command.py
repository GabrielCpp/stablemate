"""farrier scaffold — YAML scaffold definitions rendered on demand.

Scaffolds are no longer install-time file copies: `scaffolds/*.yml` in the
library define parameterized file trees, `agents.yml → scaffolds:` lists the
ids a repo may use, and `farrier scaffold <id> --param k=v` seeds the files
(never overwriting existing ones).
"""

from pathlib import Path

import pytest

from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    (library / "library" / "skills").mkdir(parents=True)
    (library / "packs").mkdir()
    (library / "scaffolds").mkdir()
    return library


def write_scaffold(library: Path, name: str, content: str) -> None:
    (library / "scaffolds" / f"{name}.yml").write_text(content, encoding="utf-8")


GO_SERVICE = """\
go-service:
  description: Seed a Go service folder.
  params:
    dir: api
  tree:
    $dir/.gitignore: |
      bin/
      dist/
    $dir/docs/README.md: |
      # $repo_title service ($repo_name)
    $dir/docs/specs/.gitkeep: ''
"""


def run(argv: list[str]) -> int:
    return main(argv)


def test_scaffold_writes_tree_with_defaults(tmp_path: Path, capsys) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "my-repo"
    repo.mkdir()

    assert (
        run(["scaffold", "go-service", "--repo", str(repo), "--library", str(library)])
        == 0
    )

    assert (repo / "api/.gitignore").read_text() == "bin/\ndist/\n"
    readme = (repo / "api/docs/README.md").read_text()
    assert readme == "# My Repo service (my-repo)\n"
    assert (repo / "api/docs/specs/.gitkeep").exists()
    out = capsys.readouterr().out
    assert "created: api/.gitignore" in out


def test_scaffold_param_override_redirects_dir(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "repo"
    repo.mkdir()

    run(
        [
            "scaffold",
            "go-service",
            "--param",
            "dir=backend",
            "--repo",
            str(repo),
            "--library",
            str(library),
        ]
    )

    assert (repo / "backend/.gitignore").exists()
    assert not (repo / "api").exists()


def test_scaffold_never_overwrites_existing_files(tmp_path: Path, capsys) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "repo"
    (repo / "api").mkdir(parents=True)
    (repo / "api/.gitignore").write_text("mine\n", encoding="utf-8")

    run(["scaffold", "go-service", "--repo", str(repo), "--library", str(library)])

    assert (repo / "api/.gitignore").read_text() == "mine\n"
    assert "exists (kept): api/.gitignore" in capsys.readouterr().out


def test_scaffold_required_param_missing_errors(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(
        library,
        "svc",
        "svc:\n  params:\n    name: ~\n  tree:\n    $name/main.go: |\n      package main\n",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit, match="requires --param for: name"):
        run(["scaffold", "svc", "--repo", str(repo), "--library", str(library)])


def test_scaffold_unknown_param_errors(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit, match="does not accept param"):
        run(
            [
                "scaffold",
                "go-service",
                "--param",
                "folder=x",
                "--repo",
                str(repo),
                "--library",
                str(library),
            ]
        )


def test_scaffold_unknown_id_errors(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit, match="Unknown scaffold: 'nope'"):
        run(["scaffold", "nope", "--repo", str(repo), "--library", str(library)])


def test_agents_yml_scaffolds_list_gates_availability(tmp_path: Path) -> None:
    """With an agents.yml present, only ids listed there (or via packs) run."""
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    write_scaffold(
        library, "docs", "shared-docs:\n  tree:\n    docs/.gitkeep: ''\n"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\nscaffolds:\n  - go-service\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="not enabled for this repo"):
        run(["scaffold", "shared-docs", "--repo", str(repo), "--library", str(library)])

    assert (
        run(["scaffold", "go-service", "--repo", str(repo), "--library", str(library)])
        == 0
    )


def test_pack_scaffolds_contribute_available_ids(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(
        library, "docs", "shared-docs:\n  tree:\n    docs/.gitkeep: ''\n"
    )
    (library / "packs" / "docs.yml").write_text(
        "description: docs\nscaffolds:\n  - shared-docs\n", encoding="utf-8"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\npacks:\n  - docs\n", encoding="utf-8"
    )

    assert (
        run(["scaffold", "shared-docs", "--repo", str(repo), "--library", str(library)])
        == 0
    )
    assert (repo / "docs/.gitkeep").exists()


def test_no_agents_yml_allows_every_library_scaffold(tmp_path: Path) -> None:
    """Bootstrapping a repo from scratch: no agents.yml yet, all ids usable."""
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "fresh"
    repo.mkdir()

    assert (
        run(["scaffold", "go-service", "--repo", str(repo), "--library", str(library)])
        == 0
    )


def test_scaffold_empty_dirs_null_and_empty_mapping(tmp_path: Path, capsys) -> None:
    """A bare `key:` (null) or `key: {}` tree node creates an empty directory."""
    library = make_library(tmp_path)
    write_scaffold(
        library,
        "svc",
        (
            "svc:\n"
            "  params:\n"
            "    dir: api\n"
            "  tree:\n"
            "    $dir/logs:\n"          # null value
            "    $dir/cache: {}\n"      # empty mapping
            "    $dir/main.go: |\n"
            "      package main\n"
        ),
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    assert run(["scaffold", "svc", "--repo", str(repo), "--library", str(library)]) == 0

    assert (repo / "api/logs").is_dir()
    assert (repo / "api/cache").is_dir()
    out = capsys.readouterr().out
    assert "created: api/logs/" in out
    assert "created: api/cache/" in out

    # Re-run: existing directories are kept and reported, never an error.
    run(["scaffold", "svc", "--repo", str(repo), "--library", str(library)])
    assert "exists (kept): api/logs/" in capsys.readouterr().out


def test_scaffold_list_shows_ids_and_params(tmp_path: Path, capsys) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "go-service", GO_SERVICE)
    repo = tmp_path / "repo"
    repo.mkdir()

    run(["scaffold", "--list", "--repo", str(repo), "--library", str(library)])

    out = capsys.readouterr().out
    assert "go-service — Seed a Go service folder." in out
    assert "--param dir=...  (default: api)" in out


def test_scaffold_url_node_downloads_content(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    remote = tmp_path / "remote.gitignore"
    remote.write_text("node_modules/\n", encoding="utf-8")
    write_scaffold(
        library,
        "web",
        f"web:\n  tree:\n    .gitignore: {{ url: 'file://{remote}' }}\n",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    run(["scaffold", "web", "--repo", str(repo), "--library", str(library)])

    assert (repo / ".gitignore").read_text() == "node_modules/\n"


def test_duplicate_scaffold_id_across_files_errors(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(library, "a", "dup:\n  tree:\n    x: 'x'\n")
    write_scaffold(library, "b", "dup:\n  tree:\n    y: 'y'\n")
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit, match="Duplicate scaffold id 'dup'"):
        run(["scaffold", "--list", "--repo", str(repo), "--library", str(library)])


def test_path_escaping_repo_errors(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    write_scaffold(
        library,
        "svc",
        "svc:\n  params:\n    dir: api\n  tree:\n    $dir/x.txt: 'x'\n",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit, match="resolves outside the repo"):
        run(
            [
                "scaffold",
                "svc",
                "--param",
                "dir=../escape",
                "--repo",
                str(repo),
                "--library",
                str(library),
            ]
        )


def test_legacy_mapping_scaffold_entry_rejected(tmp_path: Path) -> None:
    """The old `{source-prefix: dest}` install-time form fails with a hint."""
    library = make_library(tmp_path)
    skill = library / "library" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\nskills:\n  - demo\nscaffolds:\n  - flutter: app\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="must be scaffold ids"):
        run(["install", "--repo", str(repo), "--library", str(library)])
