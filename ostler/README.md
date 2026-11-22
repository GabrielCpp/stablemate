# ostler

> Tend your documentation graph.

`ostler` is the single system-of-record for a repository's `docs/` planning graph. It **defines,
validates, searches and mutates** your planning docs (backlog items, milestones, epics, stories,
seeds and specs) as plain markdown documents with YAML frontmatter.

Everything is markdown. An epic's seeds and its story dependency-DAG live inside its `epic.md`; there
is **no** `seed.json` or `dependencies.json`, and no epics queue. Ostler owns id
allocation and is the one tool that reads and writes the graph, so structure stays consistent while
humans (or agents) author the prose.

It is a standalone, repo-agnostic CLI that operates relative to the **current working directory**:
roots default to `<cwd>/docs/epics` and the organization name to the repo
folder name. Specs default to `<artifacts dir>/specs` outside git. Point it at any repo with `-C/--chdir`.

## Install

```bash
pipx install ostler          # recommended: isolated CLI on your PATH
# or
pip install ostler
```

For development against a local checkout:

```bash
pipx install --editable /path/to/stablemate/ostler --force
```

The package installs one console entry point, `ostler`.

## Quickstart

Ostler creates the *structure and ids*; you author the *content* into the skeletons it scaffolds.

```bash
# 1. See if the graph is healthy
ostler doctor

# 2. Capture intake and its release boundary (both allocate immutable ids)
ostler create backlog-item "Ship checkout parity" --section Scope --json
ostler create milestone checkout-mvp --title "Checkout MVP" \
  --source-items <full-backlog-id> --json

# 3. Scaffold an epic (allocates an id and writes <artifacts dir>/epics/<epic-id>/epic.md;
#    `--json` reports the id, which is also the folder's name)
ostler create epic checkout-flow --title "Checkout Flow at Parity"

# 4. Record a seed (a unit of intended work) in that epic's ## Seeds
ostler seed add checkout-flow address-step --status researched \
  --surface checkout/address --summary "Collect & validate the shipping address"

# 5. Cut a story that covers the seed (adds it to the epic's ## Stories, scaffolds story.md)
ostler create story checkout-flow 01-address-step \
  --title "Address step" --covers address-step

# 6. Ask what to work on next, then list the epic's stories as JSON
ostler next-story checkout-flow
ostler list --type story --epic checkout-flow --json
```

Then open the scaffolded `epic.md` / `story.md` and write the narrative, acceptance criteria, and
prose — ostler keeps the seeds, edges and ids coherent around it.

A story's `id` is an opaque string. `create story` mints a ULID, and nothing else assumes the id's
shape. A tracker key such as `CASE-574` may be written as the `id` by hand. The `id` is the immutable
identity used by commit trailers and spec directories. The slug names the story's folder and its
heading in `epic.md`. Every command takes the id. A slug passed to a command is refused, and the
error spells out the id to use. IDs and slugs must be unique across stories; `doctor` rejects
ambiguity rather than letting graph order choose one.

## The hierarchy

A repository's planning documents live under `docs/` as directories of markdown files. A document
is one `.md` file with a YAML **frontmatter** block (whose only hard requirement is a non-empty
`type`) and a markdown **body** using conventional headings.

**Identity is the path.** A document's id is its path under its document root, without `.md`.
The reserved filenames `index.md` (an ordered listing of a root) and `log.md` (history) are not
documents the graph reads.

### Entity types

| `type` | Location (repo-relative) | Identity | Required frontmatter |
|---|---|---|---|
| `milestone` | `docs/milestones/<NNNN-slug>/milestone.md` | folder name `<NNNN-slug>`, or its bare `<slug>`; optional `id` defaults to it | `type`, `title`, `status` |
| `epic` | `<artifacts dir>/epics/<epic-id>/epic.md` | the minted `id`, which names the folder; the `slug` names it in commands and branches | `type`, `id`, `slug`, `title` |
| `story` | `<artifacts dir>/epics/<epic-id>/stories/<story-id>/story.md` | opaque `id` (a ULID when ostler mints it), which names the folder; the `slug` names the `epic.md` heading | `type`, `slug`, `status` |
| `spec.<stem>` (`spec.plan`, `spec.review`, `spec.qa`, `spec.executive`, `spec.vet`, …) | `<artifacts dir>/specs/<story-id>/*.md` (`ostler path spec <story-id>`) | path | `type` |

**Epic and story folders are named by their ids.** `create epic checkout-flow` mints an id and
writes `<artifacts dir>/epics/<epic-id>/epic.md` with `slug: checkout-flow` in its frontmatter;
`create story` writes `<epic-id>/stories/<story-id>/story.md`. An id never changes, so a path built
from it never goes stale. The slug still names the epic in every command: `--epic checkout-flow`,
`create story checkout-flow …`. The order of the work lives in the milestones alone: a milestone's
`dependsOn` milestones come first, then its `epics:` list in order (`Ostler.milestone_epics()`).
Use `ostler path epic <slug>` when you need the directory itself.

A shelf still holding `NNNN-slug` epic folders refuses every command until `ostler layout apply`
renames each epic and story folder to its id and records each epic's slug.
Doctor reports an epic or story folder not named by its id (`epic-folder-not-id`,
`story-folder-not-id`).

