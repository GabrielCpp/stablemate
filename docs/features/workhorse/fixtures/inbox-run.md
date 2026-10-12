---
type: fixture
title: Inbox run
---
# Inbox run

A run directory at `/tmp/workhorse-book/inbox/$dir` whose `inbox.jsonl` holds two messages:
`m1` is outstanding and `m2` was replied to. The [operator inbox](../concepts/operator-inbox.md)
page describes the file. Each scenario that names this fixture gets a fresh copy, because
`inbox reply` rewrites the file.

- args: dir
- lifetime: scenario
- code: `workhorse/workhorse/inbox.py::Message` @e2ad0fc21f23

## Steps

### clear

- kind: seed
- run: rm -rf "/tmp/workhorse-book/inbox/$dir" && mkdir -p "/tmp/workhorse-book/inbox/$dir"

### messages

- kind: seed
- run: printf '%s\n%s\n' '{"id":"m1","body":"may I push?","at":"2026-01-01T00:00:00+00:00"}' '{"id":"m2","body":"tests are red","at":"2026-01-01T00:00:00+00:00","reply":"no","replied_at":"2026-01-02T00:00:00+00:00"}' > "/tmp/workhorse-book/inbox/$dir/inbox.jsonl"

### landed

- kind: verify
- run: grep -q '"m2"' "/tmp/workhorse-book/inbox/$dir/inbox.jsonl"
