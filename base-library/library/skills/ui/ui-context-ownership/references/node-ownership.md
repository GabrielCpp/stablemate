# A component owns only what it renders

Passing a ref to an element is fine. The defect is keeping a reference to a node another block
controls, or moving your own node out of the tree the framework manages. Another block can remove those
nodes at any time, and the framework does not know about the move.

## 2.1 Own nodes only

**Trigger.** A stored ref, an action or directive target, or a saved query result points at a node the
component did not render: a parent, a sibling, or content passed in as children or a slot.

**Fix.** Pass data or a callback to the owner, and let the owner act on its node. When a child needs to
position itself against a parent, the parent hands down a measurement or exposes a method.

**Counter-case.** A transient read inside one synchronous handler, such as measuring the parent's
bounding box, is fine when the reference is not stored.

**Proof.** Replace the slot content while the component stays mounted, then trigger the action. Assert
it reaches the current content.

## 2.2 Portals leave a placeholder

**Trigger.** A component moves its own node with `appendChild`, `insertBefore`, `replaceWith` or
similar. The usual targets are `document.body` and the fullscreen element.

**Fix.** Use the framework's portal primitive when it has one: React `createPortal`, Vue `Teleport`,
Angular CDK `Portal`. Otherwise write one shared portal helper and use it everywhere:

1. Before moving the node, insert a placeholder the component owns, such as a comment node, at the
   node's original position.
2. Move the node.
3. To move back, swap the node into the placeholder.
4. On destroy, swap back into the placeholder. If the placeholder is gone, remove the node.

**Counter-case.** None for a hand-rolled move. A component that moves nodes it owns between containers
it owns still breaks the framework's tracking.

**Proof.** Unmount while the node is moved. Assert nothing is left in the target and nothing throws.

## 2.3 Teardown assumes nothing outside

**Trigger.** A cleanup, destroy or unmount hook dereferences a node or object the component did not
create, with no check that it still exists.

**Fix.** Cleanup touches only what the component created. When it must touch an outside node, check
that the node exists and is still connected first.

**Why.** Frameworks treat a throw during teardown as fatal to the swap. Svelte 5 aborts the branch swap
and leaves a blank panel. React unmounts the whole tree up to the nearest error boundary.

**Proof.** Remove the outside node first, then unmount. Assert nothing throws.

## 2.4 Keys unique at the source

**Trigger.** A keyed list renders data built by merging, joining or flattening several sources, so one
id can appear twice.

**Fix.** Dedupe in the function that builds the list. The render sees a list that is already unique.

**Why.** Duplicate keys corrupt reconciliation. Some frameworks throw, in production builds too.

**Proof.** Give two sources the same id, as the producer can return it. Assert the screen shows one row.

## 2.5 Selection as id

**Trigger.** State holds an object copied out of a collection. After every reload or revert, code finds
the matching object again and reassigns it.

**Fix.** Store the selected id. Derive the object from the current collection, for example
`selected = derived(collection.find(item => item.id === selectedId))`. A stale object reference then
cannot exist.

**Counter-case.** The selection is a draft the user is editing apart from the collection. That is a copy
on purpose, and it belongs to a write session (1.2).

**Proof.** Reload the collection with the selected record changed. Assert the screen shows the new
values, and shows the empty state when the record is gone.
