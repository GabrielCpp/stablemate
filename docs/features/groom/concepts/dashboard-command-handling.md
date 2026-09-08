---
type: concept
slug: dashboard-command-handling
title: Dashboard command handling
---
# Dashboard command handling

The dashboard command path is documented at two levels, not as alternative answer
implementations. `groom/groom/app.py::_handle_command` recognizes `watch` frames,
registers their queue, and sends the current detail when the selected workflow exists;
for an `answer` frame it reads the three command fields and delegates to
`groom/groom/app.py::_answer`. That helper selects the control-socket or file fallback,
records the attempt, clears the blocked state only after a successful final answer, and
broadcasts the resulting state.

Use [method-handle-command](groom-app-module.md#method-handle-command) for browser-frame
dispatch and watch registration. Use
[transition-successful-last-gate-answer](workflow-state.md#transition-successful-last-gate-answer)
only for the lifecycle condition reached after the delegated answer succeeds. Neither
view supersedes the other: one describes command routing and the other the guarded
state transition it can cause.

- rule: use the command-handler view for websocket command dispatch; use the workflow-state transition only for a successful answer that leaves an existing blocked workflow with no gates.
