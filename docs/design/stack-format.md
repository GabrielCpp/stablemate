# The stack format, and what `ops/` is for

**Disclosure.** I wrote this note after reading the existing solution: the `stack.yml` loader,
renderer and runtime in ostler, the format reference in the ostler skill, the runbook and
environment node types, saddlebag's environment docs and the earlier
[run stack instances](run-stack-instances.md) note. The design decisions they carry are claims in
section 1b. I checked each part and concept against "would I have named this without having seen
the solution?" Where a name survives from the code, section 5 says why.

## 1. Problem

A developer who runs a client product locally keeps a pile of setup files in the product repo:
a local Dockerfile per app, a proxy config, a compose file, make targets, an `.env.example`. The
book's `stack.yml` was meant to replace that pile, but today it cannot. It cannot say "the web
book needs the whole api book", only one service at a time. It cannot place a Dockerfile in the
copy's folder and build it against the checkout, so the local Dockerfile stays in the repo. Its
secrets come from saddlebag environments, one per book, that someone fills key by key on each
machine, when the team already keeps one `.env` or one encrypted vault file. An infrastructure
tool such as Pulumi or Terraform can run as a one-shot container, but what it creates cannot
reach the services that start after it. The format is described in an agent skill reference
only, and `ostler env ls` lists copies without saying what any service is.

**Done**, as the developer sees it:

- The product repo holds no local-only Dockerfile, proxy config or compose file. Each lives as a
  template in the book's `ops/` folder and lands in the copy's folder on `up`.
- A web book names `api` once, at the book level, and `up web` brings every api service up first.
- One `.env` file, or one encrypted file the team decrypts with its own tool, feeds every book's
  `${VAR}`. A missing name is reported by `ostler env check` before anything boots, by name and
  never by value.
- A Pulumi, Terraform or any other tool's job runs with no ostler change, and a value it
  produces (a bucket name, a generated id) reaches the services that need it as `${VAR}`.
- `ostler env ls` prints every service with its one-line `about`, which copies run it and the
  address it publishes.
- One reference page lists every key the loader accepts, and a test fails when the two disagree.

**Out of scope:**

- the production Dockerfiles and deploy files. They stay in the product repo. A local service
  may still build from one with `dockerfile: {{ repo }}/<path>`, and only a Dockerfile that
  exists for local setup alone moves into `ops/`;
- deployed environments and preview deploys. A copy stays a local, disposable compose project;
- the runbook's own bring-up recipe and whether it survives once every book has a `stack.yml`
  (parked, see section 7, A8);
- saddlebag's credentials, leases and `fill`, which are untouched;
- infrastructure that lives outside the copy and needs a destroy on `down` (A2).

## 1b. Claims

1. `stack.yml` sits beside the book's pages, at `docs/features/<book>/stack.yml`. (format reference)
2. Every path in the file is read from the folder the file sits in. (format reference)
3. `secrets:` names one saddlebag environment per book, rendered per copy. (format reference)
4. `render:` lists helper templates. Each is Jinja-rendered and lands in the service's folder of
   the copy with `.j2` stripped. (format reference, renderer)
5. A template sees `copy`, `project`, `shared`, `repo`, `book_dir`, `dir`, `fixtures` and
   `service()`. (format reference)
6. `needs:` names services only: `name` for this book's, `book:name` for another's. (format reference)
7. `once: true` marks a job that runs to completion. (format reference)
8. ostler writes `depends_on`, `ports` and `container_name`, and refuses a template that sets
   one. (renderer)
9. `ostler env ls` lists the copies of the repo's stack. (commands)
10. `about` is optional. (loader)

## 2. Parts and concepts

### Level 1: parts

1. **Stack description.** What the stack is made of: books, their services, what each needs, the
   files each brings. Owns the format and its validation. Never knows how docker runs anything.
   Hands a validated catalog to every other part.
2. **Copy assembly.** Turns a chosen slice of the catalog into files in one copy's folder: the
   compose document and every rendered or copied file. Never knows where a secret value comes
   from. Hands the folder to the lifecycle.
3. **Secret supply.** Produces the copy's secret values from the repo's one source and hands
   them to compose as a file only it and compose read. Never knows which service uses which
   value. Hands the lifecycle a file path and the set of names it defines.
4. **Copy lifecycle.** Brings a copy up in order, collects what jobs produce, tears it down.
   Never knows the format's keys. Reads the catalog and the assembled folder.
5. **Explaining the stack.** Tells a person or an agent what exists: the service listing, the
   reference page, the schema. Never changes a copy.

