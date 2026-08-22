---
type: story
id: POLI-01KZ53S2Z01WKC6Z2Q9TYGVW20
slug: policy-list
status: Not started
---
# Story: Show the register

## Dependencies

- Blocked by: create-policy

## Fixtures

- Fixture: policies

## Context

The register is the desk's front door: every policy on file, in policy-number order, each row a
link into [its detail screen](../../../../features/policy/gui/screens/policy-detail.md).

It is also where the navigation region arrives, and navigation is the half of this story a live
scenario can miss. A link that reloads the document reaches the same screen as one that does not,
so a criterion about *arriving* is satisfied by both; the criterion below is about the register
staying mounted, which only one of them does.

## Acceptance Criteria

- `GET /api/policies` answers `200` with every policy on file, ordered by policy number.
- The register renders one row per policy and names each row by its policy number.
- An empty register renders a notice saying so, and no table.
- A register that cannot be read renders an alert rather than an empty table.
- Following a row's link opens that policy's detail screen as a client route: the document is not
  reloaded, and the screen shows the policy that was clicked rather than the one visited before it.
- The navigation region offers the register and the new-policy form from every screen.

## Implementation Status

- **Status**: Not started
