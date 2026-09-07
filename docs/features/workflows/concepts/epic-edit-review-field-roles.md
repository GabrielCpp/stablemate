---
type: concept
slug: epic-edit-review-field-roles
title: Epic edit review field roles
---
# Epic edit review field roles

`EpicEditReview` carries a disposition and its reviewer explanation as separate, complementary
parts of one review result. `status` states whether the proposed edit is approved, needs rework,
or is blocked. `notes` carries the explanation accompanying that disposition. Neither field is a
replacement for the other, and the source declares no ranking between them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditReview`
- rule: use `status` to determine the review disposition and `notes` to read its explanation; no selection rule applies because the fields serve distinct roles in the same review.
