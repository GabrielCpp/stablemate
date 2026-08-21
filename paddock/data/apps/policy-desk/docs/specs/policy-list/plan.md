---
type: spec.plan
---

# Plan: Show the Register

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished services, and what runs against them is QA.

## 1. Approach

The list endpoint is a read over the same ledger the creation writes — no cache, no projection —
so the register cannot disagree with the record it links to. The register screen fetches once on
mount and refreshes on an interval, and both paths render the same three states: rows, an empty
notice, or an alert.

The navigation region is a component of its own rather than markup inside the router, so a screen's
links and the shell's links are separable when one of them breaks.

## 2. Files

- `app/api/list.go` — `GET /api/policies`, ordered by policy number.
- `app/api/service.go` — the route table gains the list route.
- `app/web/src/PolicyList.tsx` — the table, the empty notice, the failure alert, the refresh.
- `app/web/src/Nav.tsx` — the navigation region.
- `app/web/src/routes.tsx` — the register becomes the landing route.

## 3. Acceptance Checklist

- [x] `GET /api/policies` answers 200 with every policy on file, ordered by policy number.
- [x] The register renders one row per policy, named by its policy number.
- [x] An empty register renders a notice and no table.
- [x] A register that cannot be read renders an alert rather than an empty table.
- [x] A row's link opens the detail screen client-side, showing the policy that was clicked.
- [x] The navigation region offers the register and the new-policy form from every screen.

## 4. QA

Every claim above is observable over HTTP or on the rendered page. The navigation criterion is the
one that needs care: arriving at the detail screen is not evidence of a client route, because a
document reload arrives too. What separates them is the register staying mounted across the
transition.

The ledger persists across scenarios and nothing empties it, so a scenario about the empty state
must put the register back first — `DELETE /api/policies`, documented on the policy desk API.