Flow: description validates and hands a catalog to assembly, supply and explanation. On `up`,
supply writes the secrets file, assembly writes the folder, the lifecycle runs the first wave
(jobs whose outputs others need), reads their outputs, then runs the full copy. On `down` the
lifecycle removes the copy and supply's file with it.

### Level 2: concepts

**Stack description**

| Concept | Owns | Never knows |
|---|---|---|
| Stack root | the repo-wide settings: the secret source | any book's services |
| Book | its services and the books it needs whole | how another book's services are defined |
| Service | one runnable unit: about, definition template, needs, address, files, fixtures | the copy it will run in |
| Reference | a name for one service or one whole book, and its expansion to services | whether the service is up |
| Catalog | every book and service, each problem found across them | docker |
| Key table | the keys each level accepts and what each means | how a key is applied |

A service plays one role for the lifecycle ("when are you ready?") with two variants: a
**server** is ready when started or healthy, a **job** is ready when it exited 0 and its declared
outputs exist. The catalog is the read-only reference every part consults. The key table is a
shared value the loader, the reference page and the schema all read.

**Copy assembly**

| Concept | Owns | Never knows |
|---|---|---|
| Copy folder | where one copy's files live in local state | the repo layout |
| Template context | the values a template sees | which file renders with it |
| File placement | one source mapped to one target in the service's folder: a `.j2` source is rendered, any other is copied byte for byte | compose |
| Compose document | merging the service blocks and writing the keys ostler owns | secret values |

**Secret supply**

| Concept | Owns | Never knows |
|---|---|---|
| Secret source (role) | "give this copy its values as a dotenv file, and the names in it" | how the file is stored on disk |
| Plain file (variant) | reading one `.env` file in the checkout | encryption |
| Decrypt command (variant) | running the team's own decrypt command and capturing its stdout | which tool it is |
| Name check | the `${VAR}` names templates use that neither the source nor a needed job defines | any value |

**Copy lifecycle**

| Concept | Owns | Never knows |
|---|---|---|
| Wave plan | splitting a bring-up at jobs whose outputs another service reads | the format |
| Job outputs | collecting a job's `KEY=value` file and checking its declared names | what tool wrote it |
| Teardown | down, keep-data and reclaiming a dead run's copy | secrets' source |

**Explaining the stack**

| Concept | Owns | Never knows |
|---|---|---|
| Service listing | each service with its about, address and the copies running it | how a copy started |
| Reference page | the prose and the key tables a reader learns the format from | the loader's code |
| Schema | the JSON Schema an editor validates `stack.yml` with | prose |

## 3. Invariants

1. **A secret value never reaches a terminal, a log or a file outside the copy folder.** Owner:
   secret source. The decrypt variant captures stdout, writes it `0600`, and reports a failure by
   exit code and stderr only. Upheld by teardown, which deletes the file.
2. **Every `${VAR}` a rendered block uses is defined by the secret source or by a job the service
   needs.** Owner: name check. Compose would substitute an empty string with a warning, and the
   service would boot broken.
3. **A file lands inside its service's folder of the copy.** Owner: file placement. A target with
   `..` or an absolute path is refused.
4. **A service is defined once and an address is published once.** Owner: catalog. (Exists.)
5. **The format has no key, value or branch that names a tool.** Owner: key table. A tool is an
   image and a command inside a template.
6. **The keys the reference page lists are the keys the loader accepts.** Owner: key table, held
   by a test that compares the page's tables to it.
7. **One repo has one secret source.** Owner: catalog. A `secrets:` key outside the stack root
   is refused.
8. **Every service says what it is.** Owner: catalog. A service with no `about` is refused, so
   the listing never shows a blank.

## 4. Forces and patterns

### Forces

- **Tools appear.** Pulumi, Terraform, a seeder, a cloud emulator's CLI. Each must run with no
  ostler change.
- **Secret storage differs per team** and changes independently of the stack: a plain `.env`,
  sops, ansible-vault, age.
- **A job's product is needed before its dependents start**, because compose reads `${VAR}` and
  `env_file` when it loads the project, not when a container starts.
- **Books depend on books.** A web book needs everything the api book runs, and naming each api
  service again in the web book drifts when the api book grows.
- **Readers are humans and agents.** Both need the same key list, and it grows.
- **Builds run from the checkout.** The build context is the checkout root, so a run in a
  worktree builds its own code, while the Dockerfile lives in the copy's folder.

### Between parts

A sequence of stages handing one value along: catalog, then folder, then running copy. No force
asks for more. The secret source is a port with two adapters, because storage varies on its own.

