---
type: screen
slug: new-policy
title: New policy form
---
# New policy form

- route: `/policies/new`
- requires:
  - none; underwriting a policy needs nothing that came before it.
- params:
  - none
- entry: no; it is reached from
  [the register's New policy link](policy-list.md#new-policy-link).

The form that opens a [policy](../../concepts/policy.md). Its field names are the service's field
names, so a refusal [POST /api/policies](../../http/policy-desk-api.md#post-policies) makes about
`end_date` lands under the end-date input instead of arriving as a blob of JSON the operator has to
read.

Two of its inputs are conditional on the coverage type — the VIN for `auto`, the address for `home`
— which is the form's whole shape: what is required depends on a choice made two fields earlier, and
one rule (the umbrella prerequisite) depends on a record that is not on this screen at all.

## Components

### policy-form

- selector: `form[aria-label="New policy"]`
- role: form
- name: New policy
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: `Tab` through the fields in document order, then `Enter` to submit.
- parent: [New policy form](#new-policy-form)
- code: app/web/src/NewPolicy.tsx
- does: collects the policy number, holder email, coverage type, term and premium, plus whichever
  conditional field the coverage type calls for.
- verify: visible(locator="form:New policy")

### coverage-type-select

- selector: `#coverage_type`
- role: combobox
- name: Coverage type
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: `Tab` to the control, arrow keys to change the selection.
- parent: [New policy form](#new-policy-form)
- states: opens on `auto`.
- states: offers exactly the three coverage types the service accepts.
- code: app/web/src/NewPolicy.tsx
- does: decides which conditional field the form shows and which premium band the entry is judged
  against.
- verify: visible(locator="combobox:Coverage type")

### vehicle-vin-field

- selector: `#vehicle_vin`
- role: textbox
- name: Vehicle VIN
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: `Tab` to the field.
- parent: [New policy form](#new-policy-form)
- exclusive-with: [property-address-field](#property-address-field)
- states: present only while the coverage type is `auto`.
- code: app/web/src/NewPolicy.tsx
- does: carries the VIN the auto policy covers, and carries the service's `vehicle_vin` message
  when the field is refused.
- verify: visible(locator="textbox:Vehicle VIN")

### property-address-field

- selector: `#property_address`
- role: textbox
- name: Property address
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: `Tab` to the field.
- parent: [New policy form](#new-policy-form)
- exclusive-with: [vehicle-vin-field](#vehicle-vin-field)
- states: present only while the coverage type is `home`.
- code: app/web/src/NewPolicy.tsx
- does: carries the address the home policy covers, and carries the service's `property_address`
  message when the field is refused.
- verify: visible(locator="textbox:Property address")

### field-error-message

- selector: `span.field-error`
- role: generic
- name: none
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: none, because it is read beside the field it belongs to.
- parent: [New policy form](#new-policy-form)
- code: app/web/src/FieldError.tsx
- does: shows the refusal for one field, next to that field, in the words the service used.
- verify: visible(locator="text=End date must be after the start date.")

### duplicate-policy-alert

- selector: `p[role="alert"]`
- role: alert
- name: none
- placement: width 40-100%, x 0-30%, y 5-60%
- keyboard: none, because it is announced rather than operated.
- parent: [New policy form](#new-policy-form)
- code: app/web/src/NewPolicy.tsx
- does: reports a refusal that belongs to no single field — a duplicate policy number above all —
  at the top of the form.
- verify: visible(locator="alert", text="Duplicate Policy Number")

### create-policy-button

- selector: `form[aria-label="New policy"] button[type="submit"]`
- role: button
- name: Create policy
- placement: width 0-40%, x 0-30%, y 10-100%
- keyboard: `Tab` to the button, `Enter` or `Space` to submit.
- parent: [New policy form](#new-policy-form)
- code: app/web/src/NewPolicy.tsx
- does: submits the form, and stays disabled while the request is in flight so the same policy
  number is not sent twice.
- verify: visible(locator="button:Create policy")

## Interactions

### submit-new-policy

- on: [create-policy-button](#create-policy-button)
- trigger: submit the new policy form
- role: button
- name: Create policy
- keyboard: `Enter` in any field, or `Enter`/`Space` on the button.
- when: every rule the entry has to satisfy is satisfied.
- does:
  - adds a policy that was not on the books before to the register, and navigates to its detail screen at `/policies/{id}` — so the operator lands on the record they just made rather than back on the register.
- code: app/web/src/NewPolicy.tsx
- verify: created(subject="policy pn-1001")
- verify: visible(locator="heading:Policy PN-1001")
- verify: visible(locator="text=Draft")

### refuse-new-policy

- on: [create-policy-button](#create-policy-button)
- trigger: submit the new policy form
- role: button
- name: Create policy
- keyboard: `Enter` in any field, or `Enter`/`Space` on the button.
- when: the service refuses the entry.
- does:
  - shows each field's refusal beside that field and stays on the form with the entry intact, rather than navigating away or printing the response body.
- code: app/web/src/NewPolicy.tsx
- verify: visible(locator="text=Auto coverage needs the vehicle VIN.")
- verify: visible(locator="form:New policy")
