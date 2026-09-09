---
type: concept
slug: outbound-notification-push
title: Outbound notification push
---
# Outbound notification push

Outbound notification delivery to external systems — the backend piece that reaches a phone or home-automation hub. Two independent channels, both opt-in via environment variables and both best-effort (short timeout, silent on failure — an unreachable notifier must never wedge the collector). The implementation is a thin stdlib `urllib` wrapper modeling the sidecar's fire-and-forget `_push` pattern.

- code: `groom/groom/notify.py`
- detail: [blocked notification delivery](blocked-notification-delivery.md)

## Methods

### method: push

- sig: `push(title: str, message: str) -> None`
- does: when `GROOM_NTFY_TOPIC` is configured, post the notification to the ntfy channel
- verify: http_status(code=200, path="https://ntfy.sh/<topic>")
- does: when `GROOM_WEBHOOK_URL` is configured, post the notification to the webhook channel
- verify: http_status(code=200, path="<webhook_url>")
- does: environment is read per call, so long-lived groom picks up configuration changes on restart only
- does: tests can patch `os.environ` without reimporting the module
- raises: does not raise
- raises: any failure (network unreachable, timeout, malformed URL) is silent
- verify: absent(subject="exception")
- code: `groom/groom/notify.py::push`
- tests: `groom/tests/test_notify.py::test_push_sends_to_ntfy_when_topic_is_configured`
- tests: `groom/tests/test_notify.py::test_push_sends_to_webhook_when_url_is_configured`
- tests: `groom/tests/test_notify.py::test_push_silent_on_network_error`
- tests: `groom/tests/test_notify.py::test_push_timeout_is_configurable`

### method: _post

- sig: `_post(url: str, data: bytes, headers: dict[str, str]) -> None`
- abstract: internal HTTP POST helper; callers run this off the event loop via `asyncio.to_thread` since `urllib` blocks
- does: POST the data to the URL with the given headers
- does: close the response body to release the socket
- raises: does not raise for valid requests
- verify: http_status(200, path="<url>")
- raises: for network errors, timeouts, or invalid URLs, catches all exceptions without propagating to caller
- verify: absent(subject="exception")
- code: `groom/groom/notify.py::_post`
- emits: request reaches the URL immediately (best-effort, no retry)

## Configuration

### field: GROOM_NTFY_TOPIC

- type: string, optional
- default: empty string (unconfigured)
- semantics: when non-empty, ntfy channel is active
- verify: http_status(code=200, path="https://ntfy.sh/<topic>")
- semantics: the field value is the topic name appended to `GROOM_NTFY_URL`
- verify: http_status(code=200, path="https://ntfy.sh/<topic>")
- meaning: subscribe to this topic in the ntfy.sh app to receive notifications

### field: GROOM_NTFY_URL

- type: string, optional
- default: `https://ntfy.sh`
- semantics: the ntfy server base URL
- verify: http_status(code=200, path="<GROOM_NTFY_URL>/<topic>")
- semantics: topic is appended as `{base}/{topic}`
- verify: http_status(code=200, path="<GROOM_NTFY_URL>/<topic>")
- meaning: allows self-hosted ntfy servers; default is public ntfy.sh

### field: GROOM_WEBHOOK_URL

- type: string, optional
- default: empty string (unconfigured)
- semantics: when non-empty, webhook channel is active
- verify: http_status(code=200, path="<webhook_url>")
- semantics: webhook receives notification as JSON with title and message fields
- verify: json_path(path="$.title", matches=".*")
- verify: json_path(path="$.message", matches=".*")
- meaning: allows Slack receivers, home automation, or any JSON-consuming webhook

### field: GROOM_NOTIFY_TIMEOUT

- type: float, seconds
- default: `5.0`
- semantics: when a POST target does not respond within the timeout duration, the response body is absent
- verify: absent(subject="response body")
- semantics: when push() encounters a timeout on all configured channels, no exception is raised to the caller
- verify: absent(subject="exception")
- required: false
- meaning: protects the collector from hanging on an unresponsive notifier; both channels share this timeout
