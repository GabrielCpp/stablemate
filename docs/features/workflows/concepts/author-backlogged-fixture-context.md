---
type: concept
slug: author-backlogged-fixture-context
title: Author backlogged fixture contexts
---
# Author backlogged fixture contexts

`backlogged` is shared test setup, not an alternative implementation of either Author node. It
creates a committed repository containing a two-bullet backlog and a roadmap, with no epics or
OKF book. The fixture's committed, epics-free baseline lets reconciliation observe the normal
first-run skip; the same named backlog supplies the identities that backlog adoption assigns
before story selection or decomposition.

Neither method supersedes the other. Use the method documentation for the node whose behavior a
scenario exercises: reconciliation needs the committed baseline with no `docs/epics`, while
backlog adoption needs the unnamed two-bullet backlog.

- rule: use `verify_reconcile` for the committed epics-free baseline and `adopt_backlog` for the unnamed backlog; neither method is preferred because they exercise different node behavior
