---
type: flow
slug: decide-a-claim
title: Decide a claim
---
# Decide a claim

- start: [List claims](../http/claims-api.md#list-claims), holding a token carrying the `adjuster`
  role.
- steps:
  - Read every claim on file — the adjuster's list is the whole ledger, not one holder's — and take
    the version off the claim to be decided.
  - Approve or deny it with [decide a claim](../http/claims-api.md#decide-claim), quoting that
    version and a note.
  - Quote the same version again and be refused `409 Stale Decision`: the version the first decision
    consumed is spent.
  - Read the claim back as the holder it belongs to, who sees the decision and the note without
    being able to make either.
- end: the claim is `Approved` at version `2` with the adjuster's note on it, and is still so after
  the service restarts.
- verify: json_path("claim.status", equals="Approved")
- verify: persists(subject="claim cl-1001")
- tests:

The half of the product a holder can reach but not perform, which makes it the journey where the
role gate is worth something. Walked with an adjuster's token alone it proves only that approving
works; the refusal that matters — a holder calling the same route — is a step this flow does not
contain and the endpoint's own `authorization` clause does.

The end state is deliberately durable rather than merely returned. A decision held in the memory of
the process that made it satisfies every read inside one run.
