---
name: structured-parsing
description: "Parse, don't match — a format with a grammar (Markdown, YAML frontmatter, JSON/JSONC, Python, Go/TypeScript/PHP/Twig source, a unified diff) is read with its parser, never with a regex over its raw text. Covers the parser-per-format table, the ostler.markdown query API (sections, bullets, tables, links, frontmatter), where regex is still correct (log lines, slugifiers, identifier validators, our own line protocols), and how to declare an exemption in scripts/check_parsers.py. Load when writing or reviewing code that reads a document, extracts a symbol, scrapes an agent reply, or reaches for `re`."
applyTo: "**/*.py"
tags: [standards, backend]
---

# Parse, don't match

> A format with a grammar has a parser. Read it with that parser. A regex over its raw
> text is the same parser re-implemented without its cases — and it fails **silently**,
> in both directions.

That last word is the whole argument. A hand-written matcher does not raise when it is
wrong; it returns a confident answer that happens to be false, and the caller has no way to
tell. Every defect below shipped, ran for months, and was found by reading the code rather
than by a failure.

## The five that were real

**A URL truncated every workspace config.** `load_jsonc` stripped comments with
`re.sub(r"//[^\n]*", "", text)`. A regex does not know what a string literal is, so
`{"url": "https://example.com"}` became `{"url": "https:` and then reported itself as
invalid JSON. This was the parser for VSCode `.code-workspace` files — files that routinely
hold URLs and `//` paths. Now `json5.loads`.

**Three frontmatter fences disagreed about what closes one**, plus a fourth hand-written
line scan. Between them they returned *no frontmatter at all* for a CRLF file, for a file
whose closing `---` carried a trailing space, and for one with no newline after the closing
fence — three total losses, each reported as "this document has no frontmatter". They also
read a **4-space-indented** `---` inside a YAML block scalar as the terminator and split the
document in the wrong place. Now one `front_matter` token from the parser.

**Links were matched inside fenced code blocks.** The link regex ran over a copy of the
document with code spans blanked out by *another* regex, approximating what the token
stream already knew exactly. A link in a code span is simply not a `link_open` token, so
the approximation became structurally true and the masking hack was deleted.

**A commented-out export was a unit the book owed coverage for.** `ostler`'s symbol front
end read Go, TypeScript, PHP and Twig with a declaration regex per language, and a regex
matches text — so `/* export function ghost() {} */` entered the coverage *denominator*, a
name inside a template literal grounded a `code:` citation, and an imported `type Auth`
grounded one too (the facade bug the module was extracted to kill, in TypeScript). It failed
the other way at the same time: `export abstract class`, `export const {a, b} = …` and Go's
grouped `type (…)` were shapes the alternation did not spell, so a *correct* citation
reported `missing-code-symbol` with no edit that could clear it. Across three real repos the
switch to tree-sitter dropped 71 names it had been reporting as declarations and admitted
2,274 real ones it had missed. Now `ostler.syntax`.

**A test name was truncated at the comma inside it.** `ostler`'s QA context read the bullet
citing tests (`verify:` then, `tests:` now) with one regex whose symbol group was `[^`,]+`, so a bullet citing a real test —
`… > exports the live editor through canonical XML, revokes its object URL, and clears the
named status` — was read as `… > exports the live editor through canonical XML`. That name
matches nothing, so the grounding gate reported a correct citation as citing a test that
does not exist, and a story burned four documentation review passes being told to repair
something that was already right. The comma was inside an inline-code span the whole time;
the parser knew where the span ended and the regex could not. Now `markdown.all_code_spans`
plus `str.partition("::")`.

Markdown **tables** were a sixth, quieter case: the parser ran on the bare `commonmark`
preset, so every table in the library's docs came back as an undifferentiated paragraph and
any caller wanting a row had no option but to split on `|` itself.

## The parser for each format

| Format | Use | Not |
| --- | --- | --- |
| Markdown (sections, bullets, tables, links) | `ostler.markdown.split(text)` → `MarkdownDoc` | `^#`, `^\s*-`, `\[..\]\(..\)`, `^\|` |
| Markdown frontmatter | `ostler.markdown.split(...).frontmatter` (a dict) | `\A---\n(.*?)\n---` |
| …in farrier, which needs frontmatter only | `farrier.frontmatter` — `split_front_matter`, `frontmatter_tags`, `frontmatter_metadata`, `banner_sources`, `first_heading` | a second fence regex |
| YAML | `yaml.safe_load` | `^key:\s*(.+)$`, or `line.split(":", 1)` |
| JSON with comments / trailing commas | `json5.loads` (`workhorse_workflows.kit.load_jsonc`) | strip-comments-then-`json.loads` |
| A JSON object embedded in agent prose | `json.JSONDecoder().raw_decode` scanned from each `{` (`runner/extract._json_objects`) | `re.search(r"\{.*\}", DOTALL)` |
| Python source | `ast` | `^(?:async\s+)?(?:def\|class)\s+(\w+)` |
| Go, TypeScript/TSX, PHP, Twig source | `ostler.syntax.parse(language, text)` — tree-sitter | `^func\s+(\w+)`, `^export\s+(?:class\|const)\s+(\w+)` |
| Unified diff | `unidiff.PatchSet` | `^@@ -\d+ \+\d+ @@` |
| A path, and where its suffix begins | `pathlib.Path(p).suffix` against a set | `\.(?:py\|tsx?\|go\|ya?ml)` |
| A ref with a declared separator (`path::name`) | `str.partition("::")` — the right half is the name, commas and all | `(?P<symbol>[^,]+)` |

