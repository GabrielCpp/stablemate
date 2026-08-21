---
type: concept
slug: claim-tenancy
title: Claim tenancy
---
# Claim tenancy

- code: app/api/scope.go
- extends:

Two roles read [the ledger](claim-ledger.md), and they see different things. A **holder** sees the
claims whose `holder_uid` is the subject of their own token, and nothing else on file. An
**adjuster** sees every claim, because deciding them is the job.

The rule is stated once, here, and asked twice — for a list and for a single claim — rather than
re-derived in each handler. That is the whole reason it is a file of its own: a scoping rule spelled
out at two call sites is a scoping rule that can disagree with itself, and the disagreement shows up
as one endpoint being correct.

Neither answer depends on anything in the request but the verified identity. There is no query
parameter, no header and no path that widens what a caller may read, so the only way to see another
holder's claim is to hold another holder's token.

## Methods

### VisibleTo

- sig: `VisibleTo(ledger Ledger, identity Identity) []Claim`
- abstract: the claims this identity may read, in ledger order.
- returns: for a holder, the claims whose `holder_uid` equals the token's subject, and an empty
  list rather than an error when there are none.
- returns: for an adjuster, every claim on file.
- verify: count(subject="claims", equals=1)
- verify: http_status(200, path="/api/claims")
- parent: [Claim tenancy](#claim-tenancy)

### Entitled

- sig: `Entitled(claim Claim, identity Identity) bool`
- abstract: whether this identity may read this one claim.
- returns: true for an adjuster, and for the holder the claim belongs to.
- returns: false for any other holder, which the route turns into `403 Not Your Claim`.
- verify: http_status(403, title="Not Your Claim", path="/api/claims/cl-1002")
- parent: [Claim tenancy](#claim-tenancy)
