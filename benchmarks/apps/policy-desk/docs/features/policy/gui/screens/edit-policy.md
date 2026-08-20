---
type: screen
slug: edit-policy
title: Edit policy form
---
# Edit policy form

- route: `/policies/{id}/edit`
- requires:
  - the policy exists; the form is filled from the record it is editing.
- params:
  - `id` — the slug of the policy number, such as `pn-1001`.
- entry: no; it is reached from
  [the detail screen's Edit policy link](policy-detail.md#edit-policy-link).

The form that changes a [policy](../../concepts/policy.md) already on the books. It opens filled
from the record, and it keeps one thing the operator never sees: the `version` the record was at
when the form was opened.

That token is what it sends back with the edit, and what
[PUT /api/policies/{id}](../../http/policy-desk-api.md#put-policy) compares against the ledger. A
form that drops it turns a refused overwrite into a silent one, which is a defect no single-editor
walkthrough can produce.

## Components

### edit-form

- selector: `form[aria-label="Edit policy"]`
- role: form
- name: Edit policy
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: `Tab` through the fields in document order, then `Enter` to submit.
- parent: [Edit policy form](#edit-policy-form)
- states: opens filled from the stored record — the holder, the term and the premium as they stand.
- code: app/web/src/EditPolicy.tsx
- does: offers the fields an edit may change, and neither shows nor sends the policy number.
- verify: visible(locator="form:Edit policy")

### stale-policy-alert

- selector: `p[role="alert"]`
- role: alert
- name: none
- placement: width 40-100%, x 0-30%, y 5-60%
- keyboard: none, because it is announced rather than operated.
- parent: [Edit policy form](#edit-policy-form)
- code: app/web/src/EditPolicy.tsx
- does: reports that the policy moved under the form, and says to reload — rather than letting the
  save look as though it landed.
- verify: visible(locator="alert", text="Stale Policy")

### save-policy-button

- selector: `form[aria-label="Edit policy"] button[type="submit"]`
- role: button
- name: Save policy
- placement: width 0-40%, x 0-30%, y 10-100%
- keyboard: `Tab` to the button, `Enter` or `Space` to submit.
- parent: [Edit policy form](#edit-policy-form)
- code: app/web/src/EditPolicy.tsx
- does: submits the edit together with the version the form was opened at.
- verify: visible(locator="button:Save policy")

## Interactions

### save-edit

- on: [save-policy-button](#save-policy-button)
- trigger: submit the edit form
- role: button
- name: Save policy
- keyboard: `Enter` in any field, or `Enter`/`Space` on the button.
- when: the edit is acceptable and the quoted version is the policy's current one.
- does:
  - saves the edit and navigates back to [the detail screen](policy-detail.md), which shows the new values.
- code: app/web/src/EditPolicy.tsx
- verify: visible(locator="heading:Policy PN-1001")
- verify: visible(locator="text=$1350.00")

### refuse-stale-edit

- on: [save-policy-button](#save-policy-button)
- trigger: submit the edit form
- role: button
- name: Save policy
- keyboard: `Enter` in any field, or `Enter`/`Space` on the button.
- when: the policy has been written since the form was opened.
- does:
  - leaves the stored record as it is and says on the form that it moved, rather than navigating away as though the edit had landed.
- code: app/web/src/EditPolicy.tsx
- verify: visible(locator="alert", text="Stale Policy")
- verify: conflict_on_stale(subject="policy pn-1001", token="version")
