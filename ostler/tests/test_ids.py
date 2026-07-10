"""Id-prefix derivation: ostler owns the prefix, tied to the CWD repo's name."""

from __future__ import annotations

import json
from pathlib import Path

from ostler import ids
from ostler.model import load


def _repo(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    return root


def test_prefix_is_first_four_letters_of_repo_name_uppercased(tmp_path: Path):
    root = _repo(tmp_path, "stablemate")
    assert ids.allocate(load(root)) == "STAB-1"
    registry = json.loads((root / ".agents/ids.json").read_text())
    assert registry == {"prefix": "STAB", "counter": 2}


def test_prefix_skips_non_alphanumerics_and_handles_short_names(tmp_path: Path):
    assert ids.allocate(load(_repo(tmp_path, "my-app"))) == "MYAP-1"
    assert ids.allocate(load(_repo(tmp_path, "ai"))) == "AI-1"


def test_explicit_prefix_overrides_and_registry_pins_it(tmp_path: Path):
    root = _repo(tmp_path, "stablemate")
    assert ids.allocate(load(root), prefix="pred") == "pred-1"
    # once minted, the registry prefix is pinned — later allocations keep it
    assert ids.allocate(load(root)) == "pred-2"
