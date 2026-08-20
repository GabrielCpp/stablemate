---
type: screen
slug: policy-list
title: Policy register
---
# Policy register

- route: `/policies`
- requires:
  - none; the desk carries no session and the register is the app's front door.
- params:
  - none
- entry: yes; it is the app root — `/` redirects here — and the start of both documented journeys.

The register is the list of every [policy](../../concepts/policy.md) on the books, read from
[GET /api/policies](../../http/policy-desk-api.md#get-policies). It is a client route in a single
bundle: the links below move between screens without reloading the document, and the Go binary
serves that same bundle for any of the four paths, so each one is also a working deep link.

It re-reads the register on a timer as well as on arrival, because a desk is not the only writer of
its own books — and a failure to re-read is announced rather than swallowed, since a stale table
that looks current is the one failure mode a register must not have.

## Components

### policy-table

- selector: `table`
- role: table
- name: Policies on file
- placement: width 60-100%, x 0-20%, y 20-100%
- keyboard: reachable by `Tab` from the document start, with no shortcut of its own.
- parent: [Policy register](#policy-register)
- code: app/web/src/PolicyList.tsx
- does: renders one row per policy on the books, with its number, holder, coverage, premium and
  status.
- verify: visible(locator="table:Policies on file")
- verify: visible(locator="table:Policies on file", text="PN-1001")
- does: names each row by its policy number, as a link to that policy's detail screen.
- verify: visible(locator="link:PN-1001")

### empty-register-notice

- selector: `main > p`
- role: paragraph
- name: none
- placement: width 40-100%, x 0-20%, y 10-60%
- keyboard: none, because it is read rather than operated.
- parent: [Policy register](#policy-register)
- exclusive-with: [policy-table](#policy-table)
- code: app/web/src/PolicyList.tsx
- does: stands in for the table when the books are empty, and points at the way to start one.
- verify: visible(locator="text=No policies are on file yet")

### register-error-alert

- selector: `p[role="alert"]`
- role: alert
- name: none
- placement: width 40-100%, x 0-20%, y 10-60%
- keyboard: none, because it is announced rather than operated.
- parent: [Policy register](#policy-register)
- code: app/web/src/RegisterError.tsx
- does: says so when the register cannot be re-read, rather than leaving the previous table on
  screen looking current.
- verify: visible(locator="alert")

### new-policy-link

- selector: `nav a[href="/policies/new"]`
- role: link
- name: New policy
- placement: width 0-40%, x 0-30%, y 0-20%
- keyboard: `Tab` to the link, `Enter` to follow it.
- parent: [Policy register](#policy-register)
- code: app/web/src/Nav.tsx
- does: opens [the new policy form](new-policy.md) as a client route, without reloading the
  document.
- verify: visible(locator="link:New policy")

## Interactions

### open-policy

- on: [policy-table](#policy-table)
- trigger: click on a policy number in the register
- role: link
- name: PN-1001
- keyboard: `Tab` to the link, `Enter` to follow it.
- does:
  - navigates to [the policy's detail screen](policy-detail.md) at `/policies/{id}`, client-side, and the detail screen shows that policy rather than the one visited before it.
- code: app/web/src/PolicyList.tsx
- verify: visible(locator="heading:Policy PN-1001")
