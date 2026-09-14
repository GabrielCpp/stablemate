### `test-subject` — the node documents a test double, not the product

Every `code:` citation on this node is test source: a mock, a fake declared in a test file, a
fixture helper. A book documents behaviour a user can assert against the running product; how
the product's own tests are built is an implementation detail of the test suite, and no claim
about it can be observed from outside. This is the one finding whose repair **is** removal —
the shared rule above protects claims about the product, and this node makes none.

1. **When the finding's `ref` is `<path>#code` — the page's own node — delete the file.** Every
   node on it goes with it; other findings on this page were not queued for that reason.
2. **Otherwise delete the node**: its heading and everything down to the next heading of the
   same or a higher level.
3. **Never keep the node by repointing `code:` at production code.** A mock's methods mirror
   the interface it doubles, and that interface is — or will be — documented by the node for
   the real implementation. Rewriting the mock's page into a second copy of it is not a repair.
4. If a product claim on the node has no other home, it belongs on the node for the real
   implementation; name that node in `doc_status` rather than moving the claim, which is
   another item's file.

Links from other pages into what you deleted now dangle; those files are other items' work and
doctor queues them. For a deleted node, check with `ostler doctor --path` on its file; for a
deleted page there is nothing left to check — confirm only that the file is gone.
