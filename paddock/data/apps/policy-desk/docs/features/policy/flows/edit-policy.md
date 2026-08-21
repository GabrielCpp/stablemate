---
type: flow
slug: edit-policy
title: Amend a policy on the books
---
# Amend a policy on the books

- start: [Policy register](../gui/screens/policy-list.md)
- steps:
  - Open the register and follow a policy number to
    [its detail screen](../gui/screens/policy-list.md#open-policy), client-side.
  - Follow [Edit policy](../gui/screens/policy-detail.md#edit-policy-link) to
    [the edit form](../gui/screens/edit-policy.md), which opens filled from the record and holds the
    version it was opened at.
  - Change the holder, the term or the premium and save. The edit carries that version, and
    [is refused if the policy moved meanwhile](../gui/screens/edit-policy.md#refuse-stale-edit).
  - An accepted edit
    [returns to the detail screen](../gui/screens/edit-policy.md#save-edit), showing the new values
    at the next version.
- end: [Policy detail](../gui/screens/policy-detail.md), showing the amended values.
- verify: visible(locator="heading:Policy PN-1001")
- verify: conflict_on_stale(subject="policy pn-1001", token="version")
- tests:

This is the journey that makes the version token observable. The form is opened against one version;
only a save quoting that number is applied, and an editor who came back to a record that moved is
told so rather than served. The difference between a compare-and-swap and an unconditional write
cannot be seen from a single happy path — one operator editing one policy passes either way.

It is also the journey that most needs its navigation walked rather than inferred. Every step
between the register and the form is a client route, and a link that stops navigating, or a detail
screen that keeps showing the previous policy after the id changes, leaves every API call in the
journey answering correctly while the journey itself is broken.
