---
type: concept
slug: epic-selection-documentation-roles
title: Epic selection documentation roles
---
# Epic selection documentation roles

`_pick_epic` performs both sides of the selection outcome: it obtains the applicable queue, finds
the first pending entry, and constructs the `EpicChoice` returned to later nodes. Its callers supply
different completion predicates, so the algorithm and the result fields are complementary views of
the same selector rather than competing implementations.

Use [Author main epic selection](author-main-epic-selection.md) to determine the queue source,
completion evaluation, and selected-epic resolution. Use [Epic choice field
roles](epic-choice-field-roles.md) to interpret the verdict, selected paths, reason, and progress in
the resulting `EpicChoice`. Neither view is ranked above or replaces the other; understanding a
selection requires both.

- rule: use Author main epic selection for how `_pick_epic` chooses work and Epic choice field roles for the meaning of its `EpicChoice` result; neither concept replaces the other
