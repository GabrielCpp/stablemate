# One typed schema for the two shared config files

Disclosure: before this note was written, its author had read the home-config book page, the
`farrier-setup` skill's config section, the names of the functions in core's config module,
and one raw-dict read in farrier's doctor. Decisions they carried are listed as claims in 1b.

## 1. Problem

A person or an agent setting up stablemate on a client machine has only the installed tools.
They cannot learn which settings the machine's config file and the repository's manifest
accept, so they guess key names, copy stale examples, and find out a key was wrong only when a
run misbehaves.

Done looks like this. One command from one installed tool prints every setting of both files,
each with its type, its default, its meaning and an example. Every setting any tool reads
appears in that output, and nothing appears that no tool reads. A tool that starts reading a
new setting cannot ship until the setting is declared, so the output never falls behind.

Out of scope:

- Where the human user guide is hosted. The guide links to the command's output and to the
  book pages generated from the same source.
- Settings that live in other files: groom's `prices.toml`, run state, a benchmark's task
  file, a workflow's prompt files. (revised, R6)
- The keys a library skill or prompt reads from the manifest's free template values. Those
  belong to the library that reads them. (revised, R2)
- A generic command that sets any key. The existing commands that set fixed keys stay.
- Environment variables that do not stand in for a setting of these two files.
- Settings that no tool reads today stop being documented. A client file that still carries
  one gets a warning on load. It is not rewritten. (revised, R5)

## 1b. Claims

1. The schema lives in the shared core package that every tool vendors. (this conversation)
2. Farrier is the one tool that prints the reference. (this conversation)
3. Every tool reads its settings through typed models. (this conversation)
4. The machine config carries a version. A tool refuses to write a newer file, migrates an
   older file forward on its first write, and never fails to read a newer file. (INSTALL.md)
5. Writes merge key by key, so any key is legal in the machine config. (home-config book page)
6. The manifest's `workflow:` section is read by the workflows package, not by farrier.
   (farrier-setup skill)
