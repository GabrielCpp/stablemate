---
type: flow
slug: file-a-claim
title: File a claim
---
# File a claim

- start: [Submit a claim](../http/claims-api.md#submit-claim), holding a token minted for a holder.
- steps:
  - Acquire an identity from [the auth emulator](../ops/auth-emulator.md) and read the claims
    already on file with [list claims](../http/claims-api.md#list-claims) — for a new holder, none.
  - File the claim. A refusal comes back as
    [field errors keyed by field name](../http/claims-api.md#submit-claim), and nothing is written;
    an acceptance answers `201` with the stored record and the identifier it was given.
  - Read the claim back at its own address with
    [get a claim](../http/claims-api.md#get-claim), which is where the version a decision has to
    quote comes from.
  - File the same claim again and be refused `409 Duplicate Claim`.
- end: the holder's list holds exactly the one claim they filed, at status `Submitted`.
- verify: json_path("claims[0].status", equals="Submitted")
- verify: count(subject="claims", equals=1)
- tests:

The journey the desk exists for, and the one that makes tenancy observable — but only if it is
walked twice. Every step here passes for a service that hands every holder the whole ledger; what
fails is the *end state*, and only when a second holder has filed something for the first holder's
list to wrongly contain.

The step that is easiest to lose is the first. A token is free here, so a walk that acquires one and
reuses it everywhere costs nothing less than a walk that acquires three — it simply proves a
smaller thing, and proves it without saying so.
