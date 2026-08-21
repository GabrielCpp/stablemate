---
type: concept
slug: policy
title: Policy
---
# Policy

- code: app/api/validate.go
- extends:

A policy is one insurance contract on the desk's books: a policy number nobody else holds, the
holder it covers, one of three coverage types, the term it runs for, the premium it is priced at,
and a status — `Draft` on creation, `Cancelled` once somebody cancels it. It carries an integer
`version` that every write increments; that number is the compare-and-swap token
[PUT /api/policies/{id}](../http/policy-desk-api.md#put-policy) requires, and the reason a second
editor cannot silently overwrite the first.

What makes a policy more than a form is that its rules are not all about one field at a time. The
coverage type decides which further field is required, the premium band it is priced against, and —
for umbrella coverage — whether a *different* record has to exist first. Those are the rules a
scenario has to drive the documented route to see, because no client-side check can decide them from
the form alone.

The premium bands are `100`–`10000` for auto coverage, `150`–`20000` for home and `200`–`50000`
for umbrella. They are stated here as prose rather than as a rule per band because a premium is one
field with one rule — the band that applies is chosen by the coverage type, not argued about
separately.

The durable side is [the policy ledger](policy-ledger.md); the machine surface is
[the policy desk API](../http/policy-desk-api.md); the screens are
[the policy register](../gui/screens/policy-list.md) and the three that hang off it.

## Fields

### policy_number

- type: string
- default: none
- required: true on creation, and rejected as `policy_number` when blank.
- semantics: the human-facing identity of the contract, and the only field the id is derived from —
  `PN-1001` is always the policy at `/policies/pn-1001`. It is settled at creation: an edit neither
  sends it nor may change it.

### holder_email

- type: string
- default: none
- required: true, on creation and on every edit.
- semantics: the person the contract covers, matched case-insensitively when the umbrella
  prerequisite looks for this holder's other policies.

### coverage_type

- type: string
- default: `auto`, which is what [the new policy form](../gui/screens/new-policy.md) opens on.
- required: true, and refused unless it is one of `auto`, `home`, `umbrella`.
- semantics: the discriminator. It decides which further field is required, which premium band
  applies, and whether the cross-record umbrella prerequisite is checked at all.

### vehicle_vin

- type: string
- default: none
- required: true when `coverage_type` is `auto`, and ignored otherwise.
- semantics: the vehicle the auto policy covers. Its requirement is conditional, so a form that
  drops the field when the coverage type changes drops the rule with it.

### property_address

- type: string
- default: none
- required: true when `coverage_type` is `home`, and ignored otherwise.
- semantics: the property the home policy covers, on the same conditional footing as the VIN.

### start_date

- type: string, as `YYYY-MM-DD`
- default: none
- required: true, and refused when the date is in the past *on creation only* — an existing policy
  can be edited long after it started.
- semantics: the day cover begins.

### end_date

- type: string, as `YYYY-MM-DD`
- default: none
- required: true, and refused unless it is strictly after `start_date`.
- semantics: the day cover ends. Equal dates are a zero-length term and are refused as such.

### premium

- type: number
- default: none
- required: true, within the band its coverage type sets.
- semantics: the annual price, banded per coverage type, so the same number is acceptable on one
  contract and refused on another.

## Methods

### Validate

- sig: `Validate(in PolicyInput, ledger Ledger, today string, isCreate bool) map[string]string`
- abstract: every rule a policy has to satisfy, returned as one message per offending field key —
  the same key the form puts its inline message under, so the two layers cannot describe a refusal
  differently. An empty map means the input is acceptable.
- raises: nothing at all, because a refusal is a returned message rather than an error.
- returns: a map keyed by field name, using only the keys `policy_number`, `holder_email`,
  `coverage_type`, `vehicle_vin`, `property_address`, `start_date`, `end_date`, `premium`.
- verify: json_path("errors.vehicle_vin", equals="Auto coverage needs the vehicle VIN.")
- verify: json_path("errors.end_date", equals="End date must be after the start date.")
- parent: [Policy](#policy)

### hasUnderlyingPolicy

- sig: `hasUnderlyingPolicy(ledger Ledger, email, self string) bool`
- abstract: answers the umbrella prerequisite — this holder already has a live non-umbrella policy
  on file.
- returns: `true` only for a policy that is not this one, is not itself umbrella coverage, is not
  `Cancelled`, and names the same holder.
- verify: json_path("errors.coverage_type", equals="Umbrella coverage needs an existing auto or home policy for this holder.")
- verify: http_status(422, path="/api/policies")
- parent: [Policy](#policy)
