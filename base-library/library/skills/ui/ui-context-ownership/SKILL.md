---
name: ui-context-ownership
description: "The ownership contract for UI code, framework-neutral: a response written into a context the user already left, a write session racing a context switch, state read after an await, a lock split across several flags, a component holding or moving a node it does not render, a teardown that throws, a repeated list key, a selection stored as a copied object. Load when writing or reviewing an async handler, a fetch fired by navigation or a selection change, an edit-then-save flow, a dialog that starts a write, a portal or any code that moves a node, an element ref, a cleanup hook, a keyed list, or a selection held in state. The testing-component skill proves these rules in tests. Applies to UI source files."
applyTo: "**/*.tsx,**/*.jsx,**/*.ts,**/*.svelte,**/*.vue,**/*.dart"
tags: [standards]
---

# The Context Ownership Contract

A piece of code may only touch what it owns. Three owners cover every rule here:

- An **async response** owns the context it was sent for.
- A **component** owns the nodes it renders.
- A **selection** owns an id. The object is derived from the id.

Every rule catches one way a piece of code outlives its owner or reaches past it.

This skill decides what the component does. {{ skill_link("testing-component") }} decides how a test
proves it: each guard here is a cell of that skill's state matrix, and a held answer is how the test
reaches the cell. A framework skill supplies the primitives.

## Definitions

- **Context**: whatever the screen is scoped to, such as the selected account, record, filter, tab or
  date range. The user changes it by navigating or selecting.
- **Read**: a request whose result only fills the screen. Throwing it away costs nothing.
- **Write session**: an edit the user builds up, then saves. It runs from the first request to the
  confirmed final write.
- **One-off write**: a single write the user confirms in one gesture, such as a dialog's OK button.
- **Capture**: copy a value into a local before an await, then use only the local after it.

## Trigger table

Scan this table against the code or the diff. Each row is a shape you can find by reading or grepping.
When a row fires, open its reference file for the fix, the counter-case and the proof.

| # | Trigger | Rule |
| --- | --- | --- |
| 1.1 | A response handler assigns state with no check that its request is still the latest | Latest read wins |
| 1.2 | A control that changes context stays enabled while edits are unsaved or a save is in flight | Lock the write session |
| 1.3 | A dialog's confirm handler reads page state after its first await | Capture at confirm |
| 1.4 | An async function reads mutable or reactive state after its first await, or queued work reads state when it runs | Capture before await |
| 1.5 | Two controls compute "locked" from different subsets of flags | One flag per lock |
| 2.1 | A stored ref points at a parent, a sibling, or content passed in as children or a slot | Own nodes only |
| 2.2 | A component moves its own node with `appendChild`, `insertBefore` or similar | Portals leave a placeholder |
| 2.3 | A cleanup or destroy hook dereferences a node or object the component did not create | Teardown assumes nothing outside |
| 2.4 | A keyed list renders data built by merging or joining sources | Keys unique at the source |
| 2.5 | State holds an object copied from a collection, and code resyncs it after a reload | Selection as id |

Rows 1.x live in [references/async-context.md](references/async-context.md). Read it for any request,
await, save flow or lock. Rows 2.x live in [references/node-ownership.md](references/node-ownership.md).
Read it for any ref, portal, cleanup hook, keyed list or selection.

## Done

A review or an implementation is done when every row has been checked against the code in scope. Each
hit is fixed or has its counter-case named in the review. Each guard has the test its rule names, and
that test was seen red with the guard removed.

## Rejected designs

- **Per-response guards on writes.** Every future request has to remember the check, and one forgotten
  check is a silent wrong write. Lock the session instead.
- **A global request queue.** It serializes unrelated work, and the screen stalls behind requests from
  a context the user already left.
