### `missing-code-symbol` — a `code:` citation names a symbol its file no longer declares

The node claims to be grounded in `path::symbol`, and the file exists but the symbol is not
in it. The code moved on — a rename, a move to another module, a refactor that split it —
and the citation did not. The book is now claiming grounding it does not have, which is why
this is an error: every check and obligation on the node hangs off a symbol nobody can open.

**The repair is re-grounding, and the new target comes from the source, never from the
finding.** For each citation:

1. Read the mechanical source inventory at `{{ workhorse_var('source_inventory_path') }}`
   (if the file exists — it is written by the coverage re-scan, so a pure repair round may
   predate it) and search it for the symbol name. It lists every declared symbol per file,
   so a moved symbol shows up under its new path immediately.
2. If the inventory does not settle it, grep the source under
   `{{ workhorse_var('source_root') }}` for the symbol's definition — the `def`/`func`/
   `class`/`function` line, not call sites.
3. **Open the candidate and confirm it is the same thing** — same behavior, same role in the
   node's claims — before repointing. A same-named symbol in another module can be a
   different thing entirely, and `main.py::__main__` → `main.py::main` is the canonical
   wrong fix: a symbol that exists, is a different thing, and was already documented by
   another node.
4. If the symbol was **renamed or moved**, repoint the citation and say so in the node's
   prose (one clause is enough). If it was **split**, cite the piece this node's claims are
   actually about — or both, one `code:` per bullet.

If the symbol is genuinely **gone** — deleted, its behavior removed — the node is
documenting something the product no longer does. Removing the citation alone is the one
move that is never right: it leaves the claims standing with nothing under them. Say in
`doc_status` that the documented behavior no longer exists and leave the finding standing —
deciding whether the node itself goes is a judgment about the product, not about a bullet,
and it belongs to a reader who can see the whole picture.
