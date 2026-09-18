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

The form that opens a [policy](../../concepts/policy.md). Its field names are the service's field
names, so a refusal [POST /api/policies](../../http/policy-desk-api.md#post-policies) makes about
`end_date` lands under the end-date input instead of arriving as a blob of JSON the operator has to
read.

Two of its inputs are conditional on the coverage type — the VIN for `auto`, the address for `home`
— which is the form's whole shape: what is required depends on a choice made two fields earlier, and
one rule (the umbrella prerequisite) depends on a record that is not on this screen at all.

## Components

### policy-form

- selector: `form`
- role: form
- name: New policy
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: `Tab` through the fields in document order, then `Enter` to submit.
- verify: visible(locator="#policy-form")
- parent: [New policy form](#new-policy-form)
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

Collects the policy number, holder email, coverage type, term and premium, plus whichever
conditional field the coverage type calls for.

### coverage-type-select

- selector: `#coverage_type`
- role: combobox
- name: Coverage type
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: `Tab` to the control, arrow keys to change the selection.
- parent: [New policy form](#new-policy-form)
- states: opens on `auto`.
- states: offers exactly the three coverage types the service accepts.
- verify: visible(locator="#coverage-type-select")
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

Decides which conditional field the form shows and which premium band the entry is judged against.

### vehicle-vin-field

- selector: `#vehicle_vin`
- role: textbox
- name: Vehicle VIN
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: `Tab` to the field.
- parent: [New policy form](#new-policy-form)
- exclusive-with: [property-address-field](#property-address-field)
- states: present only while the coverage type is `auto`.
- verify: visible(locator="#vehicle-vin-field")
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

Carries the VIN the auto policy covers, and carries the service's `vehicle_vin` message when the
field is refused.

### property-address-field

- selector: `#property_address`
- role: textbox
- name: Property address
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: `Tab` to the field.
- parent: [New policy form](#new-policy-form)
- exclusive-with: [vehicle-vin-field](#vehicle-vin-field)
- states: present only while the coverage type is `home`.
- verify: visible(locator="#property-address-field")
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

Carries the address the home policy covers, and carries the service's `property_address` message
when the field is refused.

### field-error-message

- selector: `span.field-error`
- role: generic
- name: none
- placement: width 20-80%, x 0-30%, y 10-100%
- keyboard: none, because it is read beside the field it belongs to.
- parent: [New policy form](#new-policy-form)
- states: present only beside a field the service refused.
- verify: visible(locator="#field-error-message", text="End date must be after the start date.")
- code: app/web/src/FieldError.tsx::FieldError@5e33630c096e

Shows the refusal for one field, next to that field, in the words the service used.

### duplicate-policy-alert

- selector: `p[role="alert"]`
- role: alert
- name: none
- placement: width 40-100%, x 0-30%, y 5-60%
- keyboard: none, because it is announced rather than operated.
- parent: [New policy form](#new-policy-form)
- states: present only after a refusal that belongs to no single field.
- verify: visible(locator="#duplicate-policy-alert", text="Duplicate Policy Number")
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

Reports a refusal that belongs to no single field — a duplicate policy number above all — at the top
of the form.

### create-policy-button

- selector: `#create-policy`
- role: button
- name: Create policy
- placement: width 0-40%, x 0-30%, y 10-100%
- keyboard: `Tab` to the button, `Enter` or `Space` to submit.
- verify: visible(locator="#create-policy-button")
- parent: [New policy form](#new-policy-form)
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

Submits the form, and stays disabled while the request is in flight so the same policy number is not
sent twice.

### new-policy-link

- selector: `#new-policy`
- role: link
- name: New policy
- verify: visible(locator="#new-policy-link")
- placement: width 0-40%, x 0-30%, y 0-20%
- keyboard: `Tab` to the link, `Enter` to follow it.
- parent: [New policy form](#new-policy-form)
- same-as: [New policy link](policy-list.md#new-policy-link)
- code: app/web/src/Nav.tsx::Nav@4b67472aa613

The same `Nav` region [policy-list.md](policy-list.md#new-policy-link) documents, rendered on this
screen too — one nav, four screens. It stays present on the form the link opens, rather than
disappearing once the operator has followed it here.

## Interactions

### submit-new-policy

- on: [create-policy-button](#create-policy-button)
- trigger: submit the new policy form
- role: button
- name: Create policy
- keyboard: `Enter` in any field, or `Enter`/`Space` on the button.
- verify: focusable(locator="#create-policy-button", activates="Enter")
- when: every rule the entry has to satisfy is satisfied.
- exclusive-with: [refuse-new-policy](#refuse-new-policy)
- does:
  - adds a policy that was not on the books before to the register, and navigates to its detail screen at `/policies/{id}` — so the operator lands on the record they just made rather than back on the register.
- verify: created(subject="policy pn-1001")
- verify: visible(locator="policy-detail.md#policy-heading", text="Policy PN-1001")
- verify: visible(locator="policy-detail.md#policy-summary", text="Draft")
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1

### refuse-new-policy

- on: [create-policy-button](#create-policy-button)
- trigger: submit the new policy form
- role: button
- name: Create policy
- keyboard: `Enter` in any field, or `Enter`/`Space` on the button.
- verify: focusable(locator="#create-policy-button", activates="Enter")
- when: the service refuses the entry.
- exclusive-with: [submit-new-policy](#submit-new-policy)
- does:
  - shows each field's refusal beside that field and stays on the form with the entry intact, rather than navigating away or printing the response body.
- verify: visible(locator="#field-error-message", text="Auto coverage needs the vehicle VIN.")
- verify: visible(locator="#policy-form")
- code: app/web/src/NewPolicy.tsx::NewPolicy@843f418d2cc1
