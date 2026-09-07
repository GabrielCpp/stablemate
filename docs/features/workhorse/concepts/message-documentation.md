---
type: concept
slug: message-documentation
title: Message documentation
---
# Message documentation

`Message` has two complementary documentation views; neither supersedes the other. The model
declares the caller-supplied identity, body, creation time, and paired reply state, while the
inbox operations define an outstanding message as one whose `reply` is empty. They validate and
serialize that model as JSON lines, preserving workflow-defined extra fields through a round trip.

Use [run inbox](run-inbox.md) to determine the meaning of an operator or failure-handoff message,
whether it is outstanding, and how a reply changes it. Use [message representations](message-representations.md)
to read or write the persisted JSON-lines representation, including workflow-defined extra fields.
No ranking exists because these views answer different questions about the same `Message`.

- rule: use run inbox for message semantics and inbox state; use message representations for persisted JSON-lines fields and round-trip preservation
