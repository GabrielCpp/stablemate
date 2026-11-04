"""What the repo-level guard scripts share: the tracked-file listing, the `.agent-checks.toml` declarations and the `--root` argument."""

from __future__ import annotations

import argparse
import subprocess
import tomllib
from pathlib import Path


def tracked_files(repo: Path, roots: tuple[str, ...]) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", *roots],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [repo / p for p in out.split("\0") if p]


def declarations(root: Path, config_name: str, table: str) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`."""
    config = root / config_name
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(table, {})


def root_argument(description: str | None, config_name: str) -> Path:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help=f"repo holding {config_name} (default: cwd)"
    )
    return parser.parse_args().root
