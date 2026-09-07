---
type: concept
slug: live-source-documentation-guide
title: LiveSource documentation guide
---
# LiveSource documentation guide

`LiveSource` has one generic implementation: its module explains that additional callers use
the same implementation rather than a second one. The related concepts are therefore
complementary views, not implementation choices.

Use [LiveSource configuration fields](live-source-configuration.md) while constructing a
source or deciding whether accompanying local packages belong in `with_editable`. Use
[LiveSource — immutable bind-source generations](live-source.md) to understand staging,
installation, failure recovery, and generation retention. Use [LiveSource documentation
context](livesource-documentation-context.md) for a short orientation that distinguishes the
first two views.

- rule: select the configuration-fields view for constructor inputs, the immutable-generations view for lifecycle behavior, and the documentation-context view for an overview; all describe the one generic LiveSource implementation
