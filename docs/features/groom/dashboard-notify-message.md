---
type: format
slug: dashboard-notify-message
title: Dashboard notify message
---
# Dashboard notify message

Dashboard notify message is the JSON frame the server pushes down [WS /ws](http/groom.md#websocket-dashboard) when something has just happened that the operator should be *interrupted* about: a workflow became blocked on a gate, or a time-based alert rule fired. It carries one already-composed message string to every connected tab, and the dashboard's frame dispatcher hands it to the [dashboard toast pusher](concepts/dashboard-toast-pusher.md#method-on-notify), which raises an in-page toast and — when [browser notification permission](concepts/browser-notification-permission.md) has been granted — a system notification.

It replaced an inline `<script>` fragment. The htmx-era dashboard delivered this same alert by rendering a code-carrying HTML fragment into the broadcast and letting the browser execute it, which meant a gate question ended up interpolated into script source and had to be escaped correctly on the server to stay inert. Now the question is a JSON string member, parsed by the browser's JSON decoder and written to the document through `textContent`. No value on this path is ever interpolated into markup or script source, so there is no escaping step left that can be got wrong.

The frame is deliberately kept **off** the [dashboard state payload](dashboard-state-payload.md). State is a snapshot, re-pushed by the 5-second clock and by every reconciliation, so an alert carried inside it would re-fire on every tick for as long as the run stayed blocked. This frame is an edge: it is sent once, by the code path that observed the transition, and a tab that missed it does not learn about it from a later resync. That asymmetry is the point — the row stays blocked in every snapshot, but the operator is only interrupted the once.

- file: not an on-disk artifact; this is one transient server-to-browser websocket JSON message.
- code: groom/groom/app.py::_broadcast_notify
- code: groom/groom/app.py::push_blocked
- code: groom/groom/app.py::_apply_socket_blocked
- code: groom/groom/app.py::_dispatch_alerts
- code: groom/groom/assets/dashboard.js::onFrame
- code: groom/groom/assets/dashboard.js::onNotify
- refs: [blocked push payload](blocked-push-payload.md), [dashboard state payload](dashboard-state-payload.md), [dashboard answered message](dashboard-answered-message.md), [browser notification permission](concepts/browser-notification-permission.md)
- verify: groom/tests/test_app.py::test_push_blocked_sends_the_state_frame_then_a_separate_notify_frame
- verify: groom/tests/test_app.py::test_socket_blocked_delta_sends_the_same_notify_frame_as_the_http_push
- verify: groom/tests/test_app.py::test_the_notify_message_truncates_the_question_to_the_limit
- verify: groom/tests/test_telemetry.py::test_v1_traces_receiver_stores_spans_and_fires_alerts

## Contract

- producer: three server paths send this frame — [receive blocked push](http/groom.md#receive-blocked-push), the [sidecar blocked applier](concepts/sidecar-blocked-applier.md) handling a live `blocked` websocket delta, and the alert-rule dispatcher when a telemetry alert fires. All three go through the same one broadcast helper, so there is one wire shape rather than three.
- media: a JSON object on the dashboard websocket. It is not an HTTP body, an inline `<script>`, a DOM `CustomEvent`, or a persisted record.
- shape: exactly two keys — `type` and `message`. No workflow id, gate file path, rule name as its own member, severity, timestamp, toast variant, lifetime, or envelope is included.
- discriminator: `type` is the string `notify`, which is how the client's frame dispatcher routes it. It is the same discriminator every dashboard push carries, so the client has one dispatch table rather than a shape-sniffing branch.
- audience: every connected dashboard client. The [run watch registry](concepts/run-watch-registry.md) scopes detail pushes; it does not scope this one. Groom is a shared console, and a run blocking is a fact about the fleet rather than about whoever happens to have that pane open.
- pre-composition: the human-readable string is assembled server-side before broadcast, and the client displays it verbatim. The client applies no formatting, no truncation, and no template of its own; there is exactly one place each alert's wording lives.
- ordering: the blocked paths send this frame *after* the [dashboard state payload](dashboard-state-payload.md) and the accompanying run-detail push, so a tab rendering frames in arrival order raises the alert against already-updated content.
- delivery is best-effort and once: no acknowledgement, no retry, no replay for a tab that connects later, and no record of the alert anywhere in the state a resync would fetch.
- state mutation: sending this frame mutates nothing. Any workflow state change has already happened, before the state broadcast that precedes it.
- consumer: the client's `notify` handler pushes one blocked-variant toast with a seven-second lifetime, and additionally constructs a browser `Notification` when the API exists and permission is already `granted`. It never *requests* permission from this path — a prompt raised by an incoming socket frame arrives with no user gesture behind it, which is both hostile and, in current browsers, refused.

## Fields

### field-type

- type: JSON string, always `notify`.
- default: none
- required: true
- wire-key: `type`
- consumer-use: the frame dispatcher's routing key; frames whose `type` matches no known handler are ignored.
- meaning: the frame discriminator shared by every server-to-browser dashboard push.

### field-message

- type: JSON string
- default: none
- required: true
- wire-key: `message`
- source: for a gate, the workflow's display name, a colon, and the gate question truncated to the [question notification limit](concepts/groom-app-module.md#field-question-notify-limit); for a fired rule, the bracketed rule name followed by the rule's own message.
- consumer-use: the toast body, and the body of the system notification when one is raised. An empty or absent value falls back to `A workflow needs your input.` in the client, so a malformed frame still produces a legible alert rather than a blank toast.
- meaning: the whole human-readable content of the alert. The question is truncated rather than sent whole because this is an interruption, not the pane — the full markdown question is already on the wire in the run's detail payload, rendered and sanitized there.
