---
type: format
slug: dashboard-answered-message
title: Dashboard answered message
---
# Dashboard answered message

Dashboard answered message is the JSON frame the server pushes down [WS /ws](http/groom.md#websocket-dashboard) after a [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) writes a gate successfully. It carries the answered workflow id and gate file path to every connected tab, and the dashboard's frame dispatcher hands it to the handler that raises the `answer sent` toast.

It exists to confirm, and only to confirm. The pane the answer came from is refreshed by the [run detail](http/groom.md#get-run-detail) push the same command triggers, and the fleet list by the [dashboard state payload](dashboard-state-payload.md) broadcast alongside it — so by the time this frame arrives, everything visible is already correct and the only thing left to say is *that worked*. Keeping the acknowledgement as its own frame is what lets the confirmation be a toast rather than a re-render: nothing in the tab has to be invalidated to show it.

The frame is broadcast fleet-wide rather than returned to the submitting socket. Groom is a shared console — two operators watching the same blocked run should both see that it was answered, and the tab that did not submit learns it from the same frame as the one that did.

- file: not an on-disk artifact; this is one transient server-to-browser websocket JSON message.
- code: groom/groom/app.py::_handle_command
- code: groom/groom/assets/dashboard.js::onFrame
- code: groom/groom/assets/dashboard.js::onAnswered
- refs: [dashboard websocket answer frame](dashboard-websocket-answer-frame.md), [answer result](answer-result.md), [dashboard toast pusher](concepts/dashboard-toast-pusher.md)
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_an_answered_event
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- producer: the dashboard websocket answer command handler sends this frame only when the [answer result](answer-result.md) reports `ok=true`. Rejected, duplicate, stale, and failed answers produce no frame of this type.
- media: a JSON object on the dashboard websocket. It is not an HTTP body, an inline `<script>`, a DOM `CustomEvent`, a dataset attribute, or a persisted record — the answered fact reaches the browser as data on the same socket as every other push, with no code-carrying frame anywhere on the path.
- shape: exactly three keys — `type`, `id`, and `file_path`. No command name, answer text, success flag, message, workflow state, gate question, toast text, or envelope is included.
- discriminator: `type` is the string `answered`, which is how the client's frame dispatcher routes it. It is the same discriminator every dashboard push carries, so the client has one dispatch table rather than a shape-sniffing branch.
- audience: every connected dashboard client, not only the socket that submitted the answer and not only the tabs watching that run. The [run watch registry](concepts/run-watch-registry.md) scopes detail pushes; it does not scope this one.
- source values: `id` is the normalized `workflow_id` and `file_path` the normalized gate path from the answer frame that succeeded. Neither is re-derived from current workflow state, the answer log, or the gate collection.
- ordering: the frame is sent after the shell broadcast and any accompanying detail push, so a tab that renders frames in arrival order shows the confirmation against already-updated content.
- consumer: the client's frame dispatcher routes `answered` to a handler that pushes one success toast with a fixed lifetime and does nothing else. It reads no member of the frame.
- no re-fetch: the handler issues no HTTP request and re-renders no pane. That is deliberate — the detail push already carried the run's remaining gates, so a re-fetch here would be a redundant round trip, and one triggered in every tab would also risk replacing a *different* run's answer form while somebody was typing in it.
- escaping: values are JSON members parsed by the browser's JSON decoder. Quotes, markup, backslashes, newlines, and non-ASCII characters stay data; no value is ever interpolated into markup or script source on this path.
- identity preservation: no trimming, path normalization, id canonicalization, lowercasing, length limiting, or existence check is applied. The values sent are the normalized strings the command handler used.
- excluded content: the answer text, the gate question, the answer log message, the fleet state, the run detail, and the sidecar frames are all outside this format.
- state mutation: sending this frame mutates nothing. Any workflow state change from the answer has already happened, before the shell broadcast that precedes this frame.

## Fields

### field-type

- type: JSON string, always `answered`.
- default: none
- required: true
- wire-key: `type`
- consumer-use: the frame dispatcher's routing key; frames whose `type` matches no known handler are ignored.
- meaning: the frame discriminator shared by every server-to-browser dashboard push.

### field-id

- type: JSON string
- default: none
- required: true
- wire-key: `id`
- source: the normalized `workflow_id` from the accepted [dashboard websocket answer frame](dashboard-websocket-answer-frame.md#field-workflow_id).
- consumer-use: none in the current first-party client — the toast is unconditional. The member is on the wire so a consumer that needs to scope the acknowledgement can, without a protocol change.
- meaning: the workflow container id whose gate answer succeeded.

### field-file_path

- type: JSON string
- default: none
- required: true
- wire-key: `file_path`
- source: the normalized `file_path` from the accepted [dashboard websocket answer frame](dashboard-websocket-answer-frame.md#field-file_path).
- consumer-use: none in the current first-party client; it identifies the answered gate for observers, tests, and future consumers.
- meaning: the gate context-file path the successful answer was written to. It preserves which gate was answered, which `id` alone cannot say for a run that had several open.