### Inside a part

- **Tools** (force 1): no pattern. A job is a container the template defines. The only thing
  ostler adds to a job that declares `outputs:` is a mounted folder and the variable
  `STABLEMATE_OUTPUTS`, the path of the file it writes `KEY=value` lines to. Pulumi writes
  `pulumi stack output --shell`, Terraform writes `terraform output`, piped through whatever
  the team likes. ostler never learns which.
- **Secret source** (force 2): role plus two variants. The decrypt command is the open end: a
  third storage is one command line in the stack root, not a new variant.
- **Wave plan** (force 3): two compose invocations on the same project when, and only when, a
  needed job declares outputs. The first brings up that job's closure, the second the whole
  copy with the outputs file added as an `--env-file`.
- **Book references** (force 4): the level decides the namespace. A book-level `needs:` names
  books. A service-level `needs:` names services. No new syntax.
- **Key table** (force 5): one table drives the loader's accepted keys, the schema and the page
  test.
- **Template context** (force 6): plain values. `repo` is the checkout root, `env_dir` the copy
  folder, `dir` the service's folder inside it.

### The format after

`docs/features/ops/stack.yml`, the stack root:

```yaml
secrets:
  decrypt: sops --decrypt docs/features/ops/secrets.enc.env
```

or

```yaml
secrets:
  file: .env
```

`docs/features/web/ops/stack.yml`:

```yaml
needs: [api]
default-fixtures: [schema]
services:
  web:
    about: the browser app, built from this checkout
    define: services/web.yml.j2
    files:
      Dockerfile: images/web.Dockerfile.j2
      Dockerfile.dockerignore: images/web.dockerignore
  gateway:
    about: the proxy a browser opens
    define: services/gateway.yml.j2
    files:
      Caddyfile: services/Caddyfile.j2
    needs: [web]
    address: gateway
    port: 80
    host-port: 8443
```

`services/web.yml.j2`:

```yaml
build:
  context: {{ repo }}
  dockerfile: {{ dir }}/Dockerfile
environment:
  API_URL: http://{{ service('api:api') }}:8080
  SESSION_KEY: ${SESSION_KEY}
```

`docs/features/api/ops/stack.yml`, a job whose output the api reads:

```yaml
services:
  infra:
    about: creates the upload bucket in the storage emulator
    once: true
    needs: [storage]
    outputs: [UPLOAD_BUCKET]
    define: services/infra.yml.j2
  api:
    about: the HTTP API, built from this checkout
    needs: [infra, db]
    define: services/api.yml.j2
```

`ostler env ls`:

```text
api
  api:db        the MySQL the api reads and writes             shared, story-12
  api:infra     creates the upload bucket in the storage emu…  shared (done)
  api:api       the HTTP API, built from this checkout         shared, story-12
web
  web:web       the browser app, built from this checkout      shared
  web:gateway   the proxy a browser opens   gateway :8443      shared
```

**What `ops/` is for.** A book's `ops/` folder holds everything it takes to run the book on a
machine: `stack.yml`, the templates and plain files it places, and the `environment` and
`runbook` pages that describe it. Nothing in `ops/` is product. Paths in `stack.yml` are read from
`ops/`. A secret path and the decrypt command are read from the repo root, because a `.env` sits
there by convention. The features root's `ops/stack.yml` is the stack root. In a one-book repo it
is also that book.

### Claims

1. Rejected, revised: `stack.yml` moves into `ops/`, so the folder is self-contained (A7).
2. Kept, from force 6 and the move: paths read from the file's folder, now `ops/`.
3. Rejected: one source per repo (forces 2 and the "single file" requirement). Saddlebag leaves
   the bring-up path.
4. Reshaped into `files:`, a map of target to source. A target name is explicit, a directory
   source copies a tree, and only `.j2` sources render, so a file holding `{{ }}` for another
   tool survives.
5. Kept and extended: `env_dir` is added. `book_dir` is renamed `ops_dir`, since after the move
   it names the `ops/` folder.
6. Kept at the service level, extended at the book level (force 4).
7. Kept. It is the job variant's spelling.
8. Kept. ostler also writes the outputs mount on a job that declares `outputs:`.
9. Reshaped: `ls` lists services, with copies as a column.
10. Rejected: `about` is required (invariant 8).

### SOLID check

- Single responsibility: each Owns reads without "and", except Service, which is a value.
- Open/closed: a new secret storage is a command line; a new tool is a template. Neither touches
  ostler.
