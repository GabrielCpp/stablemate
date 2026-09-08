---
type: concept
slug: blocked-push-documentation-index
title: Blocked push documentation index
---
# Blocked push documentation index

[Blocked push documentation scopes](blocked-push-documentation-scopes.md) and [blocked push
flow contexts](blocked-push-flow-contexts.md) both ground themselves in `push_blocked` because
each answers a different question about the same endpoint, not because they compete to
describe it.

Documentation scopes answers *which written view of `push_blocked` itself to read*: the
[push blocked method](groom-app-module.md#method-push-blocked) for the endpoint's complete
input, side effects, and notification contract, or the [blocked push
transition](workflow-state.md#transition-blocked-push) for only the `BLOCKED` lifecycle
effect it produces.

Flow contexts answers a different question: *which surrounding document to read next* — the
[blocked push payload](../blocked-push-payload.md) format that producers send in, the
[dashboard notify message](../dashboard-notify-message.md) format the endpoint emits, or one of
the two flows ([operator answers blocked
gate](../flows/operator-answers-blocked-gate.md), [residual sidecar push and query
fallback](../flows/residual-sidecar-push-and-query-fallback.md)) that carry a blocked
notification through the system around this one endpoint call.

Neither concept supersedes the other and no ranking exists between them: a reader picks
documentation scopes to choose between competing *descriptions* of `push_blocked`, and flow
contexts to choose between its *adjacent* payload, output, and journey documents. Both remain
current and are read together, not as alternatives.

- rule: consult documentation scopes to choose which write-up of `push_blocked` describes it; consult flow contexts to choose which adjacent payload, message, or flow document to read next

