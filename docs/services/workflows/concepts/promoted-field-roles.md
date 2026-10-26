---
type: concept
slug: promoted-field-roles
title: Promoted record field roles
---
# Promoted record field roles

`Promoted` in `workflows/src/workhorse_workflows/author/shared/schemas/main.py` reports two
complementary facts about one story-mode promotion. `record_id` names the register record that was
closed. `reason` is the text the close wrote on that record: the story that now stands for it and
the epic that story belongs to.

The fields are not competing implementations and neither ranks above the other. Read `record_id`
to learn which record changed, and read `reason` to learn which story replaced it. Read both when
a caller needs the complete result.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Promoted` @c0c7fb10e846
- rule: use `record_id` for the record that was closed and `reason` for the story and epic that replaced it, because neither field substitutes for the other
