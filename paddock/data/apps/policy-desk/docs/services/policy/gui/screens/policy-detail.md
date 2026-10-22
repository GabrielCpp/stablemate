---
type: screen
slug: policy-detail
title: Policy detail
---
# Policy detail

- route: `/policies/{id}`
- requires:
  - the policy exists; an id that is not on the books shows the service's refusal rather than an
    empty record.
- params:
  - `id` — the slug of the policy number, such as `pn-1001`.
- entry: `/policies/{id}`

One [policy](../../concepts/policy.md), read from
[GET /api/policies/{id}](../../http/policy-desk-api.md#get-policy), and the two things that can be
done to it: edit it, or cancel it.

The read is keyed on the route parameter rather than done once on mount, which is the part a
single-visit walkthrough never sees: following a link from one policy to another has to re-read, or
the second policy is shown under the first one's record.

## Components

### policy-heading

- selector: `h1`
- role: heading
- name: Policy PN-1001
- placement: width 40-100%, x 0-30%, y 0-20%
- keyboard: none, because it is read rather than operated.
- verify: visible(locator="#policy-heading", text="Policy PN-1001")
- parent: [Policy detail](#policy-detail)
- code: app/web/src/PolicyDetail.tsx::PolicyDetail@ad9440914800

Names the policy the screen is showing. Declared because it is what every navigation that lands
here observes: arriving is seeing *this* policy's number, and a check that says so needs something
in the book to point at.

### policy-summary

- selector: `dl`
- role: generic
- name: none
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: none, because it is read rather than operated.
- parent: [Policy detail](#policy-detail)
- states: a policy still open reads `Draft`, and an auto policy shows the vehicle VIN it was
  written against.
- verify: visible(locator="#policy-summary", text="Draft")
- verify: visible(locator="#policy-summary", text="1HGCM82633A004352")
- code: app/web/src/PolicyDetail.tsx::PolicyDetail@ad9440914800

States the policy's status, holder, coverage, term and premium, and the conditional field its
coverage type carries.

### edit-policy-link

- selector: `#edit-policy`
- role: link
- name: Edit policy
- placement: width 0-40%, x 0-30%, y 10-100%
- keyboard: `Tab` to the link, `Enter` to follow it.
- verify: visible(locator="#edit-policy-link")
- parent: [Policy detail](#policy-detail)
- code: app/web/src/PolicyActions.tsx::PolicyActions@0d875e76d278

Opens [the edit form](edit-policy.md) for this policy as a client route.

### cancel-policy-form

- selector: `form`
- role: form
- name: Cancel policy
- placement: width 40-100%, x 0-30%, y 20-100%
- keyboard: `Tab` to the confirmation field; `Enter` submits.
- parent: [Policy detail](#policy-detail)
- states: present only while the policy's status is `Draft`, so a cancelled policy offers no way
  to cancel it again.
- verify: visible(locator="#cancel-policy-form")
- code: app/web/src/PolicyActions.tsx::PolicyActions@0d875e76d278

Makes a cancellation something typed out — the policy's own number — rather than a button a stray
click can hit.

### new-policy-link

- selector: `#new-policy`
- role: link
- name: New policy
- verify: visible(locator="#new-policy-link")
- placement: width 0-40%, x 0-30%, y 0-20%
- keyboard: `Tab` to the link, `Enter` to follow it.
- same-as: [New policy link](policy-list.md#new-policy-link)
- parent: [Policy detail](#policy-detail)
- code: app/web/src/Nav.tsx::Nav@4b67472aa613

The same `Nav` region [policy-list.md](policy-list.md#new-policy-link) documents, rendered on this
screen too — one nav, four screens. Opens [the new policy form](new-policy.md) as a client route,
without reloading the document.

## Interactions

### cancel-policy

- on: [cancel-policy-form](#cancel-policy-form)
- trigger: submit the cancellation form
- role: button
- name: Cancel policy
- keyboard: `Enter` in the confirmation field, or `Enter`/`Space` on the button.
- when: the typed confirmation is the policy's own number.
- exclusive-with: [refuse-cancellation](#refuse-cancellation)
- does:
  - cancels the policy and shows it at status `Cancelled`, with the cancellation form gone.
- verify: visible(locator="#policy-summary", text="Cancelled")
- code: app/web/src/PolicyActions.tsx::PolicyActions@0d875e76d278

### refuse-cancellation

- on: [cancel-policy-form](#cancel-policy-form)
- trigger: submit the cancellation form
- role: button
- name: Cancel policy
- keyboard: `Enter` in the confirmation field, or `Enter`/`Space` on the button.
- when: the typed confirmation is anything else.
- exclusive-with: [cancel-policy](#cancel-policy)
- does:
  - leaves the policy at `Draft` and says beside the field what has to be typed.
- verify: visible(locator="#cancel-policy-form", text="Type the policy number to confirm the cancellation.")
- code: app/web/src/PolicyActions.tsx::PolicyActions@0d875e76d278
