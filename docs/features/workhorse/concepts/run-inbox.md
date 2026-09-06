---
type: concept
slug: run-inbox
title: Run inbox
---
# Run inbox

The run inbox is an advisory operator-to-run message store at `<run_dir>/inbox.jsonl`. Messages
are JSON lines and remain available after a run is parked, dead, or finished. Reading never
removes an entry; a reply rewrites the matching entry with `reply` and `replied_at`. Outstanding
messages are those whose `reply` is empty. Extra fields are preserved so workflows can attach
their own classification and diagnostic data without changing the shared store.

- code: `workhorse/workhorse/inbox.py::Message`
- tests: `workhorse/tests/test_inbox.py::test_outstanding_excludes_replied_messages`
- detail: [run inbox JSONL](../inbox-jsonl.md)

The same store carries failure-handoff entries from the driver. The inbox primitive does not
interpret message kinds; a workflow or operator filters them.

## Fields

### id
- type: string
- required: true
- semantics: caller-supplied identity used to locate the message for a reply
- verify: json_path(path="$.id", matches=".+")
- code: `workhorse/workhorse/inbox.py::Message`

### body
- type: string
- required: true
- semantics: operator or failure-handoff message text
- verify: json_path(path="$.body", matches=".*")
- code: `workhorse/workhorse/inbox.py::Message`

### at
- type: string
- required: true
- semantics: creation timestamp supplied by the writer
- verify: json_path(path="$.at", matches=".+")
- code: `workhorse/workhorse/inbox.py::Message`

### reply
- type: string
- default: empty string
- required: true
- semantics: response text; empty means the message remains outstanding
- verify: json_path(path="$.reply", equals="")
- code: `workhorse/workhorse/inbox.py::Message`

### replied_at
- type: string
- default: empty string
- required: true
- semantics: timestamp written with a non-empty reply
- verify: json_path(path="$.replied_at", equals="")
- code: `workhorse/workhorse/inbox.py::Message`

## Methods

### append
- sig: `append(path, *, id, body, at, **extra) -> Message`
- does: appends one JSON line without rewriting existing messages
- returns: the validated Message that was appended
- verify: count(subject="messages after one append", equals=1)
- code: `workhorse/workhorse/inbox.py::append`
- tests: `workhorse/tests/test_inbox.py::test_append_returns_and_persists_the_message`

### all_messages
- sig: `all_messages(path) -> list[Message]`
- returns: every message oldest first, including replied messages
- verify: count(subject="messages returned after two appends and one reply", equals=2)
- code: `workhorse/workhorse/inbox.py::all_messages`
- tests: `workhorse/tests/test_inbox.py::test_outstanding_excludes_replied_messages`

### outstanding
- sig: `outstanding(path) -> list[Message]`
- returns: messages whose reply is empty, oldest first
- verify: count(subject="unreplied messages after one of two messages is replied", equals=1)
- code: `workhorse/workhorse/inbox.py::outstanding`
- tests: `workhorse/tests/test_inbox.py::test_outstanding_excludes_replied_messages`

### reply
- sig: `reply(path, message_id, text, *, at) -> Message`
- does: updates the matching message's reply and replied_at fields
- verify: persists(subject="replied inbox message")
- does: atomically rewrites the inbox
- verify: persists(subject="replied inbox message")
- does: preserves other messages during the rewrite
- verify: unchanged(subject="other inbox messages")
- raises: KeyError when message_id is absent
- returns: the updated Message
- code: `workhorse/workhorse/inbox.py::reply`
- tests: `workhorse/tests/test_inbox.py::test_reply_sets_reply_and_replied_at`, `workhorse/tests/test_inbox.py::test_reply_to_missing_id_raises`
