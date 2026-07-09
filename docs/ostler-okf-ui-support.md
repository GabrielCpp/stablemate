# Ostler changes to support the OKF UI profile

> **Status:** draft for review. This document specifies the **ostler** changes
> needed to recognize, validate, format, and scaffold the node types introduced by
> [the OKF UI profile](okf-ui-profile.md). The UI profile defines the *format*; this
> spec defines the *tooling* that makes it navigable and enforceable. Once approved
> it folds into `ostler/SPEC.md`. File/line references point at the code as it stands
> today.

## 1. Scope & design stance

The UI profile adds eleven node types (`screen` / `component` / `interaction` /
`cli` / `command` / `server` / `endpoint` / `invocation` / `flow` / `concept` /
`format`) across three surfaces, organized per service and per context under
`docs/features/<service>/` (see the profile, §3–§4). Ostler must:

1. **recognize** the types as first-class (not conformance-only),
2. **model** section-level nodes (`### id` under `## Components` / `## Interactions`
   / …) as addressable graph nodes,
3. **validate** the graph as a **mandatory linter** — every finding is an error the
   agent is expected to fix, each carrying a file+line location,
4. **format** docs into a canonical shape (`ostler fmt`), and
5. **scaffold** new nodes into the correct place in the hierarchy (`ostler scaffold`).

**Stance.** Ostler stays the *index-and-integrity layer*: it loads the markdown into
a typed graph, answers navigation queries, and enforces referential integrity. It is
not an authoring tool and not a code generator. The three new capabilities —
**mandatory linting + formatter + scaffolding** — are deliberately coupled: they
close a loop in which every mandatory error has a deterministic remedy (format it, or
scaffold the missing node), so a strict `doctor` *converges* instead of nagging.

## 2. Current state (grounded)

With a UI doc already sitting under `docs/features/groom/…`:

| Capability | Today | Where |
|---|---|---|
| Loads as a graph node | ✅ as a flat `FeatureRecord` | `model.py:324` (`_load_features`) |
| `doctor` enforces non-empty `type` | ✅ | `doctor.py:212` (`okf-missing-type`) |
| `ostler search <q>` finds it | ✅ (feature body text) | `query.py:85` |
| `relink` / `rename` rewrite path links | ✅ | `edit.py:7-8` |
| `--json`, exit 1 on error | ✅ | `cli.py:277-279` |
| `ostler list --type component` | ❌ returns nothing | `query.py:37` (hardcoded types; unknown → `crud_generic`) |
| `trace` walks UI links (`on`/`parent`/`extends`/`steps`) | ❌ | `trace.py` (seed/story/gap/surface only) |
| Dangling path link is flagged | ❌ links extracted, never resolved | `markdown.py:26,43` extract; no check in `doctor.py` |
| Section nodes (`### id`) modeled | ❌ only `epic.md` `## Seeds`/`## Stories` | `model.py:183-223` |
| Findings carry file+line | ❌ only `epic` + `ref` token | `doctor.py:16` (`Finding`) |
| A `type: screen` doc keeps `doctor` green | ⚠️ **no** — trips `feature.schema.json` | see §10 |

So the profile's §5/§6 present-tense claims (`list --type component`, `trace` walks
the links, "a dangling link is at most a warning") describe the target, not today's
code. This spec closes that gap — and, per the reviewer's direction, upgrades "at
most a warning" to **mandatory error**.

## 3. The registry is the single source of truth

`registry.py` already declares that role — the loader, validator, retrieval, and
mutation all consult it (`registry.py:3-6`). Every change below hangs off **one
per-type spec** added there, so the formatter (order), linter (rules), and scaffolder
(skeleton) never drift.

### 3.1 Built-in UI types (not template kinds)

Template kinds (`dynamic_registry.py:47`) are reduced to *conformance-only*
(`as_entity_types`, `dynamic_registry.py:147`) — no schema, no structure. Since the UI
types must be first-class and mandatory, declare them as **built-in** `EntityType`s in
`registry.py`, reusing the template *engine* (path resolution, body template) but with
built-in *specs*.

