---
type: concept
slug: dashboard-active-pane-documentation-scope
title: Dashboard active-pane documentation scope
---
# Dashboard active-pane documentation scope

`groom/groom/assets/dashboard.js::loadActivePane` is one function, not a set of alternative
implementations. It reads the store's `mode` and, on an exact match, invokes the Files pane
loader for `files` or the Changes pane loader for `diff`; every other mode is a no-op.

Read [Dashboard active pane loader](dashboard-active-pane-loader.md) for the complete dispatch
contract: the caller relationship to repository selection, the mode source, the error-handling
and state-mutation guarantees, and the method's algorithm. Read [Dashboard active-pane flow
selection](dashboard-active-pane-flow-selection.md) when the question is which downstream flow —
the workspace-file flow or the working-tree-diff flow — a given mode reaches; it names the two
flows the dispatcher routes to rather than restating the dispatcher's own contract. Neither
concept replaces the other or is deprecated.

- rule: use Dashboard active pane loader for the dispatcher's complete contract, and Dashboard active-pane flow selection for identifying which of the two downstream flows a mode routes to; they document one function from two complementary angles rather than competing implementations
