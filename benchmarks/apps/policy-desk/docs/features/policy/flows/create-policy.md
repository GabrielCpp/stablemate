---
type: flow
slug: create-policy
title: Underwrite a policy
---
# Underwrite a policy

- start: [Policy register](../gui/screens/policy-list.md)
- steps:
  - Open the register and read what is already on the books from
    [the policy table](../gui/screens/policy-list.md#policy-table).
  - Follow [New policy](../gui/screens/policy-list.md#new-policy-link) to
    [the form](../gui/screens/new-policy.md), client-side.
  - Choose a coverage type, which decides
    [which conditional field the form asks for](../gui/screens/new-policy.md#vehicle-vin-field),
    and fill in the term and the premium.
  - Submit. A refusal comes back
    [beside the field it belongs to](../gui/screens/new-policy.md#field-error-message) and the form
    keeps what was typed; an acceptance
    [lands on the new policy's detail screen](../gui/screens/new-policy.md#submit-new-policy).
- end: [Policy detail](../gui/screens/policy-detail.md), showing the new policy at status `Draft`
  with the premium that was entered.
- verify: visible(locator="heading:Policy PN-1001")
- verify: visible(locator="text=Draft")
- tests:

The journey the desk exists for, and the one that makes the conditional rules observable: what the
form must carry is not fixed, it is chosen two fields earlier, and one rule — umbrella coverage
needing an underlying policy for the same holder — cannot be decided from this screen at all. A walk
that only ever submits a valid auto policy sees none of that, and neither does a walk that submits an
invalid one without reading where the refusal landed.

The step that is easiest to lose is the last one. Creating the policy and returning to the register
looks like success from the API's side, and the record is genuinely there — but the operator is then
on a list rather than on the thing they just made, and the journey's end state is not what the book
says it is.
