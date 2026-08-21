---
type: concept
slug: policy-ledger
title: Policy ledger
---
# Policy ledger

- code: app/api/store.go
- code: compose.yml
- extends:

The ledger is the whole of the service's state: one JSON file holding every
[policy](policy.md) on the books with its fields, its status and its version. It is read on every
request rather than cached, and written atomically. Both properties are load-bearing rather than
tidy: a store that answers out of the memory of the process that wrote it cannot tell a commit from
a cache, and a torn write would surface as a lost policy blamed on the wrong rule.

It is the durable half of [the policy desk API](../http/policy-desk-api.md); the rules that decide
what may enter it are [the policy's methods](policy.md#methods).

## Methods

### Read

- sig: `Read() (Ledger, error)`
- abstract: the current ledger; a ledger file that does not exist yet reads as an empty book rather
  than an error.
- returns: every policy on file, in the order they were written.
- verify: persists(subject="policy pn-1001")
- verify: http_status(200, path="/api/policies/pn-1001")
- parent: [Policy ledger](#policy-ledger)

### Write

- sig: `Write(ledger Ledger) error`
- abstract: replaces the ledger atomically.
- returns: an error only when the file cannot be written.
- verify: keys_unchanged(subject="policies")
- verify: persists(subject="policy pn-1001")
- persistence: a created policy is on disk before the response that announces it, and is still on
  the books — at the version the creation returned, with the same premium — after the service
  restarts.
- parent: [Policy ledger](#policy-ledger)
