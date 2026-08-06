"""Tests for the shared secret-redaction filter (runner/redact.py) and its mount at
process.stream_subprocess. Runnable two ways:
    ./.venv/bin/python -m pytest tests/test_redact.py
"""
from __future__ import annotations

import base64
import json
import sys

from workhorse.config_run import AgentResilience
from workhorse.runner import process
from workhorse.runner.redact import REDACTED, SecretRedactor


def test_redacts_the_raw_secret_value():
    redactor = SecretRedactor(["hunter2"])
    assert redactor.redact("login failed for hunter2\n") == f"login failed for {REDACTED}\n"


def test_redacts_base64_authorization_header_form():
    secret = "hunter2"
    redactor = SecretRedactor([secret])
    encoded = base64.b64encode(secret.encode()).decode()
    line = f"Authorization: Basic {encoded}\n"
    out = redactor.redact(line)
    assert encoded not in out
    assert REDACTED in out


def test_redacts_url_encoded_form():
    secret = "a b/c+d"
    redactor = SecretRedactor([secret])
    import urllib.parse

    encoded = urllib.parse.quote(secret, safe="")
    out = redactor.redact(f"redirected with token={encoded}")
    assert encoded not in out
    assert REDACTED in out


def test_redacts_json_escaped_form():
    secret = "a/b"
    redactor = SecretRedactor([secret])
    line = json.dumps({"token": secret})
    out = redactor.redact(line)
    assert secret not in out
    assert REDACTED in out


def test_holds_back_tail_across_a_split_value():
    secret = "sUp3rSecretValue1234567890"
    redactor = SecretRedactor([secret])
    half = len(secret) // 2
    first = redactor.feed(f"the value is {secret[:half]}")
    second = redactor.feed(secret[half:] + " end")
    out = first + second + redactor.flush()
    assert secret not in out
    assert REDACTED in out


def test_prefix_heuristic_catches_truncated_echo_with_no_known_secrets():
    redactor = SecretRedactor([])
    out = redactor.redact("error: invalid key sk-or-v1-abcdefghijklmnop\n")
    assert "sk-or-v1-abcdefghijklmnop" not in out
    assert REDACTED in out


def test_no_false_positive_on_ordinary_text():
    redactor = SecretRedactor(["hunter2"])
    line = "the build finished with 0 errors\n"
    assert redactor.redact(line) == line


class _BoomingRedactor(SecretRedactor):
    """A redactor whose rewrite step always raises — the seam for proving the
    fail-closed contract without waiting for a real internal error to occur."""

    def _rewrite(self, text: str) -> str:
        raise RuntimeError("boom")


def test_fails_closed_on_internal_error():
    redactor = _BoomingRedactor(["hunter2"])
    assert redactor.feed("x" * 200) == REDACTED
    assert redactor.flush() == REDACTED


def test_redaction_keeps_ndjson_valid():
    secret = "a/b\"c"
    redactor = SecretRedactor([secret])
    line = json.dumps({"msg": f"token leaked: {secret}"})
    out = redactor.redact(line)
    parsed = json.loads(out)
    assert secret not in parsed["msg"]


def test_stream_subprocess_redacts_known_secret_from_streamed_lines():
    lines: list[str] = []
    process.stream_subprocess(
        [sys.executable, "-u", "-c", "print('leaking hunter2 now')"],
        "test_node",
        30,
        lines.append,
        resilience=AgentResilience(),
        secrets=["hunter2"],
    )
    joined = "".join(lines)
    assert "hunter2" not in joined
    assert REDACTED in joined


def test_stream_subprocess_redacts_via_prefix_heuristic_with_no_known_secrets():
    lines: list[str] = []
    process.stream_subprocess(
        [sys.executable, "-u", "-c", "print('key is AKIAABCDEFGHIJKLMNOP')"],
        "test_node",
        30,
        lines.append,
        resilience=AgentResilience(),
    )
    joined = "".join(lines)
    assert "AKIAABCDEFGHIJKLMNOP" not in joined
    assert REDACTED in joined


if __name__ == "__main__":
    test_redacts_the_raw_secret_value()
    test_redacts_base64_authorization_header_form()
    test_redacts_url_encoded_form()
    test_redacts_json_escaped_form()
    test_holds_back_tail_across_a_split_value()
    test_prefix_heuristic_catches_truncated_echo_with_no_known_secrets()
    test_no_false_positive_on_ordinary_text()
    test_fails_closed_on_internal_error()
    test_redaction_keeps_ndjson_valid()
    test_stream_subprocess_redacts_known_secret_from_streamed_lines()
    test_stream_subprocess_redacts_via_prefix_heuristic_with_no_known_secrets()
    print("ok")