- Liskov: plain file and decrypt command are each a kind of secret source only.
- Interface segregation: the lifecycle asks the source for a path and a name set, nothing else.
- Dependency inversion: the lifecycle never names a variant.

### Open lookups

- Does compose accept a `dockerfile:` outside the build context, and does BuildKit read
  `<Dockerfile>.dockerignore` beside it? Decides whether `files:` replaces the repo's local
  Dockerfile (A3).
- Does any caller read `ostler env ls --json`? Decides whether `copies` must stay.
- Does `compose up --wait` with a subset of services leave the rest of the project alone?
  Decides the wave plan.

## 5. Mapping onto the existing system

### Revision log

- 1b claim 1, section 4: the move into `ops/` was a choice, logged as A7, since the templates
  already sit in `ops/services/` in the reference example.
- Section 2, Copy assembly: `dir` already exists as the service's folder
  (`ostler/ostler/environments/render.py:127`). Only `env_dir` is new.
- Section 5, Reference page: moved from the book-format skill (`ostler-okf`) to the CLI skill
  (`ostler-cli`). Review: `stack.yml` is read by `ostler env`, a subcommand, so its reference
  sits with the other command references. The book-format skill keeps a link.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Stack description | Reshape | `ostler/ostler/environments/spec.py`: `BOOK_KEYS` and `SERVICE_KEYS` at lines 18 and 19 are the key table, but nothing else reads them |
| Copy assembly | Reshape | `ostler/ostler/environments/render.py` |
| Secret supply | Reshape | `ostler/ostler/environments/commands.py:246`, `_render_secrets`, which shells out to saddlebag per book |
| Copy lifecycle | Exists, extended | `commands.py` `cmd_up`, `runtime.py` `Compose`, `leases.py` |
| Explaining the stack | Reshape | `commands.py:182` `cmd_ls`; the reference sits in the book-format skill at `base-library/library/skills/ostler/ostler-okf/references/stack.md`, with a copy in `ostler/README.md`. It moves to the CLI skill (revised, see the revision log) |

### Concepts

- **Stack root**: New, in `spec.py`. The features root's `ops/stack.yml`.
- **Book**: Reshape. `Book` (`spec.py:72`) gains `needs`. `secrets` moves to the stack root.
- **Service**: Reshape. `Service` (`spec.py:45`) drops `render`, gains `files` and `outputs`.
- **Reference**: Reshape. `_qualify` and `closure` (`spec.py:260`) expand book-level needs.
- **Catalog**: Exists. Gains invariants 2, 7 and 8.
- **Key table**: Reshape. Today two frozensets. They become one table with a description per
  key, which the schema and the page test read.
- **Copy folder**: Exists, `runtime.copy_for`.
- **Template context**: Reshape, `render._context`: add `env_dir`, rename `book_dir`.
- **File placement**: Reshape, `render.render` lines 74 to 76. Today it renders every source.
- **Compose document**: Exists, `render.render`. Gains the outputs mount.
- **Secret source and variants**: New, a small port beside `runtime.py`. The plain file needs no
  copy: compose reads it in place with `--env-file`. The decrypt variant writes into
  `copy.directory / secrets/`, the folder `runtime.env_files` already reads.
- **Name check**: New. It reads `${VAR}` from rendered blocks, so it runs after assembly.
- **Wave plan, job outputs**: New, in `commands.cmd_up`.
- **Service listing**: Reshape, `cmd_ls`.
- **Reference page**: Reshape, revised (see the revision log). It moves to
  `base-library/library/skills/ostler/ostler-cli/references/stack.md` and stays the one
  reference, because agents in every repo load it and it must stand alone. The CLI skill's
  `SKILL.md` lists it beside `command-interface.md`. Three links follow it: the operations row
  of `ostler-okf/SKILL.md`, the `environment` node type and `qa-harness-reference.md`.
  `ostler/README.md` keeps an example and links to it.
- **Schema**: New, `ostler env schema`.

### What the existing system has that the design lacks

- Fixtures and `default-fixtures`: a concept the design kept implicitly under Service. No change.
- Leases and reclaim of a dead run's copy: part of Teardown. No change.
- The runbook path in `ostler/ostler/qa/runbook.py:599`, which keeps a runbook's own stack for a
  lease-less call: out of scope (A8).

### Lookups

- `env ls --json`: no caller in this repo. Only the CLI prints it. `copies` stays as a key
  anyway, and `services` is added.