The eleven types split by how they live (profile §4):

- **File-level** (`screen` / `cli` / `server` / `concept` / `format` / `flow`): each is
  a `.md` file; identity = path.
- **Section-level** (`component` / `interaction` / `endpoint` / `command` /
  `invocation`): each is a `### id` under a typed `## Heading` inside a surface file;
  identity = `path#anchor`.

### 3.2 Per-type spec (generalize `SEED_META_KEYS` / `STORY_META_KEYS`)

The registry **already** models "recognized metadata bullet keys inside a `### id`
block" — `SEED_META_KEYS` (`registry.py:28`) and `STORY_META_KEYS` (`registry.py:35`)
do exactly this for seeds and stories, and `SEEDS_HEADING` / `STORIES_HEADING`
(`registry.py:23-24`) map a `## Heading` to its child node type. Generalize both into a
per-UI-type spec:

```python
@dataclass(frozen=True)
class UINodeType:
    name: str                       # "interaction"
    kind: str                       # "file" | "section"
    heading: str = ""               # section types: the parent "## Heading" (e.g. "Interactions")
    context: str = ""               # file types: context folder — "gui/screens", "http", ...
    required_sections: tuple[str, ...] = ()   # file types: headings that must be present
    bullet_keys: tuple[BulletKey, ...] = ()   # recognized keys, in canonical order
    body_template: str = ""         # skeleton emitted by `ostler scaffold`

@dataclass(frozen=True)
class BulletKey:
    key: str                        # "on", "trigger", "does", "code", "verify"
    required: bool = False
    nested: bool = False            # "does:" — a nested-bullet list
    link: bool = False              # value is a path link ostler must resolve
```

Example (`interaction`, profile §3):

```python
UINodeType(
    name="interaction", kind="section", heading="Interactions",
    bullet_keys=(
        BulletKey("on", required=True, link=True),
        BulletKey("trigger", required=True),
        BulletKey("when"),
        BulletKey("does", required=True, nested=True),
        BulletKey("code", link=True),
        BulletKey("verify", link=True),
    ),
)
```

This one definition drives all three tools (§7–§9). The heading→type map replaces the
profile's "type implied by `## <Section>` heading" prose with an executable table.

## 4. Loader: model section-level nodes

`model.py` parses sections only for `epic.md` (`_parse_seeds` / `_parse_stories`,
`model.py:183-223`). Generalize that into a surface-doc parser driven by the §3 spec:

- for each file-level surface doc, walk its typed `## Heading`s
  (`MarkdownDoc.sections`, `markdown.py:112`);
- under each, treat every `### id` child as a **section node** of the heading's type;
- parse its metadata bullets with the existing `_meta_from_bullets` (`model.py:144`),
  and read the nested `does:` effects straight off `Bullet.children` — the parser
  already builds that tree (`markdown.py:167-182`), which is the capability the profile
  relies on;
- assign identity `path#anchor` (kebab-cased heading), and keep each node's source
  line span (`Bullet.line_start` / `Section.line_start`) for located findings (§6) and
  byte-precise edits (§8–§9).

Add `screen` / `server` / `flow` / etc. records to `Graph` (or a single `ui_nodes`
list keyed by type + id) alongside `features`.

## 5. Fix conformance dispatch (the `feature.schema.json` gotcha)

`_check_conformance` (`doctor.py:192`) dispatches **by glob**: it walks each registered
type's `location` and validates every match against that type's schema. The `feature`
type globs `features/**/*.md` (`registry.py:82-86`) with `feature.schema.json`, whose
`type` is `{ "const": "feature" }`. So a `type: screen` file under `features/` is
validated as a feature and emits a warn-level `schema` finding — `doctor` is **not**
green today.

Fix: dispatch conformance **by the file's declared `base_type`** (`registry.py:105`)
when it is a registered type, validating against *that* type's spec; fall back to the
glob only for discovery / type-less files. A `type: screen` doc is then validated as a
`screen`, never double-counted as a `feature`.

## 6. Link resolution & located findings

Two additions unlock every downstream check.

