---
type: cli
slug: cli
title: ostler
---
# ostler

Ostler is the planning CLI: one `ostler` binary dispatching to subcommands that read and write the
managed markdown tree (backlog, milestones, epics, features) under a repo root.

- binary: ostler
- code: ostler/ostler/cli.py::main@f9cefee57bce
- detail: [Planning identities](concepts/planning-identities.md)

## Commands


### ostler-create-backlog-item
- usage: ostler create backlog-item SUMMARY --repo REPO --area AREA [--pattern PATTERN] [--symbol SYMBOL ...] [--id ID] [--body TEXT] [--prefix PREFIX] [--json] — files a record a person wrote on the debt register, on the `backlogs/` shelf of the artifacts dir, which no git repository tracks; with no `--id` it allocates a fresh full id, so two calls with the same summary each get their own record
- flags:
  - --repo and --area (the workspace repository and the area folder the record is shelved under, each one lowercase kebab segment), --pattern (the fix the record calls for, `untriaged` when omitted), --symbol (a code symbol the record names, repeatable), --id (file under this id instead of an allocated one), --body (the record's text below the summary), --prefix (override the derived id prefix), --json (print `{ok, id, name, message}` instead of a line of text)
- args: summary — the record's one-line listing text
- exits: 0 when the record is filed; 1 with the reason when it is refused, for a taken id, a repo or area that is not one lowercase kebab segment, or an empty or multi-line summary
- run: invoke(argv=["-C", "plan-scratch", "create", "backlog-item", "a sample backlog item", "--repo", "api-service", "--area", "billing", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "plan-scratch/art"})
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="id", matches="^TST-[0-9A-HJKMNP-TV-Z]{26}$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with records X-1 and X-2 on its register
- code: ostler/ostler/register.py::file_person@c830fda449ae
- code: ostler/ostler/ids.py::allocate@523968666eae
- detail: [Planning identities](concepts/planning-identities.md)
- tests: ostler/tests/test_register_person.py::test_create_backlog_item_files_the_same_record

### ostler-artifact-list
- usage: ostler artifact list [--json] — prints the built-in artifact kinds
  (plan-context, qa-evidence, backlog-items), each as a `{kind, filename, description}` line, or as
  one indented JSON array with --json
- flags:
  - --json (print the whole array as one indented JSON document instead of one compact line per kind)
- exits: 0 — listing the built-in kinds reads only the code-registered kind table, so this command
  never fails
- run: invoke(argv=["artifact", "list", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[2].kind", equals="backlog-items")
- verify: json_path(path="[2].filename", equals="backlog-items.json")
- fixture: none, because the kind registry is fixed in code, not read from any spec dir
- code: ostler/ostler/artifact/run.py::list_kinds@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::KINDS@ec25eeaddd5f
- code: ostler/ostler/artifact/__init__.py::__all__@d177bd2861a0
- code: ostler/ostler/cli.py::_cmd_artifact@f9cefee57bce

### ostler-artifact-scaffold
- usage: ostler artifact scaffold KIND --spec PATH [--force] — writes KIND's JSON skeleton to
  `<spec-dir>/<kind>.json`, creating the spec directory first, and prints
  `scaffolded <kind> -> <path>`; refuses to overwrite an existing artifact file unless --force is
  given
- flags:
  - --spec (the spec directory: absolute as given, else resolved under the specs root if it exists there, else under the repo root), --force (overwrite an existing artifact file instead of erroring)
- args: kind — one of the names `ostler artifact list` reports (plan-context, qa-evidence,
  backlog-items)
- exits: 0 — a kind name from the registry, scaffolded at a path that does not yet hold that kind's
  file, writes the skeleton and prints the destination
- run: invoke(argv=["artifact", "scaffold", "backlog-items", "--spec", "cli-book-scaffold-spec"])
- verify: exit_status(code=0)
- verify: contents(subject="cli-book-scaffold-spec/backlog-items.json", matches="(?s)^\\[\\]\\n$")
- fixture: [cli scenario arrangement](fixtures/cli-scenario-arrangement.md) — seeds an empty
  cli-book-scaffold-spec/ under the repo root, so --spec resolves there instead of under the specs
  root, and the directory does not yet hold the kind's file
- code: ostler/ostler/artifact/run.py::scaffold@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::ArtifactKind@ec25eeaddd5f
- code: ostler/ostler/path.py::resolve_spec_arg@6a1acd1702fd
- code: ostler/ostler/cli.py::_cmd_artifact@f9cefee57bce

### ostler-artifact-scaffold-unknown-kind
- usage: ostler artifact scaffold KIND --spec PATH — rejects a KIND outside the registry before
  touching the spec directory
- args: kind — a name not among those `ostler artifact list` reports
- exits: 1 — a kind name outside the registry is rejected before any file is touched
- run: invoke(argv=["artifact", "scaffold", "bogus-kind", "--spec", "artifact-scaffold-error-spec"])
- verify: exit_status(code=1)
- fixture: none, because an unknown kind name fails before the spec directory is read or written
- code: ostler/ostler/artifact/run.py::scaffold@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::ArtifactKind@ec25eeaddd5f
- code: ostler/ostler/cli.py::_cmd_artifact@f9cefee57bce

### ostler-artifact-vet
- usage: ostler artifact vet KIND --spec PATH [--json] — validates `<spec-dir>/<kind>.json` against
  KIND's contract and prints either `{kind}: clean` or `{kind}: problems` followed by one `  - ` line
  per problem (or the whole outcome as one JSON object with --json)
- flags:
  - --spec (same resolution as `ostler artifact scaffold`), --json (print `{kind, path, status, problems?, error?}` as one indented JSON object)
- args: kind — one of the names `ostler artifact list` reports
- exits: 1 — vetting a kind whose artifact file does not yet exist at the spec dir fails with
  `error: <path> does not exist — scaffold it first`, rather than treating an absent file as clean
- run: invoke(argv=["artifact", "vet", "backlog-items", "--spec", "artifact-vet-missing-spec"])
- verify: exit_status(code=1)
- fixture: none, because the claim is that a never-scaffolded spec dir is rejected
- code: ostler/ostler/artifact/run.py::vet@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::_backlog_items_vet@ec25eeaddd5f
- code: ostler/ostler/cli.py::_cmd_artifact@f9cefee57bce

### ostler-env-schema
- usage: ostler env schema — prints the JSON Schema of a book's `ops/stack.yml`
- exits: 0 — printing the schema reads only the code-declared key table, so this command never fails
- run: invoke(argv=["env", "schema"])
- verify: exit_status(code=0)
- verify: json_path(path=".$schema", equals="https://json-schema.org/draft/2020-12/schema")
- fixture: none, because the schema is built from the code-declared key table, not read from any
  stack.yml
- code: ostler/ostler/environments/spec.py::schema@ece1017c2482
- code: ostler/ostler/environments/spec.py::KEYS@ece1017c2482
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17

### ostler-vet
- usage: ostler vet SCREENSHOT --manifest PATH (--cdp-url URL | --regions PATH) --story STORY
  [--state STATE] [--iou-threshold FLOAT] [--write] [--json] — registers a manifest's documented
  elements against a scanned-regions file by rectangle overlap, and prints the match as one
  `VetReport` JSON object with --json, or a dry-run file diff otherwise; writes nothing to disk
  unless --write is given
- flags:
  - --manifest (the JSON list of documented elements to register), --cdp-url (a live Chrome
    DevTools Protocol URL to scan instead of replaying a regions file; mutually exclusive with
    --regions), --regions (a previously scanned regions JSON file to replay instead of a live
    scan), --story (the id of the story the vet report is filed under), --state (the label this
    render is recorded under; default "default"), --iou-threshold (the minimum
    intersection-over-union for a documented element and a region to count as the same thing;
    default 0.5), --write (apply the planned file writes instead of only printing their diff),
    --json (print the whole `VetReport` as one indented JSON object instead of the dry-run diff
    text)
- args: screenshot — the rendered page's screenshot path; read only to crop matched/unlabeled
  regions out of, so a path that does not exist still produces a report
- exits: 1 — at least one documented element is missing, or at least one scanned region is
  unexpected or unlabeled; exits 0 only when every documented, visible element matches a region
- run: invoke(argv=["-C", "edit-scratch", "vet", "nonexistent.png", "--manifest", "vet-manifest.json", "--regions", "vet-regions.json", "--story", "TST-01M585PFWZZXH4Y6KNMH1VK58H", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="summary.status", equals="disagreements")
- verify: json_path(path="summary.matchedCount", equals=2)
- verify: json_path(path="summary.missingCount", equals=1)
- verify: json_path(path="summary.unexpectedCount", equals=1)
- verify: json_path(path="summary.unlabeledCount", equals=1)
- verify: json_path(path="matched[0].iou", matches="^0\\.512")
- verify: json_path(path="matched[1].iou", equals=0.5)
- verify: json_path(path="missing[0].selector", equals=".below-threshold-dom")
- verify: json_path(path="unexpected[0].selectors[0]", equals=".below-threshold-region")
- verify: json_path(path="unlabeled[0].selectors[0]", equals=".stray-region")
- fixture: [vet manifest and regions](fixtures/vet-manifest-and-regions.md) — writes the
  `--manifest` and `--regions` files this run reads; the three element/region pairs it seeds sit
  far enough apart that each pair's overlap is independent of the others, one pair at exactly the
  default 0.5 threshold, one just above it, one just below it, plus a fourth region with no
  accessible role and no matching element
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) — gives `--story` a real id to
  resolve against, by way of its story `sx`
- code: ostler/ostler/vet/__init__.py::__all__@2e20aecf0259
- code: ostler/ostler/vet/run.py::run_vet@43917e56aea7
- code: ostler/ostler/vet/geometry.py::BBox@a6d2ef1e40b6
- code: ostler/ostler/vet/geometry.py::iou@a6d2ef1e40b6
- code: ostler/ostler/vet/manifest.py::load_manifest@4b54d3b4e9ea
- code: ostler/ostler/vet/manifest.py::DomElement@4b54d3b4e9ea
- code: ostler/ostler/vet/regions.py::merge@94a27f0a4ad7
- code: ostler/ostler/vet/regions.py::RegionBox@94a27f0a4ad7
- code: ostler/ostler/vet/register.py::match@4813a8dbde2b
- code: ostler/ostler/vet/crop.py::maybe_crop@116a8b739a47
- code: ostler/ostler/vet/report.py::build_report@30d577ca0ec9
- code: ostler/ostler/vet/writes.py::VetFileWrite@d000fa666d75
- code: ostler/ostler/vet/writes.py::VetPlan@d000fa666d75
- code: ostler/ostler/cli.py::_cmd_vet@f9cefee57bce
- detail: [Vetting a rendered screen](concepts/vetting-a-rendered-screen.md)

### ostler-vet-cdp
- usage: ostler vet SCREENSHOT --manifest PATH --cdp-url URL --story STORY [--json] — scans a live
  page over Chrome DevTools Protocol instead of replaying a `--regions` file, and reports the scan
  itself failing as a `VetOutcome` error rather than a report
- flags:
  - --cdp-url (a live Chrome DevTools Protocol URL to scan; mutually exclusive with --regions)
- args: none beyond the screenshot already covered by [ostler-vet](#ostler-vet)
- exits: 1 — a CDP URL nothing answers fails the scan before any manifest is even read, so the
  run's error names the URL, not a missing manifest
- run: invoke(argv=["-C", "edit-scratch", "vet", "nonexistent.png", "--manifest", "vet-manifest.json", "--cdp-url", "http://127.0.0.1:1/", "--story", "TST-01M585PFWZZXH4Y6KNMH1VK58H", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="error", matches="^CDP scan of 'http://127\\.0\\.0\\.1:1/' failed: ")
- fixture: [vet manifest and regions](fixtures/vet-manifest-and-regions.md) — seeds the
  `--manifest` file this run reads; its `--regions` file goes unread on this path
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) — gives `--story` a real id to
  resolve against, by way of its story `sx`
- code: ostler/ostler/vet/cdp.py::connect_and_scan@77027b587d70
- code: ostler/ostler/qa/harness/ostler_qa_scan.py::SCAN_JS@71decdf2a5c3
- detail: [Vetting a rendered screen](concepts/vetting-a-rendered-screen.md)

### ostler-env-check
- usage: ostler env check [--json] — reads every book's `ops/stack.yml`, prints `N services in M
  books fit together` when none of them disagree, and otherwise prints one `- ` line per problem
  (or the whole outcome as one JSON object with --json)
- flags:
  - --json (print `{ok, books, services, errors}` as one indented JSON object)
- exits: 1 — a book whose `ops/stack.yml` does not parse to a mapping with a `services:` key is
  reported by name and path, rather than being skipped silently
- run: invoke(argv=["-C", "env-check-scratch", "env", "check", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="errors[0]", matches="^docs/services/env-check-fixture/ops/stack\\.yml: is not a mapping with a `services:` key$")
- fixture: [cli scenario arrangement](fixtures/cli-scenario-arrangement.md) — creates a scratch repo
  whose book's ops/stack.yml is a YAML list instead of a mapping, so no other scenario reads it
- code: ostler/ostler/environments/spec.py::load@ece1017c2482
- code: ostler/ostler/environments/spec.py::_read_book@ece1017c2482
- code: ostler/ostler/environments/commands.py::cmd_check@05411233ab32
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17
