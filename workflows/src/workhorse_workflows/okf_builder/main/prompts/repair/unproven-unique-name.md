### `unproven-unique-name` — display-value glue with no distinctness claim

The template's bindable holes are display values (`.name`, `.label`, `.title`) and no
`unique-by:` claims a distinct key. Two stages both named "Fondations" render two identical
accessible names, and every locator assembled from the template matches both — the book can
only *warn* that a test finds *a* row, not prove it found *the* row.

Read the source of the collection the `one-per:` variable iterates over:

- If some key makes instances distinct — an id, a unique constraint, a dedup on insert — state
  the claim: `` unique-by: `stage.id` `` (one dot-path rooted at the iteration variable), and
  cite in prose the code that enforces it.
- If duplicates are genuinely possible, the warning is the truth: leave it standing and record
  what you read. Whether the app adds a distinguishing datum or the book waives it is a human's
  call — a `unique-by:` written without evidence converts an honest warning into a false
  promise, which is worse than the finding.
