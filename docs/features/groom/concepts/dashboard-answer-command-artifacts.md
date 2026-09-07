---
type: concept
slug: dashboard-answer-command-artifacts
title: Dashboard answer command artifacts
---
# Dashboard answer command artifacts

The dashboard command handler has three distinct data artifacts for one `cmd="answer"`
operation. It consumes the [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md),
records an [answer log entry](../answer-log-entry.md) after `_answer` returns, and broadcasts a
[dashboard answered message](../dashboard-answered-message.md) only when that result succeeds.

They are not competing implementations and have no ranking: choose the inbound frame when
describing what the browser submits, the log entry when describing the process-local record of
an attempt, and the answered message when describing the fleet-wide success confirmation. The
handler keeps all three because a failed attempt is logged but has no success confirmation, while
the submitted frame is an input rather than either output.

- code: groom/groom/app.py::_handle_command
- code: groom/groom/app.py::_answer
- rule: use the inbound frame for browser-to-server input, the log entry for every completed answer attempt, and the answered message only for the successful server-to-browser confirmation; none replaces another.