**6.1 Resolve links.** `References.links` are extracted (`markdown.py:26,43`) but never
resolved. Add a resolver: for each `[text](path)` / `[text](path#anchor)` in a surface
doc (or a node's `link:` bullet), resolve `path` relative to the file, and resolve
`#anchor` against the target's heading anchors. This is what makes `parent:` /
`extends:` / `on:` / `steps:` load-bearing edges rather than decoration.

**6.2 Locate findings.** `Finding` (`doctor.py:16`) carries only `epic` + `ref`. Add
`path` + `line` (and optional `suggestion` / `fixable`) so each finding is a targeted
edit, not a re-derivation:

```python
@dataclass
class Finding:
    severity: str            # "error" | "warn"
    code: str                # rule id
    message: str
    path: str = ""           # repo-relative file          ← new
    line: int = 0            # 1-based, file-absolute       ← new
    ref: str = ""            # offending token (existing)
    suggestion: str = ""     # expected form / nearest match ← new
    fixable: bool = False    # `ostler fmt`/relink can apply it ← new
```

Line numbers come from the node's body-relative span plus the frontmatter line count.
`Report.as_dict` serializes `vars(f)` (`doctor.py:47`), so JSON and the agent loop pick
these up for free.

## 7. `doctor` as a mandatory linter

Per the reviewer's direction, UI-profile findings are **mandatory errors**, not
warnings. `doctor` is already a linter in shape — stable `code`s, `severity`, `--json`,
error-first printing with ✗/⚠, and exit 1 on any error (`cli.py:275-292`). The new
rules, all `error`:

| code | fires when | fixable by |
|---|---|---|
| `okf-missing-type` | no non-empty `type` (existing) | agent |
| `unknown-type` | `type` not in the registry | agent |
| `missing-required-section` | a type's `required_sections` heading absent | `ostler scaffold` |
| `missing-required-bullet` | a required `bullet_key` absent | `ostler scaffold` / `fmt` |
| `dangling-link` | link target **file** does not exist | `relink` / `scaffold` |
| `missing-anchor` | file exists, `#anchor` heading does not | `relink` / `scaffold` |
| `unresolved-relation` | `on:` / `parent:` / `extends:` / `steps:` target missing | `scaffold` |
| `bad-heading-type` | a `### id` under an unrecognized `## Heading` | `fmt` / agent |

**7.1 Convergence contract.** "Mandatory" is safe only because §8 (formatter) and §9
(scaffolding) give every error a deterministic remedy. A hard error whose only fix is
"author a node that doesn't exist yet" would wedge the agent loop; with `ostler
scaffold` that fix is one command. **Do not flip findings to mandatory until fmt +
scaffold ship** (see §11 build order).

**7.2 Code-grounding runs in a later phase.** One carve-out: `code:` / `verify:`
targets (does the `path::symbol` / test id exist in the repo?) couple doc authoring to
code existing, which breaks doc-first authoring. Keep these mandatory but at a **later
gate** that runs when code exists — mirroring `_check_surfaces` (`doctor.py:258`), which
grounds surfaces against the feature inventory yet leaves "does the route actually
render" to the coder's QA gate. Doc-internal integrity (§6) is enforced at author time;
code-grounding at the QA phase.

## 8. `ostler fmt` — the formatter

A canonicalizing formatter, paired with the linter the way `ruff format` pairs with
`ruff check`: it mechanically fixes *shape* so the linter only hard-errors on *semantic*
gaps.

Canonical operations, all driven by the §3 spec:

- **frontmatter** — stable key order (`type, slug, title, …`), quoting, trailing newline
- **metadata bullets** — canonical order per `bullet_keys`; `- key: value` spacing;
  normalize a one-line `does:` into the nested-bullet form
- **sections** — canonical `## Heading` order and casing; `### id` anchors kebab-cased
- **links** — strip any `[[wikilink]]` → standard path link; canonicalize relative paths

Notes:

- `markdown.py` is deliberately **byte-exact / no-reflow** (`markdown.py:3-10`). `ostler
  fmt` is the *intentional exception* — a mutating command in the `edit.py` family
  (alongside `relink` / `rename`), never part of the read path.
- Ship it **idempotent** with a **`--check`** mode (no writes, exit 1 if unformatted) —
  the repo already uses that idiom (`farrier install --check`) so CI and the agent loop
  can assert "already canonical."

## 9. `ostler scaffold` — hierarchy-respecting node creation

Most of the engine exists. `TemplateKind` (`dynamic_registry.py:47`) already resolves an
instance path from a `path_template` with `{name}` / `{parent}` placeholders, nests via
`parent`, carries `required` frontmatter and a `template` body, and `crud_generic`
instantiates it. That *is* "create a file in the right place in the hierarchy."

Two additions:

- **File-level types** map onto the template engine directly: `ostler scaffold screen
  changes-view --service groom` resolves to
  `docs/features/groom/gui/screens/changes-view.md` (context from the type's `context`
  field, §3) and emits the frontmatter + `required_sections` skeleton.
- **Section-level types are the genuine gap.** `TemplateKind` is file-oriented;
  `component` / `interaction` / `endpoint` / `command` / `invocation` are `### id`
  *sections inside* a file. Scaffolding one means **inserting** a typed section under its
  `## Heading` (creating the heading if absent), with the ordered `bullet_keys` stubs:
  `ostler scaffold interaction click-file --in gui/screens/changes-view.md`. The
  insertion is byte-precise via the Section line spans; it just needs wiring to the §3
  spec.

Scaffolding is what lets the agent **respect the hierarchy by construction** rather than
inferring the §4 layout — and it is the remedy for the `missing-*` / `unresolved-*`
errors in §7.

## 10. Navigation: `list` / `search` / `trace`

- **`list --type <uitype>`** — add a branch to `list_entities` (`query.py:37`) filtering
  file-level nodes by `data.get("type")` (already on `FeatureRecord`) and enumerating
  section nodes from §4. Makes `ostler list --type screen` / `--type interaction` real.
- **`search`** — already includes feature body text (`query.py:85-103`); extend the
  type list to the UI types so hits report `path#anchor` for section nodes.
- **`trace`** — add a UI branch to `trace.py` that, using the §6 resolved edges, walks a
  node's outbound links (`on` / `parent` / `extends` / `presents` / `steps`) and inbound
  referrers, both directions. Optionally hop the cross-graph edges (`interaction.does.net:`
  → `endpoint` / `invocation`; `endpoint.openapi:` → `format`) once §4 lands.

## 11. Build order

Sequencing matters because §7 depends on §8–§9 for convergence:

1. **Registry spec (§3, §5)** — built-in UI types, per-type `UINodeType` spec, and the
   conformance-dispatch fix. Nothing enforces yet; `doctor` goes green on UI docs.
2. **Loader (§4)** + **`list`/`search` (§10)** — section nodes become addressable.
3. **`ostler fmt` (§8)** — canonical shape, `--check`, idempotent.
4. **`ostler scaffold` (§9)** — file types via the template engine; section-node insertion.
5. **Link resolution + located findings (§6)** and **`trace` (§10)**.
6. **Flip `doctor` to mandatory (§7)** — *last*, once fmt + scaffold give every error a
   remedy. Add the code-grounding gate (§7.2) at the QA phase.

## 12. Open questions

1. **Section-node identity in `list`/`trace` output** — `path#anchor` strings, or a
   structured `{file, anchor, type}`? (Affects the agent-fix loop's ergonomics.)
2. **`ostler fmt` scope** — frontmatter + bullets + headings only, or also prose
   wrapping? (Prose reflow is higher-risk; recommend leaving prose alone for v1.)
3. **Scaffold surface indexes** — should `ostler scaffold command` also insert the
   brief `### id` + `detail:` stub into the surface index file (profile §4 hub+detail),
   or only create the detail file?
4. **Cross-service concept links** — the resolver must accept `../../<service>/concepts/…`
   (profile §4); confirm no sandbox on resolving outside the current service subtree.
5. **Code-grounding gate placement** — a distinct `ostler ground` verb, a `doctor
   --ground` flag, or folded into the coder QA workflow?
