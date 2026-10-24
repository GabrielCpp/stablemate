"""The scripted trend-report agent and the helpers the `review-debt` tests share."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class ScriptedReports:
    """Answers each `review-register` turn with the next report in the script."""

    def __init__(self, *replies: dict[str, Any]) -> None:
        self.replies = list(replies)
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        self.args.append(ctx.as_dict())
        return f"(scripted) {node.prompt}", self.replies[len(self.args) - 1]

    @property
    def turns(self) -> int:
        return len(self.args)


def report(*clusters: list[str], singletons: tuple[str, ...] = ()) -> dict[str, Any]:
    """A trend report grouping each list of ids as a cluster and each singleton alone."""
    return {
        "clusters": [
            {"name": f"cause {n}", "cause": f"the same flaw {n}", "ids": ids}
            for n, ids in enumerate(clusters, 1)
        ],
        "singletons": [{"id": i, "cause": f"its own flaw {i}"} for i in singletons],
        "summary": "Two flaws recur.",
    }


def git_out(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def trend_ids(text: str) -> list[str]:
    """The ids of every `- <id> ` line of a rendered trends file."""
    return [line[2:].split(" ", 1)[0] for line in text.splitlines() if line.startswith("- ")]