`ostler.markdown` is the one markdown parser. `farrier` keeps its own frontmatter module
because it never needs the section tree and `farrier → ostler` is a dependency edge we do
not draw — but it is built on the same libraries, not on a regex.

## Asking a document a question

```python
from ostler import markdown

doc = markdown.split(path.read_text(encoding="utf-8"))

doc.frontmatter["tags"]                  # already a list; YAML decided that, not us
section = doc.find_section("Acceptance")  # by title, at any depth
section.is_empty                          # heading-only sub-sections do not count as prose
section.body                              # the text *without* its own heading line

doc.find_bullet("status").value           # `- **Status**: done` → "done"
bullet.bracketed                          # `- [OKF-12] a thing` → ("OKF-12", "a thing")

for table in doc.walk_tables():
    for row in table.records:             # rows keyed by header
        row["Placeholder"]
    table.column("Stands for")

for label, href, line in markdown.iter_links(text):   # never one inside a code span or fence
    ...
```

Three properties come free and are the reason to use it: a heading inside a fenced code
block is not a heading, a `- item` inside one is not a bullet, and `- **key**: v` is the
same bullet as `- key: v`. No line regex can tell any of those apart.

Line numbers on `Section` / `Table` are 0-indexed and **body-relative**; `doc.body_offset`
converts to a file line. Round-tripping is byte-exact: `split` never reflows a file, so
`replace_body` / `render` are safe on a document a human wrote.

## Where regex is still right

The rule is about **grammars**, not about `re`. These are not parsing and stay as they are:

- **Text with no grammar.** An agent CLI's log line, a cap-reset message (`resets 11:30am`),
  a token counter, a test runner's output. There is no parser because there is no format —
  only a sentence someone chose to print.
- **Constraining a string rather than reading one.** Identifier validators (`^[A-Z]{4}-\d+$`),
  slugifiers (`re.sub(r"[^a-z0-9]+", "-", name)`). Nothing is being extracted from a
  document.
- **A line protocol of our own** — the `STATUS:` / `SCOPE:` gate header. We define it, it has
  two lines and no nesting, and a parser would be ceremony. But there must be exactly **one**
  implementation of it: `workhorse.gates`. That header used to be retyped on both sides of
  the same file (a workflow writes it, groom's UI reads and rewrites it), where a divergence
  is a gate that never opens.

## No hand-rolled parsers

Where a parser exists, a small hand-written scanner is not a lighter alternative to it — it
is the same bug in fewer lines. The fifteen-line frontmatter fence scanner is exactly how
the CRLF and trailing-space losses above happened, and `split_front_matter`'s own
`line.split(":", 1)` loop carried a docstring admitting it silently mis-read both spellings
of a YAML list. Reach for the library, including for something as small as a fence.

## The check, and how to declare an exemption

`make check-parsers` (in `make test`) walks every `.py` — tracked or not yet added — and
flags regex pattern literals whose text encodes a known format's grammar, naming the parser
to use instead. It is a pattern-shape denylist, not semantic analysis: it catches the shapes
known to have gone wrong, and cannot prove an arbitrary regex is innocent.

When a format genuinely has no parser available — Make, a `.rb`/`.java`/`.rs` source no
grammar in `ostler.syntax` reads — declare the site in `ALLOWED` in
`scripts/check_parsers.py`, keyed by `(path, shape)`, with a reason that says *why this one
is right*:

```python
    ("ostler/ostler/qa/context.py", "lang-decl"): (
        "the last-resort line scan for a language *no* grammar reads — `.rb`, `.java`, `.rs`. "
        "Every language `ostler.syntax` knows is parsed (`inventory.extents`) and never reaches "
        "this; attributing a changed hunk to the nearest declaration-shaped line above it is "
        "worse than a parse and better than reporting the diff touched nothing"
    ),
```

The reason is printed on every failure, so the next person sees the standard before adding
to it. An entry that stops matching anything **fails the check** — a reason cannot outlive
the code it excuses, and the list stays a list of real exceptions rather than a graveyard.

For the ostler CLI and the doc graph these parsers serve, load [[ostler]]; for node
functions that read a book, [[workhorse-scripting]].
