---
type: concept
slug: inventory-check-decision
title: Inventory check decision
---
# Inventory check decision

`InventoryCheck` returns both an operational decision and an explanation of the inventory
precedence branch that produced it. The schema declares `needs_plan` as a boolean defaulting to
false and `check_note` as a string defaulting to an empty value; it records no preference between
the fields because they answer different questions.

Use `needs_plan` to decide whether the granularity planner must define unit rules. Use
`check_note` to present the human-readable explanation of the selected inventory-precedence
branch. Neither field replaces the other, and no ranking exists.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck`
- rule: use `needs_plan` for the planning decision and `check_note` for its precedence explanation; neither field is preferred
