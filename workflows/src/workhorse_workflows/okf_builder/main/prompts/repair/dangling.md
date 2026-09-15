### `dangling` — a `code:` citation points at nothing doctor can resolve

The node claims to be grounded in a `code:` target doctor could not find — the file is
gone, or the symbol is not in it. Every check and obligation on the node hangs off a
citation nobody can open.

**When the context carries `relocated_to`, the move is already confirmed — repoint to
it, do not re-derive it.** `relocated_to` is set only when the symbol name is unique
across the whole source inventory and lives at exactly that one other path; a name
that recurs anywhere else is left for you to judge instead, never guessed by tooling.
So when it is present:

1. Open the path in `relocated_to` and confirm the symbol there is the same thing this
   node's claims are actually about — same behavior, same role. `relocated_to` says
   where the name went, not that the node's prose still fits it.
2. Repoint the citation to `relocated_to` and say so in the node's prose (one clause is
   enough).

**When the context carries no `relocated_to`**, the symbol's name was not unique
elsewhere, or nothing shares it — this is not a confirmed move, and re-pointing to a
same-named neighbour on your own guess is the canonical wrong fix (`main.py::__main__`
→ `main.py::main`, a symbol that exists, is a different thing, and was already
documented by another node). Instead:

1. Read the mechanical source inventory at
   `{{ workhorse_var('source_inventory_path') }}` (if it exists) and search it for the
   symbol name, to see whether the code moved somewhere the predicate could not
   single out.
2. If the inventory does not settle it, grep the source under
   `{{ workhorse_var('source_root') }}` for the symbol's definition.
3. **Open the candidate and confirm it is the same thing** before repointing, exactly
   as for a confirmed `relocated_to`.

If the symbol is genuinely **gone** — deleted, its behavior removed — the node is
documenting something the product no longer does. Removing the citation alone is the
one move that is never right: it leaves the claims standing with nothing under them.
Say in `doc_status` that the documented behavior no longer exists and leave the
finding standing — deciding whether the node itself goes is a judgment about the
product, not about a bullet, and it belongs to a reader who can see the whole picture.
