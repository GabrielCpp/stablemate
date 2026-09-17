### `undetermined-provided-fact` — a provided fact whose source the book does not state

A `provides:` entry on this `fixture` node states **neither** `from:`/`read:`
**nor** `is:` — or states **both**. The finding names the key. A fact a fixture provides is
either *observed* from one of the fixture's own steps, or *asserted* by the way the fixture is
built, and nothing but the book can say which:

| spelling | means |
| --- | --- |
| `- from: [<step>](#<step>)` plus optional `- read: <path>` | **Observed.** `<step>` is one of this fixture's own `## Steps`; the harness parses that step's stdout as JSON and reads `<path>` out of it. `read:` defaults to the key's own name. |
| `- is: <value>` | **Asserted.** The fixture's construction makes this value true and no step prints it. |

Exactly one of the two. Both is a contradiction — a value cannot be simultaneously read out of a
step and fixed by construction, and the harness would have to pick a winner the book did not
name. Neither leaves the harness to guess, which is what it used to do: it parsed the *last*
step's whole stdout as JSON, which was right for the fixtures whose last step happened to print
JSON and aborted every other scenario inside `json.loads`, blaming a step nobody had pointed at.

**Extraction is eager**, so this is not a defect only the checks that reference the key pay for:
one undetermined entry withholds every obligation whose arrangement reaches this fixture — through
`needs:` too — as the compile gap of the same name. A key nobody cites kills the scenario exactly
as hard as one that is cited.

```markdown
- provides:
  - id — the seeded account's id
    - from: [seed-it](#seed-it)
    - read: account.id
  - count — how many widgets the directory holds
    - is: 0
```

**Pick by asking what would have to run for the value to be known.** If the answer is "a step
prints it", that step is the `from:` target — and it must be a step of *this* fixture, not of
another one. If the answer is "nothing; the arrangement makes it so", write `is:` with the
literal.

If neither fits because the entry is not a value at all — a sentence explaining why the
arrangement matters, a reason a read is expected to fail — then it is **not a provided fact**.
Delete the entry and put the sentence in the book's prose, where it is documentation rather than
something a `@<fixture>.<key>` reference could be pointed at. Say so in the prose, so the next
author does not silently re-add it.

A scaffolded `- provides:` with nothing under it does not trip this: the finding reads the
entries that exist. An entry with a headline and no children does.
