---
type: concept
slug: author-backlogged-fixture-context
title: Author backlogged fixture contexts
---
# Author backlogged fixture contexts

`backlogged` is shared test setup, not an alternative implementation of either Author node. It
creates a committed repository containing an approved milestone, one screen, a runbook and a
mockup, with no epics and no records on the debt register. The fixture's committed, epics-free
baseline lets reconciliation observe the normal first-run skip.

Two fixtures build on it. `with_epic` adds one authored epic, so story mode has an epic to seed
into. `with_records` adds two open records to the [debt register](../../ostler/concepts/the-debt-register.md)
in the artifacts repo, one of them with a body. Story selection and the story-edit add path read
those records.

Neither fixture supersedes the other. Use the method documentation for the node whose behavior a
scenario exercises: reconciliation needs the committed baseline with no `docs/epics`, while story
selection needs open records on the register.

- rule: use `verify_reconcile` for the committed epics-free baseline and `seed_story` for the register with open records, because they exercise different node behavior
