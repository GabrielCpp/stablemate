"""Run one review turn on the claude CLI, with no tool that can write."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from review_verdict import VERDICT_SCHEMA, Reviewer, ReviewError, Verdict, findings_from_output

MAX_TURNS = 40
TIMEOUT_SECONDS = 900


def claude_reviewer(repo: Path) -> Reviewer:
    def review(prompt: str, model: str) -> Verdict:
        command = [
            "claude", "-p",
            "--model", model,
            "--max-turns", str(MAX_TURNS),
            "--tools", "Read,Grep,Glob",
            "--setting-sources", "user",
            "--settings", json.dumps({"disableAllHooks": True}),
            "--json-schema", json.dumps(VERDICT_SCHEMA),
            "--output-format", "json",
            "--no-session-persistence",
        ]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                cwd=repo,
                check=False,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise ReviewError(f"the reviewer ran past {TIMEOUT_SECONDS} seconds") from exc
        except OSError as exc:
            raise ReviewError(str(exc)) from exc
        return Verdict(model=model, findings=findings_from_output(completed))

    return review
