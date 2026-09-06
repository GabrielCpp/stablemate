---
type: concept
slug: secret-redaction
title: Agent output secret redaction
---
# Agent output secret redaction

The stream boundary redacts caller-supplied secrets before output reaches transcript capture,
checkpoints, or telemetry. It also catches recognizable provider-token shapes, handles secrets
split across chunks, and fails closed by emitting the redaction marker if rewriting fails.

- code: `workhorse/workhorse/runner/redact.py::SecretRedactor`
- code: `workhorse/workhorse/runner/redact.py::REDACTED`
- tests: `workhorse/tests/test_redact.py::test_holds_back_tail_across_a_split_value`, `workhorse/tests/test_redact.py::test_prefix_heuristic_catches_truncated_echo_with_no_known_secrets`, `workhorse/tests/test_redact.py::test_fails_closed_on_internal_error`, `workhorse/tests/test_redact.py::test_stream_subprocess_redacts_known_secret_from_streamed_lines`
- detail: [supervised subprocess streaming](stream-subprocess.md)

## Fields

### REDACTED
- type: string
- required: true
- verify: json_path(path="$", absent=false)
- semantics: `••••`, substituted for a matched or unsafe-to-rewrite secret
- verify: json_path(path="$", equals="••••")
- code: `workhorse/workhorse/runner/redact.py::REDACTED`

## Methods

### SecretRedactor
- sig: `SecretRedactor(secrets: Iterable[str] = ()) -> SecretRedactor`
- does: derives raw, base64, URL-encoded, and JSON-escaped needles from non-empty supplied secrets
- verify: omits(subject="redactor output for secret a b/c+d", matches="a b/c\\+d|a%20b%2Fc%2Bd|YSBiL2MrZA==")
- does: prepares a holdback tail large enough for boundary-spanning matches and heuristic tokens
- verify: omits(subject="feed and flush output for a split secret", matches="sUp3rSecretValue1234567890|sk-[A-Za-z0-9_-]{10,}")
- returns: a streaming redactor
- verify: created(subject="streaming SecretRedactor")
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor`

### feed
- sig: `SecretRedactor.feed(chunk: str) -> str`
- does: buffers the unsafe tail and rewrites only the safe prefix
- does: replaces known values and recognized token-shaped strings with `REDACTED`
- verify: omits(subject="feed output", matches="hunter2|sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hvs\\.[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}")
- returns: the safely emitted redacted prefix, or `REDACTED` when rewriting fails
- verify: json_path(path="$", equals="••••")
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor.feed`

### flush
- sig: `SecretRedactor.flush() -> str`
- does: rewrites and emits the remaining buffered tail
- verify: omits(subject="flush output", matches="hunter2|sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hvs\\.[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}")
- returns: the final redacted text, or `REDACTED` when rewriting fails
- verify: json_path(path="$", equals="••••")
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor.flush`

### redact
- sig: `SecretRedactor.redact(text: str) -> str`
- does: feeds and flushes one complete text unit
- verify: omits(subject="redact output", matches="hunter2|sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hvs\\.[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}")
- returns: the complete redacted unit
- verify: omits(subject="redact output", matches="hunter2|sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hvs\\.[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}")
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor.redact`
