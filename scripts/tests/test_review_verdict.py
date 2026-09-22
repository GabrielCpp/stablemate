"""How the gate reads a verdict out of the reviewer's output."""

from __future__ import annotations

import json
import subprocess

import pytest
from review_verdict import Finding, ReviewError, findings_from_output


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["claude"], returncode=0, stdout=stdout, stderr="")


def test_structured_output_becomes_findings() -> None:
    payload = {
        "is_error": False,
        "structured_output": {
            "findings": [{"file": "a.py", "line": 3, "rule": "too-large", "problem": "split it"}]
        },
    }
    findings = findings_from_output(_completed(json.dumps(payload)))
    assert findings == (Finding(file="a.py", line=3, rule="too-large", problem="split it"),)


@pytest.mark.parametrize(
    "stdout",
    [
        "not json",
        json.dumps({"is_error": True, "result": "boom"}),
        json.dumps({"is_error": False, "structured_output": {"verdict": "pass"}}),
        json.dumps({"is_error": False, "structured_output": {"findings": ["loose text"]}}),
        json.dumps({"is_error": False, "structured_output": {"findings": [{"file": "a.py", "line": 3}]}}),
        json.dumps(
            {
                "is_error": False,
                "structured_output": {
                    "findings": [{"file": "a.py", "line": "3", "rule": "too-large", "problem": "x"}]
                },
            }
        ),
    ],
)
def test_output_the_gate_cannot_read_is_a_review_error(stdout: str) -> None:
    with pytest.raises(ReviewError):
        findings_from_output(_completed(stdout))
