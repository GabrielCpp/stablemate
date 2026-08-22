---
type: concept
slug: claim-ledger
title: Claim ledger
---
# Claim ledger

- code: app/api/store.go
- extends:

The ledger is the whole of the service's state: one JSON file holding every claim on file with its
policy number, the holder it belongs to, its amount, its status, its version and the adjuster's
note. It is read on every request rather than cached, and written atomically. Both properties are
load-bearing rather than tidy: a store that answers out of the memory of the process that wrote it
cannot tell a commit from a cache, and a torn write would surface as a lost claim blamed on the
wrong rule.

A claim's identifier is issued here, in sequence from `cl-1001`, and nothing returns one. It is the
durable half of [the claims API](../http/claims-api.md); who may read what out of it is
[claim tenancy](claim-tenancy.md).

## Methods

### Read

- sig: `Read() (Ledger, error)`
- abstract: the current ledger; a ledger file that does not exist yet reads as an empty book rather
  than an error, so a cold service serves rather than refuses.
- returns: every claim on file, in the order they were written, and the next identifier to issue.
- verify: persists(subject="claim cl-1001")
- verify: http_status(200, path="/api/claims")
- parent: [Claim ledger](#claim-ledger)

### Write

- sig: `Write(ledger Ledger) error`
- abstract: replaces the ledger atomically.
- returns: an error only when the file cannot be written.
- verify: keys_unchanged(subject="claims")
- verify: persists(subject="claim cl-1001")
- persistence: claim-record — an accepted claim is on disk before the response that announces it, and is still on
  file — at the version that response carried, with the same amount — after the service restarts.
- parent: [Claim ledger](#claim-ledger)
