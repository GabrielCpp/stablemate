### `matches-repr-spelling` — a `matches=` pattern spelled against Python, not JSON

The book documents a JSON document, so `json_path(matches=...)` is matched against the value's
**JSON** spelling: the harness renders the resolved value with `json.dumps` before running the
pattern (a `str` value is the one exemption — it is matched as itself, unquoted). `None` reads
`null`, `True`/`False` read `true`/`false`, and a list or dict element quotes with `"`, never
`'`. A pattern spelling a bare, word-bounded `None`/`True`/`False` can only have been written
against `str(value)`/`repr(value)` and can never match a live document — it is not weak, it is
unsatisfiable:

```markdown
# unsatisfiable — the document never spells this
- verify: json_path(path="$.exit_code", matches="^None$")

# repaired — the JSON encoding of the same value
- verify: json_path(path="$.exit_code", matches="^null$")
```

The same repair applies inside an alternation or a larger pattern — change only the literal
token, keep every other character (anchors, escapes, the rest of the alternation) exactly as
written:

```markdown
# unsatisfiable
- verify: json_path(path="$.attempt", matches="^(None|-?[0-9]+)$")

# repaired
- verify: json_path(path="$.attempt", matches="^(null|-?[0-9]+)$")
```

**Do not also rewrite a bare `'` inside the pattern.** A quoted list or dict element does render
with `"` in JSON, but a `str` value is matched unquoted, so a pattern like
`matches="^\{'a': \[.+\]\}$"` against a field the book declares `type: string` is testing the
field's own literal content, apostrophe included, not a JSON container — rewriting the quote
there would break a pattern that was correct. Read the field's declared `type:` (or the method
signature `code:` cites) before touching a single-quote; only a bare, unquoted `None`/`True`/
`False` is unambiguous evidence of repr authorship, which is what this code alone checks for.

**If the sibling claim's own `semantics:`/prose spells the same value the Python way** (a
`does:` bullet that says "returns `None`" beside a `verify:` this code flags), fix the prose
too, in the same edit — a book that spells one fact two ways is the defect this code exists to
catch, not a coincidence to leave standing.
