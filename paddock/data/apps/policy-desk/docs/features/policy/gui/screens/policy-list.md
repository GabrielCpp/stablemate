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
- verify: visible(locator="#policy-table")
- verify: visible(locator="#policy-table", text="PN-1001")
- verify: visible(locator="#open-policy")
- placement: width 60-100%, x 0-20%, y 10-100%
- keyboard: reachable by `Tab` from the document start, with no shortcut of its own.
- parent: [Policy register](#policy-register)
- code: app/web/src/PolicyList.tsx@1190425978c1

Renders one row per policy on the books, with its number, holder, coverage, premium and status.
Names each row by its policy number, as a link to that policy's detail screen.

### empty-register-notice

- selector: `p.empty-notice`
- role: paragraph
- name: none
- placement: width 40-100%, x 0-20%, y 10-60%
- keyboard: none, because it is read rather than operated.
- verify: visible(locator="#empty-register-notice", text="No policies are on file yet")
- parent: [Policy register](#policy-register)
- exclusive-with: [policy-table](#policy-table)
- code: app/web/src/PolicyList.tsx@1190425978c1

Stands in for the table when the books are empty, and points at the way to start one.

### register-error-alert

- selector: `p[role="alert"]`
- role: alert
- name: none
- placement: width 40-100%, x 0-20%, y 10-60%
- keyboard: none, because it is announced rather than operated.
- parent: [Policy register](#policy-register)
- states: present only after a register read fails.
- verify: visible(locator="#register-error-alert")
- code: app/web/src/RegisterError.tsx@94ff0a60334e

Says so when the register cannot be re-read, rather than leaving the previous table on screen
looking current.

### new-policy-link

- selector: `#new-policy`
- role: link
- name: New policy
- verify: visible(locator="#new-policy-link")
- placement: width 0-40%, x 0-30%, y 0-20%
- keyboard: `Tab` to the link, `Enter` to follow it.
- parent: [Policy register](#policy-register)
- code: app/web/src/Nav.tsx@4b67472aa613

Opens [the new policy form](new-policy.md) as a client route, without reloading the document.

## Interactions

### open-policy

- on: [policy-table](#policy-table)
- trigger: click on a policy number in the register
- role: link
- name: PN-1001
- keyboard: `Tab` to the link, `Enter` to follow it.
- does:
  - navigates to [the policy's detail screen](policy-detail.md) at `/policies/{id}`, client-side, and the detail screen shows that policy rather than the one visited before it.
- verify: visible(locator="policy-detail.md#policy-heading", text="Policy PN-1001")
- code: app/web/src/PolicyList.tsx@1190425978c1