- Dockerfile outside the context: unresolved, A3. First thing slice 3 checks.
- `up --wait` on a subset: unresolved, A5. First thing slice 6 checks.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A book with `secrets: <saddlebag env>` | its `${VAR}` values at boot | nothing in this repo | unmeasured, client repos (A4) | `ostler env check` names the old key and the migration, and no value is lost |
| A book using `render:` | its helper files in the copy | `test_environments.py` | the test passes | the same files land under `files:`; `check` names the old key |
| A QA run under a lease | its own copy through `leases.up` | `workflows/tests/test_kit_qa_stack_copy.py` | passes | passes unchanged |
| An agent's context | no secret value, ever | saddlebag's no-stdout design | holds | holds through the decrypt variant, by a test that fails if a value appears in any output |
| Bring-up time of a stack with no job outputs | one compose `up` | nothing | one invocation | still one invocation |
| Templates with literal `{{` in non-`.j2` files | n/a, every `render:` file is Jinja | nothing | n/a | copied untouched |

## 6. Slices

Each slice updates the reference page and the schema with it.

1. **`ls` says what each service is.** `about` required, `cmd_ls` lists services with copies and
   addresses. The reference moves into the CLI skill in the same slice, since every later slice
   edits it there. Done when `ostler env ls` on the test catalog prints every service with its
   about, a service with no about fails `check`, and no link points at the old reference path.
2. **One secret source.** Stack root with `secrets: {file}` or `{decrypt}`, name check, saddlebag
   removed from `up`. Done when a test stack boots from a `.env`, the same stack boots from a
   decrypt command, a missing name fails `check` by name, and no test output contains a value.
3. **Files and the checkout build.** `files:` with `.j2` rendering and plain copy, `env_dir`,
   `ops_dir`. Done when a service builds from `context: {{ repo }}` with a Dockerfile placed in
   the copy, honouring its `.dockerignore`, and a non-`.j2` file holding `{{ }}` lands unchanged.
4. **Book-level needs.** Done when `up web` on a catalog where web names `api` at the book level
   brings every api service up first, and a cycle across books is refused.
5. **`ops/` layout.** The loader reads `<book>/ops/stack.yml` and the root file, and refuses the
   old place with a message naming the new one. Done when the reference page, the README example
   and the scaffolds use `ops/`.
6. **Job outputs.** `outputs:`, the mount, `STABLEMATE_OUTPUTS`, the wave plan. Done when a
   busybox job writes `UPLOAD_BUCKET=x`, a service needing it boots with that value, a job that
   omits a declared name fails `up` by name, and a stack with no outputs still runs one `up`.

## 7. Assumptions

1. **A "vault file" is an encrypted file committed in the repo that the team's own CLI decrypts
   to dotenv** (sops, ansible-vault, age). Decided: the `decrypt:` command variant. Basis: none
   beyond the request's words. If wrong (a HashiCorp Vault server, or saddlebag's keyring): Part 3
   gains a variant. Nothing else moves.
2. **Infrastructure a local copy provisions lives inside the copy** (an emulator, a local
   bucket), so dropping the copy's volumes cleans it. Decided: no destroy hook on `down`. Basis:
   copies are local and disposable by design. If wrong: Job gains an `on-down` command, run in
   its container before compose down.
3. **Compose accepts a Dockerfile outside the build context, and BuildKit reads
   `<Dockerfile>.dockerignore` beside it.** Decided: `files:` places the Dockerfile in the copy.
   Basis: Docker documentation, from memory. Verify first, in minutes. If wrong: the Dockerfile
   is passed with `dockerfile_inline:` from the rendered file, and the ignore file goes to the
   context root.
4. **The books still using `secrets: <saddlebag env>` and `render:` are few and live in the
   user's client repos.** Decided: a hard switch with a `check` message, no compatibility
   reader. Basis: none in this repo. If wrong: slice 2 and 3 keep a reader for one release.
5. **`compose up --wait <subset>` leaves the rest of the project alone.** Decided: waves are two
   invocations on one project. Basis: none. If wrong: the first wave renders a project of its
   own.
6. **One secret source serves every book.** Decided: `secrets:` only in the stack root. Basis:
   "a single .env file". If wrong: invariant 7 goes, and each book names its source.
7. **The `ops/` folder should hold the stack file, not only its templates.** Decided: move it.
   Basis: the request to define `ops/`'s purpose, and the reference example already keeps
   templates in `ops/services/`. If wrong: slice 5 is dropped, nothing else changes.
8. **Runbook pages keep their own bring-up recipe for now.** Decided: untouched. Basis: the QA
   runner still selects runbooks when no lease is held. If wrong: a later note retires the
   runbook recipe in favour of `stack.yml`.
