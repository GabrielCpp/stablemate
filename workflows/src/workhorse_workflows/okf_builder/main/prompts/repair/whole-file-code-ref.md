### `whole-file-code-ref` — a section node's `code:` names the file, not the part

The node documents a **part** — a component, an endpoint, a command, a method, a field, a
step — and its `code:` bullet names a bare path with no `::symbol`. Naming the file that
contains the part says only where to start looking. Every obligation on the node then hangs
off a reference nobody can resolve to one thing, and two sibling nodes citing the same file
are indistinguishable from each other by their grounding alone.

This finding is already narrowed twice before you see it, so **it is never "the file really
is the unit"**:

- A node whose type documents a whole page's subject (`screen`, `cli`, `server`, `concept`,
  `format`, `flow`, `runbook`, `environment`, `fixture`) is exempt — the file *is* its unit.
- A citation to a file with no symbol grammar — an `.html`, a `compose.yml`, a Maestro
  `.yaml`, anything outside `.go` `.py` `.ts` `.tsx` `.php` `.twig` — is exempt, because
  there is no `path::symbol` the symbol check would accept.

So the file named in this finding **does** declare symbols, and one of them is what this
node is about.

**The repair reads the source; it does not guess from the node's name.** For each citation:

1. Open the cited file. Read the node's claims — its `does:`/`states:` bullets, its checks —
   and find the declaration that implements *those*, not the one whose name is closest to
   the node's id.
2. Repoint the bullet at `path::symbol`. Leave the `@digest` off; it is stamped when the
   turn commits, and a hand-written one is wrong.
3. If the node's claims are spread across **several** declarations in that file, that is
   several citations — one `code:` bullet each — not one bullet naming the file again.

If the file declares exactly one top-level symbol, the repair is mechanical: cite it. If you
open the file and find the node's claims are about **the whole module** rather than any part
of it, the node is typed wrong — a page-level subject written as a section — and that is a
judgment about the book's shape, not about a bullet. Say so in `doc_status` and leave the
finding standing rather than inventing a symbol to satisfy it.