`spec.*` documents are process artifacts: typed and conformance-checked, but ostler does not own their
internal schema. The subtype is the file's stem (`executive.md` → `spec.executive`); mint them with
`ostler create spec <story-id> <doc>`, which is idempotent and also retro-stamps free-form docs.

### Planning intake identity

Use `create backlog-item` (or `backlog add`) for new work. It allocates a full id and files one
record on the Register, in the artifacts repo. An old `- [id] text` list is turned into records once
by `backlog adopt --repo R <file>`, which deletes the list. Ostler reads no bullet list after that.

A milestone's generated `id` is independent of its readable filename and title. Its `sourceItems`
contains the full ids of the backlog intake it owns. Use `milestone set-source-items` to update that
set when an active milestone absorbs more intake. `doctor` rejects a backlog id owned by multiple
milestones. Its `epics` are epic ids in coding order, written with `milestone epics`, which also
writes the `## Epics` section a reader of the milestone sees. Never persist a short handle: handles are display/input conveniences and may lengthen
after a collision; Ostler resolves command inputs and writes full ids.

### `epic.md` — single source of truth for an epic

An epic's `epic.md` carries the narrative **and** its seeds and story dependency-DAG. Ostler parses two
canonical sections back out of the markdown by exact heading:

```markdown
---
type: epic
id: ACME-01JBXR7K9QZ4M2T8VNF3HD6PWC
title: Account Credits Billing Body
status: in-progress        # optional: planned | in-progress | done
followups: true            # optional: a backlog of filed follow-ups that no milestone owns
---

Free narrative prose (any headings: ## Goal, ## Method, ## Acceptance, …).

## Seeds

### billing-landing-body
- status: researched       # backlog | researched | covered | resolved | dropped | deferred
- surface: account-billing/billing-body
- backing: GET /billing/customer → CustomerDetails

The first paragraph after the metadata bullets is the seed summary; further prose is free markdown.

## Stories

### 01-billing-body
- title: Account Credits Billing Body
- id: ACME-01JBXR7M4E0S9YCG5NAKQ2TZVJ
- covers: billing-landing-body, subscription-change-plan-link
- phase: 1
- effort: 8-10 hours
```

- `## Seeds` → `### <seed-id>` per seed (omit the whole section for a seedless epic).
- `## Stories` → `### <slug>` per story, carrying the **coverage edge** `covers:` (seed ids). The
  detailed spec lives in the story's own `story.md`, and so does its place in the DAG: a
  `## Dependencies` section stating one `- Blocked by: <sibling-slug>` per blocker, or the bare
  `(none)`. That way what blocks a story is readable in the story.

See [SPEC.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/SPEC.md) for the
authoritative, formal definition of every field, status enum, and conformance rule.

## Command interface

