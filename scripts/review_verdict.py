"""What a reviewer returns, and how the gate reads it out of the reviewer's output."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "rule": {"type": "string"},
                    "problem": {"type": "string"},
                },
                "required": ["file", "line", "rule", "problem"],
            },
        }
    },
    "required": ["findings"],
}


class ReviewError(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    problem: str

    def render(self) -> str:
        return f"{self.file}:{self.line} [{self.rule}] {self.problem}"


@dataclass(frozen=True)
class Verdict:
    model: str
    findings: tuple[Finding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings


Reviewer = Callable[[str, str], Verdict]


def parse_findings(structured: object) -> tuple[Finding, ...]:
    items = structured.get("findings") if isinstance(structured, dict) else None
    if not isinstance(items, list):
        raise ReviewError(f"the reviewer returned no findings list: {structured!r}")
    return tuple(_finding(item) for item in items)


def _finding(item: object) -> Finding:
    if not isinstance(item, dict):
        raise ReviewError(f"the reviewer returned a malformed finding: {item!r}")
    file, line, rule, problem = (item.get(key) for key in ("file", "line", "rule", "problem"))
    if not (isinstance(file, str) and isinstance(line, int) and isinstance(rule, str) and isinstance(problem, str)):
        raise ReviewError(f"the reviewer returned a finding with a missing or mistyped field: {item!r}")
    return Finding(file=file, line=line, rule=rule, problem=problem)


def findings_from_output(completed: subprocess.CompletedProcess[str]) -> tuple[Finding, ...]:
    try:
        payload: object = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"exit {completed.returncode}: {completed.stderr.strip()[-500:]}") from exc
    if not isinstance(payload, dict) or payload.get("is_error"):
        raise ReviewError(f"the reviewer failed: {str(payload)[-500:]}")
    return parse_findings(payload.get("structured_output"))
