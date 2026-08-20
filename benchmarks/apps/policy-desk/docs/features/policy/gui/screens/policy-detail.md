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
- entry: yes; the id is in the path, so this screen is a deep link an operator can be sent
  directly.

One [policy](../../concepts/policy.md), read from
[GET /api/policies/{id}](../../http/policy-desk-api.md#get-policy), and the two things that can be
done to it: edit it, or cancel it.

The read is keyed on the route parameter rather than done once on mount, which is the part a
single-visit walkthrough never sees: following a link from one policy to another has to re-read, or
the second policy is shown under the first one's record.

## Components

### policy-summary

- selector: `dl`
- role: generic
- name: none
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: none, because it is read rather than operated.
- parent: [Policy detail](#policy-detail)
- code: app/web/src/PolicyDetail.tsx
- does: states the policy's status, holder, coverage, term and premium, and the conditional field
  its coverage type carries.
- verify: visible(locator="text=Draft")
- verify: visible(locator="text=1HGCM82633A004352")

### edit-policy-link

- selector: `a[href$="/edit"]`
- role: link
- name: Edit policy
- placement: width 0-40%, x 0-30%, y 10-100%
- keyboard: `Tab` to the link, `Enter` to follow it.
- parent: [Policy detail](#policy-detail)
- code: app/web/src/PolicyActions.tsx
- does: opens [the edit form](edit-policy.md) for this policy as a client route.
- verify: visible(locator="link:Edit policy")

### cancel-policy-form

- selector: `form[aria-label="Cancel policy"]`
- role: form
- name: Cancel policy
- placement: width 40-100%, x 0-30%, y 20-100%
- keyboard: `Tab` to the confirmation field; `Enter` submits.
- parent: [Policy detail](#policy-detail)
- states: present only while the policy's status is `Draft`, so a cancelled policy offers no way
  to cancel it again.
- code: app/web/src/PolicyActions.tsx
- does: makes a cancellation something typed out — the policy's own number — rather than a button
  a stray click can hit.
- verify: visible(locator="form:Cancel policy")

## Interactions

### cancel-policy

- on: [cancel-policy-form](#cancel-policy-form)
- trigger: submit the cancellation form
- role: button
- name: Cancel policy
- keyboard: `Enter` in the confirmation field, or `Enter`/`Space` on the button.
- when: the typed confirmation is the policy's own number.
- does:
  - cancels the policy and shows it at status `Cancelled`, with the cancellation form gone.
- code: app/web/src/PolicyActions.tsx
- verify: visible(locator="text=Cancelled")

### refuse-cancellation

- on: [cancel-policy-form](#cancel-policy-form)
- trigger: submit the cancellation form
- role: button
- name: Cancel policy
- keyboard: `Enter` in the confirmation field, or `Enter`/`Space` on the button.
- when: the typed confirmation is anything else.
- does:
  - leaves the policy at `Draft` and says beside the field what has to be typed.
- code: app/web/src/PolicyActions.tsx
- verify: visible(locator="text=Type the policy number to confirm the cancellation.")