All read commands accept `--json`. Mutating commands allocate ids as needed and write canonical
markdown in place. `ostler --version` prints the version; `-C/--chdir DIR` runs any command as if
from `DIR`; `--handles` / `--full-ids` choose how ids are printed (see
[Short handles](#short-handles) — human output abbreviates, `--json` does not, and a handle is
accepted as input either way).

| Verbs | What they do |
|---|---|
| `doctor` | check conformance and referential integrity |
| `list` `search` `index` `query` `next-epic` `next-story` `path` | read the graph — what exists, what covers what, what to work on next |
| `create` `update` `delete` `seed` `set-status` `unblock` `backlog` `milestone` | mutate it — scaffold identified intake/plans/specs, revise story graph metadata, record a seed, list a milestone's epics |
| `edit` | repair a rename across the whole graph |
| `template` `new` `find` `set` `remove` | declare a repo's own document kinds and operate on their instances |
| `vet` | check a rendered screenshot against the regions a story declares |
| `qa` `artifact` | the verification control plane — see below |
| `env` | bring up a local copy of the stack the books declare, and tear it down — see below |
| `book` | run a service book, the executable model of one HTTP or gRPC service, against the live service — see below |

`edit` is **dry-run unless `--write`**, so a rename across a whole graph is reviewable before it
happens; `create … --json` returns
`{"ok": true, "id": "<allocated-id>", "name": "<name-on-disk>", "message": "…"}` — `name` is what
`create epic` numbered the directory, which is why it is reported rather than assumed.

Every verb, with its real flags and what each one operates on, is in
[docs/CLI.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/CLI.md).

### Verification control plane

`ostler qa` owns the bookkeeping of a QA run. `qa validate` and `qa run` execute a hand-written
`qa_plan.py` that declares command, Playwright and Maestro targets and maps every scenario to the
ids it covers. Validation rejects unknown actions and locators, disposable pre-run inputs, literal
secrets, and coverage without a machine assertion. Each run starts with an empty `qa/`, writes an
append-only ledger and content-hashed manifest, and returns `passed`, `failed`, `blocked`, or
`invalid`. `ostler artifact` schema-checks what a workflow produces (a plan, a review resolution, a
QA outcome) against a registered contract.

```bash
ostler qa validate $(ostler path spec <story>)/qa_plan.py --json
ostler qa run      $(ostler path spec <story>)/qa_plan.py --json
ostler qa report       --spec $(ostler path spec <story>)
ostler qa frames       --spec $(ostler path spec <story>) --step <step-id>
```

Every run ends by rendering `<spec>/qa-report.md` from the ledger: one section per covered id with
its verdict, the step each covering assertion ran in, what it observed against what it expected,
and the screenshots behind it. Then come the scenarios step by step, and the warnings that would let
a rubber stamp through (an assertion with no observed value, a scenario that stopped early). It is
the one file a reviewer reads to decide whether the work is real, and `qa report` re-renders it.
When the target was recorded, every step in it says where it sits in the video, and
`qa frames --step <step-id>` writes the frames around that moment as PNGs with an index.

The run contract is in
[docs/QA-RUN.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/QA-RUN.md); the
artifact contracts are in
[docs/ARTIFACT-CONTRACTS.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/ARTIFACT-CONTRACTS.md).

### Local environments

`ostler env` runs the product on this machine from what the books say it is made of. Each book
that boots something keeps a `stack.yml` in the `ops/` folder beside its service book, at
`services/<book>/ops/stack.yml`. The stack root is `services/ops/stack.yml` beside the code, or
`services/<repo>/ops/stack.yml` in the artifacts folder, and is also a book. The file names the book's services, the compose fragment that defines each one, and what each
one needs. A need may sit in another book, so the web book names `api:api` and the api book
defines it once. Two books never define the same service. One names it, and the other needs it.

```yaml
# services/web/ops/stack.yml
default-fixtures: [schema]
services:
  web:
    about: the browser app, built from this checkout
    define: services/web.yml.j2
    needs: [api:api, api:provision]
  gateway:
    about: the proxy a browser opens
    define: services/gateway.yml.j2
    files:
      Caddyfile: services/Caddyfile.j2   # rendered, because it ends in .j2
    needs: [web]
    address: gateway          # the name a run reads its URL by
    port: 80
    host-port: 8443           # the shared copy only
```

A `define` template renders to one compose service. It sees `copy`, `repo`, `ops_dir`, `env_dir`, `dir`
(its folder in the copy, where its `files` land), `fixtures`, `fixture_sets` (the names of the sets
the bring-up loads), and `service('book:name')` for another
service's host name. ostler writes `depends_on`, `ports` and `container_name` itself, from
`needs:`, `once:` and `address:`, so a template that sets one is refused. Each copy gets one
compose file, its own project, its own named volumes and its own host ports. The shared copy is
the one exception, and keeps each `host-port`. A fixture file must exist only when its set is
loaded, so a set no bring-up names may point at a file this checkout lacks, such as a database dump
kept out of git. In a git worktree, a fixture file absent there is read from the main checkout.

```bash
ostler env check                     # every ops/stack.yml fits together: needs, cycles, one define each
ostler env up web --copy story-12    # web and everything it needs, waited until healthy
ostler env address gateway --copy story-12
ostler env compose --copy story-12 -- logs api-api
ostler env ls                        # each service, what it is, and the copies running it
ostler env ls --all                  # every copy on this machine, marked orphaned or idle
ostler env prune --dry-run           # what prune would tear down (orphaned) or stop (idle)
ostler env schema                    # the JSON Schema of a stack.yml
ostler env reset --copy story-12     # the copy's data back to what it started with, on the same addresses; refused while another process holds it
ostler env down --copy story-12      # data and rendered files go too, unless --keep-data
```

The copy defaults to `$STABLEMATE_LEASE`, so a workflow run that holds a lease brings up its own
copy without naming it. The stack root, `services/ops/stack.yml` or `services/<repo>/ops/stack.yml` in the artifacts folder, holds the repo's one secret source: `secrets: {file:
.env}` for a dotenv file, `secrets: {decrypt: <command>}` for a command whose stdout is dotenv,
or `secrets: {saddlebag: "environment=local"}` for the saddlebag secrets carrying those tags.
With saddlebag, every `docker compose` command runs under `saddlebag exec`, and no secrets file
is written. `ostler env exec [--copy NAME] -- CMD` runs a command under the secrets the stack
root's `secrets:` names.
`ostler env check` and `up` fail by name when a template requires a `${NAME}` the source does not
define. They never print a value.

A book names the books it needs with `needs: [api]` at its top level, and every service of it then
waits for every service of those books. A `once` job lists the names it writes in `outputs:`, and
the services that need it read them as `${NAME}`. A play that reaches a service its own services do not
need to start goes in `reaches: [api]`, which brings it up with the book and orders nothing. See the
format reference for each.

Every service needs an `about:` line, which `ostler env ls` shows. The format reference is the
`references/stack.md` page of the `ostler-cli` skill.

A copy's directory lives under the user state directory, or under
`$OSTLER_ENV_HOME`. It holds the rendered compose file, the helper files, the secrets file a
`decrypt:` command wrote for it, and an address book in the format `ostler qa` reads.

### Service books

`ostler book` runs a service book: the executable Python model of one HTTP or gRPC service, kept in
a repo under `services/<name>/`, or `services/<repo>/<name>/` in the artifacts folder. A run plays the book's journeys, the cells of its lifecycle
matrices and the input classes of its endpoints against the model and against the live service, and
compares the two. It refuses to judge an environment that is down. A web or mobile surface is not
covered yet.

The directory that holds `services/` is the working directory, or the one `-C DIR` names before
`book`. The command puts it on the import path itself. A service is named by its module.
In the artifacts folder a book sits at `services/<repo>/<name>/` and its module is `services.<repo>.<name>`.
`<repo>` is the repository's name: the workspace member name, else the repository folder's name in lower case
with `.` and `_` written as `-`. A surface-split book is one level deeper. A repository with `book.home: repo`
keeps `services/<name>/` and the module `services.<name>`. Books of different repositories name each other by
full module, `services.<other>.<name>`. The examples below use the bare form. `ostler book search` with no
`--service` reads the books of the repository it is started in, and every repository's when started in the
artifacts folder. `ostler book move` moves a book into its repository folder and rewrites the dotted module
names. `search` and the "no book" error name that command for a flat book left at `services/<name>/` in the
artifacts folder.

```bash
ostler book check   services.api          # build everything the book declares, no stack; 0 findings or 1
ostler book run     services.api          # every journey, cell and input class; exit 0, 1, 2 or 3
ostler book run     services.api --no-stack --only AddTodo,FindTodos
ostler book run     services.api --fresh-data   # reload the data first: the stack's `fresh` command, else a reset of the `ostler env` copy, else a refusal
ostler book explore services.api --seed-only   # walk the model's state graph, no app
ostler book walk    services.api --scene overdue --action read
ostler book search  overdue               # what the book says, read from index.tsv, and the company, team and product pages
ostler book pages [--level company|team|product] [--check]   # one line per page: level, slug, date, status, statement; --check names a page with no date or an empty body
ostler book explain services.api AddTodo
ostler book index   services.api          # rewrite index.tsv
ostler book stale   services.api --app ../api   # what changed in the app since the verified commit
# --story <id>: only the story's commits
ostler book verified services.api --app ../api  # record the app's head once stale is worked
ostler book verified services.api --app ../api --story ACME-1   # refuse only for the story's commits; leave the stamp while other commits are open
ostler book affected services.api --app ../api --since HEAD~3   # the calls and journeys the changed code calls for
ostler book move api web --repo acme                  # move flat books into services/acme/ of the artifacts folder and rewrite their module names
ostler book branch                                    # open the book branch of the current code branch in the artifacts repository, print its root
ostler book land                                      # land that book branch on the artifacts base by rebase, then remove its worktree and branch
ostler book files   services.api          # the files the book needs to load: its folder, then what it imports from outside it
ostler book decisions services.api
ostler book graph   services.api          # each record's state graph, as dot and svg
ostler book endpoints|screens|matrix|denied|plan services.api   # read the model, no app
```

A rule above any one service goes in a page of one of three books, by how far it reaches. The layout:

```
ai-artifacts/
  services/<repo>/<name>/        service book: what one service does
    decisions/                   why, tied to an element of that service
  services/<repo>/ops/           the repository's stack root
  products/<product>/            product book: one markdown page per rule
  teams/<team>/                  team book
  company/                       company book
  epics/  specs/  backlogs/      as before

