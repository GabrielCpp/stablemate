# Bullet grammar

The mechanical half of the OKF UI profile: what a `- key: value` bullet *is* to the machinery
that reads it. Every recognized key carries a set of flags, and those flags — not prose about
them — decide whether the key mints a QA obligation, resolves as a link, grounds against source,
or is silently inert. Companion to [`../SKILL.md`](../SKILL.md); the per-type key lists are in
[node-types/](node-types/), and this file is the vocabulary they all draw on.

Source of truth: `ostler/ostler/registry.py`. When this file and the registry disagree, the
registry is right and this file is a bug.

## The flags

Each recognized bullet is a `BulletKey` (`registry.py:230-258`). A key can carry several flags.

| Flag | What it means to a consumer |
| --- | --- |
| `required` | The type must carry the bullet, even to say `none`. Absent → `missing-required-bullet` (error, fixable by `scaffold`). |
| `nested` | The value is a nested-bullet list, one child per effect (`does:`). Each child is counted separately. |
| `link` | The value is a reference `ostler` resolves — a doc link or a code ref. Unresolvable → `dangling-link` / `unresolved-relation` / `missing-anchor`. |
| `check` | The value is a named check from `ostler.checks` — an **observation**. Parsed and grounded against the vocabulary. |
| `arrange` | The value names a fixture this repo declares — the **arrangement** that reaches the state the claim above it is about. |
| `normative` | The value is a **claim**. QA mints one obligation per value, which one scenario then has to prove. |
| `alias` | A second accepted spelling of the key declared just above it (`statuses` for `status`). Ordered like the primary; never stubbed by `scaffold`. |
| `owns` | The value names a file (or `path::symbol`) the node is documented *against*, so a change to that file reaches the node. This is what `ostler qa context` reads when it maps a diff onto the book. |

`owns` and `link` are distinct: `openapi: none; …` is a citation the reader does not resolve and
is still an ownership claim. `owns` and grounding are distinct too — owning a file is not being
grounded in a symbol, so `doctor` asks nothing of an owning key it does not also ground.

## The four key families

Every load-bearing key falls into one of four families, and confusing them is the single most
common authoring defect.

- **Claims** (`normative=True`) — what the node asserts. One value, one obligation, one scenario.
- **Observations** (`check=True`) — what proving a claim looks like. `verify:` on the four
  normative section types.
- **Arrangements** (`arrange=True`) — how to reach the state a claim is about. `fixture:`.
- **Grounding and ownership** (`link` / `owns`) — where it lives. `code:`, `openapi:`, `file:`,
  `config:`, `tests:`.

`code:` and `tests:` are not interchangeable with `verify:`, and the difference is a category
error rather than a typo. A test id says which code *ran*; `verify:` says what was *seen*. An
assertion filed under a test id can be arbitrarily weaker than the claim above it, which is why
`verify:` stopped being a code reference (`CODE_GROUNDING_KEYS` is now `{"code"}` alone) and
became the check vocabulary. See [check-vocabulary.md](check-vocabulary.md).

## Keys that are normative on every type

`SHARED_NORMATIVE_KEYS` (`registry.py:293`) mint obligations wherever they appear, whatever the
node type declares:

```
consistency, consistency rule, consistency group, persistence,
emits, consumes, concurrency, idempotency
```

`normative_keys(type)` is these plus the type's own `normative=True` keys. Note the consequence:
`emits:`/`consumes:` are declared *without* `normative` on `endpoint` and `invocation`, and are
normative there anyway because the shared set overrides. `declared_keys(type)` — what the type
recognizes at all — is its own keys plus this shared set; anything outside it that is
load-bearing on some other type is `unknown-bullet`.

## Ownership: what `qa context` reads

`owning_keys(type)` (`registry.py:311`) decides which nodes a changed file reaches:

- `code:` owns on **every** type, whether or not the profile lists the key;
- plus the type's own `owns=True` keys — `openapi:` on `server`/`endpoint`, `file:` on `format`,
  `config:` on `environment`/`format`.

`tests:` is deliberately **not** owning (`registry.py:318-320`): a test file is verification
evidence, not the node's subject. Neither is `binary:`, which names a program rather than a path.
`config:` additionally punches its file through `qa context`'s non-production filter, so a stack
config that would otherwise be dropped from the change surface still reaches its node.

## One provable claim per normative bullet

Each value of a normative key becomes **one** QA obligation, proved by **one** scenario. A bullet
that holds three requirements ships with the scenario proving whichever clause the planner read
and the other two claimed-as-covered — which is how a story passes QA over behaviour nobody
tested.

- `doctor` **errors** past 700 characters of prose in one normative bullet
  (`MAX_NORMATIVE_PROSE`, `doctor.py:771`) → `overlong-normative-bullet`.
- `doctor` **warns** when one bullet states more than one observation →
  `compound-normative-bullet`. A warn rather than an error because splitting is authoring
  judgment: only the author knows which clauses are separate requirements.

Split on the real seams — the success effect, each error case, what is persisted, what is
emitted — by **repeating the key**, not by rewording:

```markdown
- does: writes the revision under the caller's name
- does: bumps the document's `updatedAt`
- errors: 409 when the supplied version token is stale
```

## Document order is the binding

A `verify:` or `fixture:` binds to a claim by **position**, not by name
(`attributed_checks` / `attributed_fixtures`, `registry.py:352-420`):

