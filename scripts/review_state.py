"""What the review gate remembers between stops, kept beside the repo's git state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from review_git import git_path
from review_verdict import Verdict

HOOK_STATE_FILE = "review-gate.json"
BASE_STATE_FILE = "review-gate-base.json"


@dataclass(frozen=True)
class GateState:
    base_tree: str | None
    base_head: str | None
    blocked_rounds: int


EMPTY_STATE = GateState(base_tree=None, base_head=None, blocked_rounds=0)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def load_state(repo: Path, name: str) -> GateState:
    path = git_path(repo, name)
    if not path.is_file():
        return EMPTY_STATE
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return EMPTY_STATE
    rounds = raw.get("blocked_rounds")
    return GateState(
        base_tree=_text_or_none(raw.get("base_tree")),
        base_head=_text_or_none(raw.get("base_head")),
        blocked_rounds=rounds if isinstance(rounds, int) else 0,
    )


def save_state(repo: Path, name: str, state: GateState) -> None:
    body = {
        "base_tree": state.base_tree,
        "base_head": state.base_head,
        "blocked_rounds": state.blocked_rounds,
    }
    git_path(repo, name).write_text(json.dumps(body) + "\n", encoding="utf-8")


def next_state(state: GateState, base_tree: str, tree: str, head: str, verdict: Verdict) -> GateState:
    if verdict.passed:
        return GateState(base_tree=tree, base_head=head, blocked_rounds=0)
    return GateState(
        base_tree=base_tree,
        base_head=state.base_head or head,
        blocked_rounds=state.blocked_rounds + 1,
    )