<repository with book.home: repo>/
  services/<name>/   product/    a tool that publishes its own book
```

The books:

| Book | Holds | Lives in | Written by |
| --- | --- | --- | --- |
| service | what one service does and why: its Python and `decisions/` | `<book root>/services/<repo>/<name>/`, or `<book root>/services/<name>/` with `book.home: repo` | agents |
| product | the product's words, the constraints no story may break, where the truth for a calculation lives | `<artifacts dir>/products/<product>/<slug>.md`, or `product/<slug>.md` beside `services/` with `book.home: repo` | agents |
| team | how one team builds across products: ADRs, RFCs, conventions | `<artifacts dir>/teams/<team>/<slug>.md` | people |
| company | rules every team follows | `<artifacts dir>/company/<slug>.md` | people |

The artifacts dir is what `resolve_artifacts_dir` returns, and the book root is the folder that holds `services/`: the
artifacts folder, or the repository when its `agents.yml` says `book.home: repo`. The product is `book.product`, else the
repository's name. Started in the artifacts folder, `book pages` lists every product. A team's name is `book.team` in the
code repository's `agents.yml`. With no `book.team`, no team book is read. A folder that does not exist is skipped.

A page starts with a `date:` line (required), then optional `sources:` and `status:` lines, a blank line and prose whose
first line is its statement. `status:` is free text, for an ADR or an RFC: `proposed`, `accepted`, `superseded by <slug>`.
`ostler book search` reads every level with every query, with or without `--service`, and prints their hits first, under
`== company`, `== team <name>` and `== product` (`== product <name>` for a named product), in that order. A hit line reads `<level>  <path>:<line>` and ends with
` (superseded)` when the page's status starts with `superseded`. `--kind company`, `--kind team` or `--kind product` shows
only that level and any other `--kind` leaves them out. `ostler book pages` lists the pages and `--check` names each page
with no `date:` line or an empty body.

When two books disagree, the order of authority is company, team, product, service decision, story. An agent that finds
two of them in conflict reports the conflict and picks neither.

A screen book says how a person moves between screens. `first = True` marks a screen a person can open directly.
`leads_to = <Screen>` on an interaction names the screen the person is on once the act went through, and `inside`
with `shown_in` names the screen that hosts a dialog or an inline form, and the phase of the host that shows it.
`check` refuses a book with no first screen and a `leads_to` or `inside` that names no screen of it, and tells of a
screen no walk from a first screen reaches. `ostler book search` prints, for a screen, an interaction or a component,
the interactions to perform to get there. `ostler book explain services.web ListPage.edit` reads one component:
its phases and the way to its screen.
The play verifies it: after an act, a stated `leads_to` is waited for on the surface and a miss fails the step. An act with
no `leads_to` that leaves its screen passes, and the run lists its interaction at the end.

Exit 3 means the place could not be judged, and what ran before it is no verdict. Reports go to `--out`.
Omitted, they go to a fresh folder under the system temp directory, and the command prints its name
on a `reports:` line. The `ostler-book` skill is the guide to writing a book.

`ostler book files` lists, one path per line relative to the book root, every file a book needs to load: its
own folder, then the files its modules import from elsewhere under the book root, such as `services/shared/accounts.py`
and the `__init__.py` files on the way. It reads the imports with `ast`, follows them transitively, loads nothing and
exits 0. An import of `ostler`, the standard library, an installed package or another service's book is not listed,
since another book is its own commit. `--outside` prints only the files beyond the book's own folder. `ostler book check`
prints the same outside files as one note, never blocking, and a commit of a book takes them with it.

`ostler book affected` answers which plays a code change calls for. It reads the diff from the verified commit, or
`--since`, to the working tree, so staged, unstaged and untracked work under the app's roots counts. It reads the
`source=` pointers of the endpoints, interactions, screens, records, actions and outside happenings, and no app runs.
`--story <id>` reads the story's own commits instead of the range: the commits reachable from HEAD whose `Story:`
trailer names the id, bounded by `--since` when it is given, plus the uncommitted and untracked work. No VERIFIED
commit is needed. Each file is compared from the parent of the first story commit that touched it to the last story
commit that did (to the working tree when the file is dirty), so commits of other work between the story's do not
count, unless they edit a file the story's commits also touch. A message that only mentions the id in its body does
not match. With no commit that carries the trailer the command prints so, writes no report and exits 2.

`ostler book stale --story <id>` and `ostler book verified --story <id>` read the same commits, committed work only,
because `verified` writes HEAD. `--since` bounds them. `stale --story` lists what those commits left open.
`verified --story` exits 1 when the story's own commits changed a file or function no element names, or a pointer is
missing. It exits 0 and writes HEAD when that change is named and no other commit since the verified commit is open.
It exits 0, prints `not stamped:` and writes nothing when the story's change is named and other commits since the
verified commit left code no element names. It exits 2 when no commit carries the trailer.
A changed symbol names its element, and an element names its calls: an action reaches every endpoint,
interaction and outside happening that carries it, and a screen its interactions. The plan is `none` (nothing
changed, or only ignored files and imports), `partial` (a named list) or `whole`. It is `whole` when a record is
itself touched or when the walk cannot name a list: an action no call carries, a screen with no interactions.
A changed symbol is a function, a method, a type declaration, a package-level constant or variable, or an entry of
a Go `const (` or `var (` block. It is matched to the pointers that name it, so a record that points at
`file::Ticket` is touched by a change to the struct `Ticket`. A pointer with no symbol names the whole file and is
touched by any change to it.
The command then follows mentions. It reads every source file under the app's roots that the ignore patterns keep
(test files stay out) and maps each symbol to the text of its definition. A symbol mentions another when the other's
bare name is a whole identifier in that text. The closure of a changed symbol is the symbol and every symbol that
mentions a member of the closure, to a fixed point, except that a type (a Go `type`, a class, an interface, an enum) joins only when it is itself changed, because a type that declares or holds a name is not a caller of it. An element is affected when any of its pointers names a
member. A record whose own symbol changed makes the plan `whole`. A record whose symbol is a function that mentions the changed one is listed in the chains with no play of its own and leaves the plan as it is. Matching is by
bare name, so two functions that share a name are both followed, except that a module-level name a file defines (a Go
package, for a Go file) means that file's own definition when the file mentions it, and a method is mentioned by its
bare name from anywhere. Nothing else resolves types or packages. A file whose
definitions cannot be read with confidence (unbalanced brackets, a definition that never closes) is one unit: each
symbol in it mentions all the file mentions. Each chain says how the element was reached: `direct` when its own
symbol changed, `through <symbol>` for the nearest symbol of the closure path.

`affected` also reads the book's own folder, `services/<repo>/<name>/` (`services/<name>/` with `book.home: repo`) and the files it imports under the book root, since
the same commit, uncommitted and untracked files included. An edited element class (an endpoint, interaction,
screen, action, outside happening or journey) selects its plays, and its chain starts with `book <path>:<Class>`.
A changed module-level name (an assignment, an annotated assignment or a function) or a changed class that is no element of the book (a fixture dataclass, a helper, a mixin) selects the element classes that use it,
found through the book's own files by the identifiers each definition mentions and the imports that carry the name, and its chain reads `NAME <- used by Class`. A journey that uses it lands in `by_journey`. A changed line that is no class and no name, or a file that does not parse, makes the plan `whole` with the reason
`a shared book file changed: <path>`, and so does a changed name or class that reaches no element and is star-imported, read with `getattr` or `globals()`, or used only by names that reach none. A name or class nothing mentions selects nothing and is listed under `unused` in the JSON and `changed and used by nothing:` in the print. Import lines and the module docstring never count. A deleted class needs no play. The plan is `empty`, with exit 1, when files
changed and none selects a play, and `none`, with exit 0, when nothing changed. The `diff` field of
`<service>-affected.json` counts the changed app files and book files and lists, up to 50 paths with a count, the
changed files under `not_computed` that the command did not judge: files outside every root and files of the book
that are not Python. `only` is the list for `run --only`, `by_journey` the titles for `run --partial --journey`, and
`whole: true` with its `reason` means to run the whole book with no `--only`. `owed` lists the fallback reasons one by one, and `story` and `commits` name the story and the commits read. Under `whole`, `only` and `by_journey` stay the selection the walk names, so a caller can play them and owe the rest. The print order is in the next paragraph. `run --only` with an empty value is an
argument error, exit 2.

The report answers two questions. `only`, `journeys` and `by_journey` are everything the change might affect. `direct_journeys` and `direct_only` are what a story plays now, and they come in three ranks. Rank 1 is the journeys whose own class the change added or edited in the book. Rank 2 is the calls whose own class the change added or edited, and the calls of an edited action or screen class. Rank 3 is the calls of the elements whose `source=` names a changed file or symbol with no hop in between, and of the `widened` elements. What the change reaches only through a hop, or through a changed shared book definition, is counted under `reached` as `{"calls", "journeys", "causes"}`. Each cause is `{"cause", "calls", "journeys"}`, counted beyond the direct selection, and the causes sort by calls, then journeys, both descending, then by name. The print gives the plan, `direct journeys`, `direct calls` and the `reached beyond that` line with its top three causes, then `owed to a whole play`, `changed`, the `calls` and the `journeys`, and lists the files not judged last, up to 20 paths. The last line plays the direct selection when there is one: the direct journeys by `--partial --journey`, then the direct calls by `--only`.
A hunk with no definition line counts at the file and leaves the other hunks of the file to their own symbols. At
the file it reaches every element that names it, a record that names it makes the plan `whole`, and the place is
listed under `widened`. A Go hunk of import lines only changes nothing by itself and is listed under `imports`,
unless it adds or removes a blank or dot import, which counts at the file. Each fallback is listed with its path.
A changed symbol whose closure reaches no element, and a changed path no element names, is listed as uncovered and
makes the exit code 1. A path an ignore pattern drops is listed as ignored. Every changed path is in exactly one of
mapped, uncovered and ignored. A screen no interaction names, or an action no call carries, is listed under `unplayed` with its chain
and does not widen the plan, because no play checks it. A record or an event still makes the plan `whole`. The command prints each chain as `path::symbol -> Element (kind, how) -> plays`, ends
with the `ostler book run` line to play, and writes `<service>-affected.json` to `--out`. It does not walk dependent
books, configuration or data, and says so in the `not_computed` field. `run --only` accepts an outside happening's
name and plays the journeys and cells that arrange it.

A run ends its report with the section `Stated and never played`. It lists each outside happening, action,
rule and scene of the book that no journey step, cell, given or input class exercised, with the step that
closes it, and the streaming calls a run cannot play. An action whose only carrier is an unplayed outside
happening is named on that happening's line, and a rule counts once across every endpoint. A rule a known
defect covers is not listed. When the environment names no delivery tap, one line names the events the played
actions emit and says a tap closes it. A partial run prints `not judged on a partial run`, and a run with
skips lists what the skipped plays could have exercised under `not judged here` and judges the rest.
On a full play the section turns the run red under the part `never played`. An outside happening, action,
rule or scene that no play exercised and the book does not declare is red. A line says what closes it:
play it in a journey step, a matrix cell, an input class or a `Given`. Where the book cannot cause it, it
declares the element in `Service(unseen=...)` with `Unseen(Ghost, Because.RUNTIME, "why")`. The section then
lists it with its reason and the run stays green. A declaration for an element the run played, or that the
book does not state, is red as stale. Declaring an outside happening covers the action it carries. An action that only a streaming call carries is left to that call's line. The
events line, the streaming calls and `not judged here` are never red. `Unseen` takes an endpoint with an
item, `Unseen(Endpoint, "401", Because.X, "why")`, and any other kind without one, `Unseen(Element, Because.X,
"why")`. Those four kinds take `RUNTIME`, `OUTSIDE` or `NO_ACCOUNT` only. The run also writes `<service>-played.json` to `--out`: for each kind, each
stated element, sorted, with the plays that exercised it (a journey, a cell or an input class by name), an
empty list for an element no play did.

The run also keeps the witness: for each declared answer, whether a play saw the service produce it, and for each field,
whether a play saw it with a real value. A field of a value domain (`Enum`, `Bool`, `Int`, `Num`) that the run saw in one
value only proves nothing about the field, because a service that forces it to a constant passes. On a full play the run
prints the section `Seen with one value only` after the witness lines, with one line per such field, `Enum` and `Bool`
first, and writes it to `<service>-witness.md` under `## Seen with one value only`. A field typed `Id`, `Token`, `Bytes` or
`Str`, a field marked `opaque` or `ignores`, and a field declared `Unseen` are not listed. The section never changes the
verdict or the exit code, and a partial run prints `not judged on a partial run`.

## The parse index

`ostler doctor` re-reads and re-parses the same files on every invocation, and an agent that
checks its work often pays that cost dozens of times an hour. The parse index is a persistent,
content-addressed store that removes the repetition. **It is on by default**, and everything
about it is designed so that the worst thing a wrong index can do is be slow.

### What is cached, and what deliberately is not

Three products, and only three:

| Product | Key |
|---|---|
| **Parse products** — a document's frontmatter, sections, bullets, links and tables | the repo-name-qualified repo-relative path + the file's content sha |

Parse products are a pure function of bytes, which is what lets them be stored under a content key
with no invalidation rule beyond a single *epoch* hash over the global inputs (ostler's
version, the bundled schemas, the dynamic kind registry, the config files). Change any of those and every entry is invalidated at once.

**Doctor's findings are not cached.** Nothing that a check *concluded* is ever served from the
index — only the parse products a check reads. And the **graph-global checks are always
recomputed**, on every run, never cached: the cross-epic seed and dependency
constraints and milestones together cost a few milliseconds, so
there is nothing to win by caching them and a whole class of transitive invalidation to lose.
The hard half of the invalidation problem is the half that had nothing to gain.

Writers stay uncached on purpose: the index serves the read-only document accessor, while the
commands that mutate a document parse it themselves. A shared parsed document handed to a
writer would be a live bug, not a cache hit.

### Where it lives, and how that is resolved

The directory is resolved in this order, first one wins:

1. `--index-dir DIR` — an explicit path on any command, including `ostler cache clean`;
2. `$OSTLER_INDEX_DIR` — the environment override, which is how a container points every tool
   in it at a cache copied in from the host;
3. `ostler_index_dir` in ostler's shared config;
4. the default: `ostler-index` under the shared stablemate cache (`~/.cache/stablemate/`).

The entry key holds the repo-relative path *qualified by the repo name*, not an absolute one,
so two worktrees of the same repo — and the same repo mounted into a container — share every
entry rather than each warming a partition of their own.

### Controls

```bash
ostler doctor --no-index                 # off for this run; the index is on by default
ostler doctor --index-dir /tmp/ix        # somewhere else for this run
ostler doctor --verify-index             # run both ways and diff the reports
ostler cache clean                       # evict entries not written for 14 days
ostler cache clean --all                 # remove everything, aged out or not
ostler cache clean --max-age-days 2 --json
```

`--no-index` is the escape hatch, present on every command; `--verify-index` is the correctness
gate — it runs doctor **with the index and without it in one command and diffs the two reports**,
exiting non-zero on any disagreement, so "cached and uncached agree" is something CI asserts
rather than something a README promises. Eviction has both paths: the explicit `cache clean`
above (`--all` removes every entry, not only the aged-out ones), and automatic age-based pruning
on write, so an unattended machine cannot grow the cache without limit. An entry's age is when it
was last **written**, not last read — a key names the exact bytes it was computed from, so an
entry still being read is one whose content has not moved, and evicting it costs the single
recomputation that writes it back. The sweep is a full directory walk, so it runs at most hourly
per index directory rather than on every write; the bound is an age, and an age bound does not
need checking at write granularity.

`doctor --json` reports what the index did, added to the report rather than substituted for any
of it:

```json
{ "…": "…",
  "index": { "dir": "/home/you/.cache/stablemate/ostler-index",
             "enabled": true, "hits": 1382, "misses": 0 } }
```

That is the line a disagreement between two runs is diagnosed from without instrumenting
anything: the same **hits**/**misses** against different directories is a different fault from
different counts against the same one. Under `--no-index` both counts read zero.

### It is content-keyed, so it is allowed to go stale

A host cache is refreshed by whatever happens to run ostler on the host; there is no warming
command and no freshness protocol, and a container never writes back to the cache it was given.
The consequence is worth stating plainly: **because every entry is content-keyed, a stale index
costs time and never correctness.** An entry either matches the bytes in front of it or it is
not consulted at all, so the failure mode of decay is a run that pays close to the cold price —
never a run that answers from an out-of-date parse. Deleting the whole directory at any moment
is safe for the same reason.

This is also why **every command that loads a graph populates the index, including the
read-only ones** (`list`, `search`, `query`, …). Incidental use is the only
thing keeping a host cache warm between refreshes, and a read-only command that left it cold
would make the next `doctor` pay full price for no reason.

## Python API

The major graph and workflow-facing operations are available in-process through the
`Ostler` facade. Prefer it over spawning the CLI and parsing JSON when the operation is
available there: you load the graph once and get back plain objects instead of a
subprocess and a stdout scrape.

```python
from ostler import Ostler

okf = Ostler("path/to/repo")              # graph root discovered upward, like `-C DIR`
okf.next_story("checkout-flow")           # {"slug": …} | None
okf.create_story("checkout-flow", "02-pay", "Payment", covers=["seed-1"])
okf.doctor()                              # a QaOutcome; .data is the integrity report
```

Every check on the facade, `doctor` and the whole qa/artifact family, answers
in that same `QaOutcome` (`ok`, `status`, `message`, `data`) rather than raising: a data-shaped
failure like a book that will not load is *part of the answer*, not
an exception each caller re-catches. A call-site mistake still raises.

A public module comes with it, and it is the reason nothing here reads a document with a regex:
**`ostler.markdown`** is the one markdown parser (frontmatter, sections, bullets, GFM tables,
links, never one inside a fence).

The facade's snapshot semantics and the full call surface are in
[docs/PYTHON-API.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/PYTHON-API.md).

## Id allocation

`create backlog-item|milestone|epic|story` allocates an id,
scaffolds the canonical markdown, and (for stories) inserts the `### <slug>` block into the epic's
`## Stories`. There is no external id allocator.

The id prefix is `repo.id_prefix` in the `agents.yml` at the graph root: a letter, then up to 15 letters, digits or underscores. A mint refuses while it is unset or malformed, and the error names the key and the file.

An id is `<PREFIX>-<ULID>` — the repo prefix (`repo.id_prefix`) plus a monotonic ULID: 26 Crockford-Base32 chars encoding a millisecond timestamp and 80 bits
of randomness. It sorts by mint time and needs **no coordination**, so two worktrees, two processes
or two clones never collide and there is no counter to lock or merge. An id is an opaque string.

### Short handles

A 26-char id is not a thing anyone retypes, so ostler abbreviates it git-style to a **handle** —
`<PREFIX>-<6+ chars>`, the shortest slice unambiguous among the ids currently in the repo:

```bash
ostler list --type seed                # ACME-K3XQ7P    ← handles, the default for human output
ostler list --type seed --json         # ACME-01JB…     ← full ids, the default for --json
ostler --full-ids list --type seed     # full ids in human output
ostler --handles  list --type seed --json
```

The split is the point: a person wants a token short enough to copy, while a program wants the
identity that never changes. A handle **lengthens** the moment a colliding id is minted, so it is a
display form — never what gets written into a document.

Input is not modal. A handle is accepted wherever ostler takes an id, in either mode and from either
surface, so a token copied out of one command goes straight into the next:

```bash
ostler query stories-covering-seed ACME-K3XQ7P
ostler seed add checkout ACME-K3XQ7P --status resolved
ostler backlog prune ACME-K3XQ7P
```

The slice is of a *hash* of the ULID rather than of the id itself: monotonic ids minted in the same
millisecond differ only in their low bits, and hashing decorrelates them so even a burst abbreviates
to six characters. From Python, `okf.handle(id)` / `okf.handles()` render and `okf.expand(token)`
resolves — though every ostler entry point already expands its own id arguments.

## Profiles

`ostler` infers a profile from the tree: **`full`** when `docs/epics` exists (the epic/story/seed
planning graph), **`exploration`** otherwise (no planning graph).
Override any default in an optional `organization:` block in `agents.yml` at the repo
root (`ostler.yml` is the legacy name of the same file and still loads, with a warning).

## Templates (custom hierarchies)

The built-in types above (epic/story/milestone/spec) are fixed. For a *different*
documentation shape — your own document kinds, nesting, required fields, status enums — declare it
per-repo in **`.agents/templates.yml`** (git-tracked). A kind is live
for `new`/`find`/`set`/`remove`/`doctor` the moment it's written — no separate activation step.

```bash
ostler template new    <name> [kind ...]        # declare a template, optionally with stub kinds
ostler template edit   <name> --set <kind>.<field>[.<subfield>]=<value>
ostler template find   [<name>]                 # list templates, or one template's definition
ostler template delete <name>
ostler template apply  <name>                   # mkdir -p each doc_root + inject CLAUDE.md guidance
```

Once a template's kinds are declared, use the same generic verbs against instances:

```bash
ostler new    <kind> <name> [field=value ...]   # <parent-kind>=<name> scopes nesting
ostler find   <kind> [<name>]
ostler set    <kind> <name> field=value ...
ostler remove <kind> <name>
```

See
[SPEC.md §9](https://github.com/GabrielCpp/stablemate/blob/main/ostler/SPEC.md#9-templates-and-template-declared-kinds)
for the full YAML schema, a worked 3-level nesting example, and the bundle-vs-leaf shape rules.

## Versioning

The format is versioned `<major>.<minor>`; the current version is **1.0**. Minor bumps add
backward-compatible fields; major bumps may change required frontmatter or the `epic.md` grammar.

## License

MIT. See [LICENSE](https://github.com/GabrielCpp/stablemate/blob/main/ostler/LICENSE).