- a check binds to the **nearest authored normative bullet above it**;
- a check written **above every** normative bullet belongs to the node's own *contract*
  obligation;
- a check written under a `nested` parent was written against the whole of it, so it fans out to
  **every child**;
- a `fixture:` above every claim is ambient — state reached once is the state every later claim
  is read in — so it fans out to **all** the node's obligations. (This is the one asymmetry: an
  observation is specific by nature, an arrangement is ambient by nature.)

Canonical bullet order is the type's `bullet_keys` order and is applied by `ostler fmt`, so a
stub written in the wrong place is one the formatter moves the first time the file is touched.
`ostler scaffold` already emits check stubs under the last claim for this reason.

## Repeated controls: `one-per:` / `unique-by:` / `variants:`

A control the app renders once per member of a collection is **one node** carrying the repeat
keys (declared on `component` and `interaction`), not N copies:

```markdown
- one-per: `stage` — one row per stage in the project's stage list
- name: `{stage.name} stage row`
- unique-by: `stage.id` — primary key of the stages table
- variants: `stage.kind = draft | active` — the union StageKind
```

The grammar is strict so fixtures and tests can be compiled from it:

- **The machine value is the first backticked span**; the tail after ` — ` is prose and is
  never parsed. `one-per:` holds one identifier — the iteration variable. `unique-by:` holds
  one dot-path rooted at that variable. `variants:` holds `path = token | token | …` entirely
  inside the backticks, tokens copied from a closed enumeration in the source.
- With `one-per:` in force, `name:` is a **template**. A `{…}` hole that is a plain dot-path
  rooted at an in-scope iteration variable is *bindable*; anything else is *opaque* — kept
  verbatim, matched as a wildcard, **never evaluated**. Classification cannot fail; the only
  hard error is an unbalanced brace (`malformed-template`).
- Scope flows through markdown containment and `parent:` only. An `on:` edge is a reference,
  not membership — an interaction `on:` a repeated component does not inherit its family.
- The data-only segments compiled from the template (never code) travel with every obligation
  the node mints, and the QA plan validator demands a sampled instance per covered repeat
  obligation — see the qa-plan-authoring reference in the ostler/cli skill.

## The `untyped` node

A `## Heading` that names no type still promotes its `### id` children to nodes
(`registry.py:739`) — their links are captured, they nest, they are queryable — rather than
inventing a garbage type from prose. An `untyped` node declares no bullet keys, so it mints
nothing and is checked for nothing; a claim written in one is `unminted-claim`'s to find. It is
not a type an author picks: if the content has a type, give the heading its type.

## Mechanical and judgment

Everything above is the **mechanical** surface: enforced, orderable, gradeable. It is
deliberately not the whole of what a book has to carry.

Bullet keys say *what a node is*. They cannot say *whether a reader should be using it* — and in
a codebase with two ways to do the same thing, that second question is the one that bites. Two
notification services, one legacy and one current, each correct in a different context, will both
produce perfectly conformant nodes: correct `code:` grounding, well-split `does:` bullets,
discriminating `verify:` checks. `doctor` passes both, and the graph is structurally silent about
the only thing the reader needed to know.

**Prose is judgment, and the format deliberately does not check it** — which is precisely why
where it goes has to be written down. It goes in a `concept` node, the one type in the registry
whose own keys mint nothing, linked from each competing node with `detail:`. See
[node-types/concept.md](node-types/concept.md).

The concept carries three **advisory** keys for exactly this — a fifth family, beside the four
above, that drives no obligation and never will:

- `rule:` — the selection rule, stated as prose. Plain, not load-bearing: on any other type the
  key stays the author's own word, and nothing mints from it anywhere, because a selection rule
  is not live-provable and an obligation minted from one would demand evidence no scenario can
  produce.
- `prefers:` / `deprecates:` — the supersession pair, pointing at the winning and superseded
  nodes. Both are relations (`registry.RELATION_KEYS`), so a dangling side is
  `unresolved-relation` rather than silence, and both stay out of the load-bearing set.

Supersession lives there and **only** there. Four other keys look like it without being it:

- `exclusive-with:` is a **DOM co-render assertion**, consumed only by `locators.py` and
  `vet/placement.py` to suppress locator collisions between controls that never appear together;
- `extends:` is inheritance;
- `legacySurface` (`registry.py:40`) exists only on epic **seeds**, in the planning layer, and
  never reaches the book;
- `doctor.py:950`'s `legacy` is an unrelated reachability-root waiver.

## `unspecified` — deliberately out of contract

The one **advisory** key writable on every type (`registry.SHARED_ADVISORY_KEYS`). An
`unspecified:` bullet records a behaviour the book looked at and *decided* to leave out of
contract — an encoding order, a duplicate policy, a tie-break nobody promised. It mints
nothing: a statement of what is not promised has no observation to prove, and QA reads it as
resolved-by-design rather than as a gap to invent coverage for.

That reading is trust, and the citation is what earns it. Every `unspecified:` value must
carry at least one markdown link resolving to the record that settled the decision — a
decision doc, an acceptance criterion, a stated convention:

```markdown
- unspecified: the export's field encoding order — settled in
  [0007](../../../decisions/0007-export-encoding.md)
```

A bullet with no live citation is `ungrounded-unspecified`, an **error**: uncited, nothing
distinguishes it from a gap someone decorated, and the remedy is mechanical — cite what
settled it, or delete the bullet. The link names a record, not a node, so it is grounded by
that check rather than by the relation resolver.