7. The typed models are pydantic models. (this conversation, the author's suggestion)

## 2. Parts and concepts

### Level 1: parts

1. **Declaration**: what settings exist in each file, their types, defaults, meanings and
   examples. Owns the truth about the files. Never knows which tool reads a setting or how a
   file is found. Hands a read-only catalog to every other part.
2. **Loading**: turning a file on disk into a validated, typed value a tool consumes. Owns
   finding, parsing and validating. Never knows what a tool does with a setting. Hands the
   typed value to the tool.
3. **Editing**: changing a setting of either file on disk. Owns the change and keeping every
   other setting intact. Never knows how the value will be used. (revised, R3)
4. **Evolution**: keeping tools of different releases able to share one file. Owns the file's
   older shapes and the steps that lift them to the current one. Acts at two moments: on
   every load, it lifts in memory; on every edit, it lifts on disk or refuses.
5. **Reference**: turning the catalog into text a reader can use. Owns the rendering. Never
   knows how a file is loaded.

Flow: Declaration is consulted by the other four. A tool asks Loading for a file; Loading
parses it, asks Evolution to lift it, and validates it against Declaration. A setting change
goes through Editing, which asks Evolution whether this release may write the file and
validates the new value against Declaration. The reference command asks Reference to render
Declaration.

In plain words: one list says what each file may contain. Reading a file checks it against
that list. Changing a file checks the change against it. Old and new releases agree through
the steps that lift an old file to the current shape. The help text is printed from the same
list.

### Level 2: concepts

**Declaration**

| Concept | Owns | Never knows |
|---|---|---|
| Setting | one key: its path, type, default, meaning, example, and the environment variable that stands in for it | which tool reads it |
| Table | a fixed group of settings under one heading | the file it sits in |
| Named table | a group the user names freely (a profile, a service, a workspace), all members sharing one shape | the names a user picks |
| Free values | a map whose keys belong to someone outside the tools, such as the library's template values | which keys the library reads |
| Document | the whole shape of one file: its tables and top-level settings | the file's location and syntax |

Free values is new (R2). The keys inside it that a tool reads are Settings of their own.

**Loading**

| Concept | Owns | Never knows |
|---|---|---|
| Location | where a file is, including the environment override and the legacy names it once had | the file's contents |
| Parse | text in one syntax (TOML, YAML) to an untyped tree | the Document |
| Validation | an untyped tree to a typed Document, with errors that name the key path | where the tree came from |
| Stray key report | a warning for each key the Document does not declare, naming the closest declared key | whether the key came from a newer release or a typo |
| Last good value | the Document a long-running process keeps when a re-read fails validation | why the file changed |

Location gained legacy names (R7). Last good value is new (R8).

**Editing**

| Concept | Owns | Never knows |
|---|---|---|
| Setting change | one key path set to a value checked against its Setting | the other keys in the file |
| Preserving write | putting the change on disk with every other key, comment and unknown key left as found, in the file's own syntax | what the change means |

**Evolution**

| Concept | Owns | Never knows |
|---|---|---|
| Schema version | the number the machine config carries and the number this release understands | the settings themselves |
| Migration step | lifting one older shape to the next, a version step or an alias fold | any other step |
| Write guard | refusing an edit to a machine config newer than this release | how the edit was requested |

The manifest has no Schema version. Its older shapes are aliases, folded on every load (R4).

**Reference**

| Concept | Owns | Never knows |
|---|---|---|
| Rendering | one Document as markdown: every setting with type, default, meaning, example, environment variable, and each legacy alias it still accepts | how files are loaded or edited |

The untyped tree is a value private to Loading, Editing and Evolution. No consumer receives it.

## 3. Invariants

- **I1. A tool reads a setting only through the typed Document.** Owner: Loading, which never
  returns the untyped tree. Upheld by the type checkers, which reject an attribute the
  Document does not declare. This is what makes the reference exhaustive.
- **I2. Every Setting has a meaning and an example.** Owner: Declaration, checked by a test
  that walks every Document.
- **I3. The reference lists exactly the declared settings.** Owner: Rendering, which is
  generated from the Documents and holds no list of its own.
- **I4. Loading a file a newer release wrote never fails.** Owner: Evolution. Unknown keys go
  to the Stray key report.
- **I5. A release never writes a machine config newer than it understands.** Owner: Write
  guard.
- **I6. An edit changes one key and nothing else on disk.** Owner: Preserving write.
- **I7. An edit to an undeclared key is refused.** Owner: Setting change.
- **I8. A process that loaded a valid file never dies on a later re-read.** Owner: Last good
  value. A re-read that fails validation logs the key path and keeps the last good Document.
  (R8)
- **I9. One key has one type.** Owner: Declaration. A key two readers want in two shapes is
  split, and the older shape becomes a Migration step. (R5)

## 4. Forces and patterns

Forces:

- **F1. Settings grow.** Each workflow adds keys over time. Declaring one must be one edit in
  one place.
- **F2. Tools release independently and share one file per user.** Reads must tolerate a
  newer shape. Writes must refuse it.
- **F3. Two syntaxes.** The machine config is TOML and the manifest is YAML. Parsing and
  writing vary by file, validation does not.
- **F4. Two static type checkers gate the repo.** A setting read must be an attribute the
  checkers can see, not a string lookup.
- **F5. The reference must work offline from an installed tool.** It is generated at run
  time from what the tool carries.
- **F6. Tests point a tool at a scratch file.** Location must be overridable.
- **F7. Users name some tables.** Profiles, services and workspaces are keyed by names the
  user picks.
- **F8. Runs last days and re-read the machine config per step.** (R8)

Patterns:

- **Between parts: one shared catalog, one value handed along.** Declaration is a read-only
  catalog. Loading hands one typed Document to the tool (F1, F4).
- **Declaration: data models that carry their own documentation.** Each Setting is a typed
  field whose description and example sit on the field, so the type and the reference come
  from one line (F1, F4, F5). Named tables are maps from a user name to one model (F7). Free
  values are a map of any value, with the tool-read keys as declared fields beside it.
- **Loading: one plain function per file.** Two files, two syntaxes, no role: a manifest is
  never swapped for a machine config (F3).
- **Evolution: an ordered list of migration steps per file.** Adding a version or an alias
  adds one step (F2).
- **Reference: one function that walks a Document.** One output format, markdown, readable in
  a terminal and pasteable into a page.
- **Last good value: a cache keyed by the file's modification time.** (F8)
- **Location: the existing environment override.** (F6)

Claims:

- Claim 1 is re-derived from F1 and F2: one place that every release carries.
- Claim 2 is re-derived from F5 and the one-tool requirement (A1).
- Claim 3 is re-derived from F4 and I1.
- Claim 4 is re-derived from F2 for the machine config. The manifest gets the migration half
  without a version (R4).
- Claim 5 is rejected in part. Unknown keys found on disk are kept (I6) and reported (I4).
  An edit to an undeclared key is refused (I7).
- Claim 6 is rejected as a boundary. Which tool reads `workflow:` does not change where its
  settings are declared.
- Claim 7 is re-derived: pydantic models carry a description and examples per field, emit a
  JSON schema, and report validation errors by key path. Four tools already depend on it
  (A3).

## 5. Mapping onto the existing system

Revision log:

- **R1.** Lookups L1 to L6 resolved below.
- **R2.** Section 2 Declaration gains Free values; section 1 puts library template keys out
  of scope. The manifest's `template` and `repo` maps carry keys the library's Jinja reads,
  which no code inventory can list.
- **R3.** Section 2 Editing covers both files. Farrier's eject edits the manifest
  (`farrier/farrier/yaml_edit.py`), genesis writes it (`workflows/.../coder/genesis/nodes.py:187`),
  and paddock line-edits it (`paddock/paddock/replay.py:199`).
- **R4.** Section 2 Evolution: the manifest carries no version. Its older shapes are aliases
  read in place today: `vars`, `workflow.services`, `workflow.lint`,
  `workflow.github_token_env`, the list form of `agents`, the string forms of
  `includeReadme`.
- **R5.** Section 3 adds I9, section 1 drops dead keys. Top-level `prompts` is a list to
  farrier (`farrier/farrier/sources.py:229`) and a role map to the coder
  (`workflows/.../coder/shared/roles.py:106`). Six keys are documented or written but read by
  nothing: `workflow.storyCoder.*`, `exclude.scaffolds`, top-level `workflows` (written by
  genesis at `nodes.py:213`), `workflow.repoUrl`, `workflow.branch`, `workflow.agentsDir`,
  `workflow.envPassthrough`.
- **R6.** Section 1 puts `prices.toml` out of scope. Groom keeps prices in its own file
  (`groom/groom/prices.py:69`).
- **R7.** Section 2 Location gains legacy names. Ostler and the research workflow accept
  `ostler.yml`, `ostler.yaml` and `.agents.yml` as the manifest.
- **R8.** Section 2 adds Last good value, section 3 adds I8, section 4 adds F8. Workhorse
  re-reads the machine config on every node through `resolve_power`, and the workflow
  readers degrade silently on a bad shape today. Strict validation would turn a mid-run typo
  into a dead run.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Declaration | **New** | `core/stablemate_core/schema/` with one module per Document. Nothing declares either file today. |
| Loading | **Reshape** | Machine config: `core/stablemate_core/config.py::load_config` returns a raw dict (`:150`). Manifest: nine loaders across farrier, workflows and ostler, each a `yaml.safe_load` plus `.get` chains. |
| Editing | **Reshape** | Machine config: `write_config_key` / `write_config_section` (`config.py:179`, `:198`) rewrite the file with `tomli-w`, which drops comments. Manifest: `farrier/farrier/yaml_edit.py` keeps formatting. |
| Evolution | **Exists** for the machine config (`CONFIG_VERSION = 2`, `_MIGRATIONS`, `config.py:30`, `:380`). **New** for the manifest. |
| Reference | **New** | `farrier config reference`, beside `config show` in `farrier/farrier/cli.py`. The renderer lives in core so any tool could print it. |

### Concepts

| Concept | Verdict | Finding |
|---|---|---|
| Setting, Table, Named table | New | Defaults and env overrides are scattered today: `resolve_artifacts_dir` (`config.py:455`), `resolve_default_cli` (`profiles.py:828`), groom's env-before-config order (`groom/groom/settings.py:52`). Each moves onto its field. |
| Free values | New | `template`, `vars`, `repo.<other>`. Declared fields beside it: `repo.name`, `repo.base_branch`, `template.backend_layer_name`, `template.mobile_layer_name`. |
| Document | New | Two: machine config, manifest. |
| Location | Exists | `config_path()` (`config.py:84`) for the machine config. The manifest has no shared locator. Farrier's `find_agents_config` (`cli.py:323`) and ostler's fallback list become one function in core. |
| Parse | Exists | `tomllib` and `yaml.safe_load`. Core gains a YAML dependency, which farrier, workflows and ostler already have. |
| Validation | New | |
| Stray key report | New | No unknown-key detection exists for either file. |
| Last good value | Reshape | Groom already caches by mtime (`groom/groom/attend.py:45`). That cache moves into Loading. |
| Setting change | Reshape | Six `write_*` helpers, three without a caller (`write_artifacts_dir`, `write_paddock_dir`, `write_default_cli`). The callerless three are deleted. |
| Preserving write | Reshape | Machine config writes drop comments today (L5). Core switches the machine-config writer to `tomlkit`. |
| Schema version, Migration step, Write guard | Exists | For the machine config. A `ConfigVersionError` during an in-memory lift is swallowed and the raw shape returned (`config.py:158`). With typed models that unmigrated shape fails validation. Decision: the swallow is removed and the error raised on load, since a migration that fails is a file the release cannot read. |
| Rendering | New | |

### Readers that move onto the Documents

Machine config, by key group:

- Directory keys (`library_dir`, `base_dir`, `stablemate_dir`, `worktree_dir`,
  `artifacts_dir`, `paddock_dir`, `ostler_index_dir`): core `discovery.py`, core `resolve_*`,
  `farrier/farrier/layers.py:107`, `workhorse/workhorse/cli/run.py:272`,
  `ostler/ostler/index.py:215`.
- `workspaces.<name>`: core `resolve_workspace` and its siblings. All callers already go
  through core.
- `default_cli`, `profiles.<name>.*`, `cli.<backend>.env`: core `profiles.py`. A finding: a
  run with no profile passes the whole config to `resolve_power`, which looks for top-level
  `powers` that no v2 file has, so no model mapping applies. The typed Document has no
  top-level `powers`, so this path becomes a type error and is fixed in slice 2.
- `groom.attend.*`, `groom.dispatch.*`: `groom/groom/settings.py`.
- `user_library.<harness>.*`, `user_library.template`: `farrier/farrier/user_library.py`,
  `farrier/farrier/outputs.py:454`. Same selection keys as the manifest, so one Table model
  serves both Documents.
- `qa_tools.<name>.*`: `ostler/ostler/qa/tools.py:69`.
- `saddlebag.backend`: `saddlebag/saddlebag/preference.py:36` opens the file with `tomllib`
  and does not use core. Saddlebag is added to the vendor destinations (A4).

Manifest, by owner of the code that reads it today:

- Farrier: `agents`, `packs`, `skills`, `prompts`, `roots`, `scaffolds`, `exclude.*`,
  `template`, `vars`, `repo.*`, `localInstructions[].*`, `hooks.manager`, `services`, `lint`.
- Workflows: `services.<name>.{path,lint,test,type}`, `lint`, `repo.name`,
  `repo.base_branch`, `template.*_layer_name`, `program`, `workflow.githubTokenEnv`,
  `workflow.prompts`, `organization` (presence only).
- Ostler: `organization.{name,profile}`, `qa.tools`, `qa.fixtures.<name>.*`,
  `qa.recordingExemptTargets` (read today from `ostler.yml` only).

The existing partial checks (`Agents`, `LocalInstruction`, `parse_scaffold_ids`, hook
manager names, `qa.fixtures`) become field validators on the Document and are deleted where
they live now.

### What the existing system has that the design lacks

- `farrier config --profile` flattens one profile for display (`cli.py:260`). Not waste: it
  shows resolved values, which the reference does not. It stays and reads the Document.
- Legacy per-tool config files merged when no unified file exists (`config.py:166`). A
  Location concern, kept.
- Paddock builds scratch machine configs by deep-merging dicts
  (`paddock/paddock/homeconfig.py`). It keeps writing dicts, and its output is loaded through
  the Document like any other file, so a malformed scratch config fails at the start of a
  trial.
- The vendor guard (`make check-vendor`, `scripts/vendor_core.py`). It keeps every tool linked
  to the one copy of the Documents, which is what lets one tool speak for all.

### Claims against the existing system

| Claim | Existing system | Design |
|---|---|---|
| 1 | Core is vendored into farrier, workhorse, ostler, paddock. Groom and workflows import workhorse's copy. Saddlebag has none. | Follows, with saddlebag added. |
| 2 | Farrier owns `config show` and `init`. | Follows. |
| 3 | No typed model for either file. | Follows. |
| 4 | Follows, with the in-memory swallow above. | Follows, swallow removed. |
| 5 | Follows: any key may be written. | Rejected in part. |
| 6 | Follows. | Rejected as a boundary. |
| 7 | Pydantic in ostler, groom, workhorse, paddock. Not in core, farrier, saddlebag. | Follows (A3). |

### Lookups

- **L1.** Farrier ships in the umbrella install and is the tool that renders skills into a
  client. A client that installs workhorse alone has no farrier. Assumption A1.
- **L2.** Pydantic is a dependency of four of the seven tools. Core, farrier and saddlebag
  gain it.
- **L3.** Inventoried: every key path of both files, grouped by reader above.
- **L4.** The manifest has no version. R4.
- **L5.** Machine-config writes go through `tomli-w` and drop comments.
- **L6.** Farrier, genesis and paddock write the manifest. R3.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| An unattended run | survives every config re-read, including a bad edit mid-run | nothing | 0 failures from config reads, since readers degrade silently | 0 failures; a bad re-read logs the key path and keeps the last good value (I8) |
| A user's current machine config | resolves to the same values in every tool | nothing | measured in slice 1 on the maintainer's own file: every resolver's output | identical output from every `resolve_*` and every reader, old and new |
| A client repo's current manifest | renders the same skills, hooks and local instructions | farrier's drift check | measured in slice 3: `farrier install --repo` on this repo produces no diff | still no diff |
| A client manifest carrying a dead key | loads silently | nothing | silent | loads, with one warning per dead key; no failure |
| A per-node config read in workhorse | costs little | nothing | not measured (A9) | under 50 ms per load on a 200-line file |
| A fresh `farrier` install | installs with its current dependency set | nothing | farrier's current wheel deps | adds pydantic and PyYAML only |
| A paddock trial | starts with its scratch config | nothing | trials start | trials start; a malformed scratch config now fails at trial start, which is the intended change |
| A comment a user wrote in `config.toml` | lost on the next write | nothing | lost | kept (I6), a gain |

The unattended-run row becomes I8 with an owner. The dead-key row is listed out of scope in
section 1.

## 6. Slices

1. **Machine config, end to end.** Declaration of the full machine-config Document,
   Loading that returns it, Rendering, and `farrier config reference` printing the
   machine-config section. Core's own `resolve_*` and `discovery.py` read the Document. The
   farrier-setup skill's config section names the command and fixes the stale path. The
   home-config book page points at the command.
   Done when: an agent with only an installed farrier learns every machine-config key from
   one command; the resolver comparison row in 5b is identical on the maintainer's file;
   load cost is measured and under its limit.
2. **Machine config, every reader.** Farrier, workhorse, groom, ostler, paddock read the
   Document; saddlebag vendors core; the raw-dict accessors (`load_config`, `read_config`,
   `get_config_value`) leave the public API. Last good value replaces groom's cache.
   Machine-config writes switch to `tomlkit`. The profile-less run path is fixed.
   Done when: a grep for the raw accessors outside Loading finds nothing; `make lint` passes;
   every 5b row re-measured.
3. **Manifest, farrier's keys.** Declaration of the manifest Document, Location with legacy
   names, alias folds, Stray key report, farrier's readers and writers on the Document, the
   reference command's manifest section, the partial checks folded in.
   Done when: `farrier install --repo` on this repo and on a scratch client produces no diff;
   the reference lists every manifest key farrier reads.
4. **Manifest, the workflows' and ostler's keys.** Their readers move onto the Document. The
   top-level `prompts` role map folds into `workflow.prompts`. Genesis stops writing
   `workflows:`. Dead keys leave the example files and the book.
   Done when: the reference lists every manifest key the inventory found and no dead one; a coder dry run and
   `ostler qa` read the same values as before on this repo.
5. **The docs point at one source.** The farrier and workflows book pages for both files
   describe the keys through the reference; INSTALL.md and the farrier README point at the
   command; the user guide gets a configuration page holding the rendered reference.
   Done when: no page in the tree lists a key the reference lacks.

Docs that a slice's change touches are updated in that slice. Slice 5 carries only the
pages no earlier slice touched.

## 7. Assumptions

- **A1.** Farrier is installed on every machine where either file is set up.
  Decided: the reference command lives in farrier.
  Basis: farrier renders the skills an agent reads, and the umbrella install includes it.
  If wrong: claim 2, Reference's home. The renderer is in core, so moving the command is one
  entry point.
- **A2.** A validation error on a fresh load may stop the command that loaded it.
  Decided: fresh loads fail with the key path; only re-reads in a running process keep the
  last good value (I8).
  Basis: none. Today a bad shape degrades silently.
  If wrong: Validation, I8.
- **A3.** Core may depend on pydantic.
  Decided: the Documents are pydantic models.
  Basis: ostler, groom, workhorse and paddock depend on it already.
  If wrong: Declaration's pattern, claim 7.
- **A4.** Saddlebag may vendor core.
  Decided: saddlebag reads `saddlebag.backend` through the Document.
  Basis: saddlebag reads one key today and adds platformdirs, tomlkit, PyYAML and pydantic.
  If wrong: saddlebag keeps its own read, I1 has one exception, and a test asserts it reads
  the declared key.
- **A5.** No client relies on a key no tool reads.
  Decided: dead keys are dropped from the reference and warned about on load.
  Basis: the inventory found no reader.
  If wrong: section 1 out of scope, Stray key report.
- **A6.** No client uses top-level `prompts` as a role map.
  Decided: the role map lives only at `workflow.prompts`, with a fold for the old place.
  Basis: a map there already breaks farrier, which reads a list.
  If wrong: I9 for `prompts`.
- **A7.** `ostler.yml`, `ostler.yaml` and `.agents.yml` are legacy names for the manifest,
  and `qa.recordingExemptTargets` belongs in it.
  Decided: Location reads them as fallbacks.
  Basis: ostler takes the first of these files that holds a mapping.
  If wrong: a third Document.
- **A8.** Library template keys are the library's to document.
  Decided: Free values.
  Basis: the keys are read by Jinja in library content, not by code.
  If wrong: Declaration grows a library-declared extension point.
- **A9.** Validating a 200-line file costs under 50 ms.
  Decided: workhorse keeps re-reading per node, behind the mtime cache.
  Basis: none. Measured in slice 1.
  If wrong: Last good value also skips validation when the mtime is unchanged.
- **A10.** The manifest needs no version.
  Decided: alias folds only.
  Basis: every older shape found is an alias, and no tool writes the manifest wholesale.
  If wrong: Evolution gains a manifest Schema version and Write guard.
