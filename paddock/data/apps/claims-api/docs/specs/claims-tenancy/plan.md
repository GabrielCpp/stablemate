---
type: spec.plan
---

# Plan: Read Back Only the Claims That Are Yours

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

Both reads delegate scope to one file. `VisibleTo` answers what a register may show and `Entitled`
answers whether one named claim may be read; the handlers call them and do no filtering of their
own, so widening the register is a change to a rule rather than a change to a route.

The single-claim handler looks the claim up before it decides entitlement, which is what makes a
`403` and a `404` distinguishable only to a caller entitled to the difference.

## 2. Files

- `app/api/scope.go` — `VisibleTo` and `Entitled`, the whole of the tenancy rule.
- `app/api/list.go` — `GET /api/claims`.
- `app/api/get.go` — `GET /api/claims/{id}`.

`scope.go` is its own file rather than a pair of helpers inside `list.go` because the book's
tenancy concept cites it, and a source file cited by two nodes localizes nothing.

## 3. Acceptance Checklist

- [x] A holder's register lists exactly their own claims; an empty register is 200 with an empty list.
- [x] An adjuster's register lists every claim on file.
- [x] A claim fetched by id answers 200 for its holder and for an adjuster, carrying the version a decision quotes.
- [x] Another holder's claim answers 403 Not Your Claim; an unknown id answers 404 No Such Claim.
- [x] Entitlement is decided after the lookup, so existence does not leak.

## 4. QA

Every claim above is observable over HTTP, and none of them is observable with one identity. Each
criterion is a statement about a *second* caller: the register a holder does not see, the claim
another holder may not fetch, the whole desk only the adjuster reads. A plan that acquires one
token proves the happy path of every route here and none of the rules.

The three identities are seeded by compose and signed in through the emulator on `18086`; a claim's
`holder_uid` is the subject of the token that filed it, so a scenario proves scope by comparing
what it filed against what each caller is handed back.
