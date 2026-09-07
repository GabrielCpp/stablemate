---
type: concept
slug: message-representations
title: Message representations
---
# Message representations

`Message` is the shared inbox entry model. Its two documents are complementary and neither
supersedes the other: use the run-inbox fields when deciding what an operator message means or
whether it is outstanding, and use the JSONL fields when reading or writing its persisted line.
The model permits workflow-defined extra fields, so the JSONL representation is also the place to
learn how those fields survive a round trip.

- code: `workhorse/workhorse/inbox.py::Message`
- rule: use run-inbox fields for message semantics and inbox state; use run inbox JSONL fields for the persisted JSON-lines representation
- detail: [message documentation](message-documentation.md)
