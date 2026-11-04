---
type: cli
slug: qa
title: ostler qa commands
---
# ostler qa commands

The commands that turn a change into evidence: they build a packet of the book nodes a change
touches, compile and run a QA plan against it, and report what the run proved. Every claim here runs
in a scratch repository whose spec directories and tool table sit under the checkout, so no run
writes to the artifacts directory of the person who runs the book. The claims run in the order they
are written, because each later command reads what an earlier one wrote.

A run can depend on an outside system the book does not start, which a `resource` page describes.
A fixture step with `on:` acts on that resource. A step with `request:` sends one HTTP request to
the resource's `base:`, and a step with `run:` runs a command whose binary and secrets the harness
checks first. The first step or observation on a resource runs its probe, once per harness process.
A resource that does not answer gaps every claim that needs it as `gapped: <resource name> absent`.

A `kind: borrow` step takes something from the resource in order, like any other step. When it
succeeds, the harness registers the `kind: release` steps that follow it and records a
`release-pending` event for each. The harness sends the releases when the scenario ends, last
borrowed first, whether the scenario passed, failed or errored, and records a `release` event for
each with its `ok` and `detail`. A release that fails never stops the others and fails a scenario
that had passed. When a scenario times out, the parent runner sends each release that has a
`release-pending` event and no `release` event, after it stops the scenario's servers.

A claim that carries `observe: @<resource>.<observation>` has the harness read that observation.
The plan compiles it to `qa.observe(resource, observation, within=N, until=[...])`, and each
`verify:` row held on it to a `qa.verify` on the document the read returned. The harness records an
`observe` event for each read with the polls it took. A secret's value stays in the harness's own
environment, and no plan, transcript or event carries it. See
[describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md).

- binary: ostler
- code: ostler/ostler/cli.py::main@e56ee756ce4b

## Commands

### ostler-qa-tools-list
- usage: ostler qa tools list: prints each QA tool the repo opts into, the command it runs and
  whether that command resolves
- exits: 0 always
- run: invoke(argv=["-C", "qa-scratch", "qa", "tools", "list"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^demo \\(echo\\) \\[ok\\]")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/tools.py::catalog@b9ec43ce49bb

### ostler-qa-context
- usage: ostler qa context (--base BASE | --refresh) --spec SPEC [--head HEAD] [--services-root DIR]
  [--source-root SURFACE=PATH] [--story-file FILE] [--json]: maps the code that changed since BASE to
  the book nodes that own it and writes the context packet into the spec directory. The packet
  records the inputs that built it, and `--refresh` rebuilds it from them
- flags:
  - --base (the revision to compare from)
  - --refresh (rebuild from the inputs the packet on disk recorded; refused when it records none)
  - --head (the revision to compare to; default is the working tree)
  - --spec (the spec directory or story id the packet is written into)
  - --services-root (the book directory, when the config does not name it)
  - --source-root (an OKF surface mapped to its production source directory, repeatable)
  - --story-file (a story page whose acceptance criteria join the packet)
  - --json (print the packet instead of the two file names)
- args: none
- exits: 0 when the packet is built and no health finding is an error
- run: invoke(argv=["-C", "qa-scratch", "qa", "context", "--base", "HEAD", "--spec", "s1", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="available", equals=true)
- verify: json_path(path="status", equals="passed")
- verify: json_path(path="changedCode[0].path", equals="src/demo.py")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-okf-context.json", matches="\"base\": \"HEAD\"")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-okf-context.json", matches="\"name\": \"greeting\"")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-okf-context.json", matches="\"from\": \"stdout\"")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-okf-context.json", matches="names no source")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/book_index.py::captures_by_node@3461b43ebf37
- code: ostler/ostler/qa/captures.py::CaptureDecl/parse_bullet@248120ebb77f
- code: ostler/ostler/qa/compile.py::annotate_deferred_obligations@3cf23080c032
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@cf06f3c86495
- code: ostler/ostler/qa/compile_http.py::api_scenarios@4dc4547ef07a
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@89108ef98180
- code: ostler/ostler/qa/compile_maestro.py::device_state_walks@f685bb9e79dc
- code: ostler/ostler/qa/compile_moves.py::move_walks@c8463448d0ef
- code: ostler/ostler/qa/compile_page.py::page_scenarios@fba8efba86f1
- code: ostler/ostler/qa/compile_support.py::on_href@dd9915c8e301
- code: ostler/ostler/qa/context.py::book_files@223cd8ab76ef
- code: ostler/ostler/qa/dispatch.py::claim_driver@7c6d2995f39d
- code: ostler/ostler/qa/fixture_provides.py::closure@bdd1adf2dc1d
- code: ostler/ostler/qa/fixtures.py::parse_bullet@69e389c684f7
- code: ostler/ostler/qa/grounding_health.py::resolve_groundings@add94afddb88
- code: ostler/ostler/qa/journey_steps.py::journey_steps@348541ac03a5
- code: ostler/ostler/qa/navigation.py::navigation_rows@4df2fbcf356b
- code: ostler/ostler/qa/obligation.py::obligation_of@b558662c2212
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@1d8c8dad0e49
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/owners.py::book_relative@8f7d64d535b5
- code: ostler/ostler/qa/packet.py::packet_of@6f73061e9eed
- code: ostler/ostler/qa/plan_source.py::arrangement_of@9dcaf902b06a
- code: ostler/ostler/markdown.py::bullet_text@44779fe79ecf
- detail: [Compiling a book into a QA plan](concepts/compiling-a-book-into-a-qa-plan.md)

### ostler-qa-context-validate
- usage: ostler qa context-validate --spec SPEC [--json]: checks that a spec's context packet parses
  and that its book digests still match the book
- exits: 0 when the packet is valid
- run: invoke(argv=["-C", "qa-scratch", "qa", "context-validate", "--spec", "s1"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^Context is valid\\.$")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/context.py::cmd_context_validate@f2fc5672fe0a
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3

### ostler-qa-context-show
- usage: ostler qa context-show --spec SPEC [--required | --context-only] [--node SUBSTR] [--kind
  KIND] [--offset N] [--limit N] [--ids-only] [--no-locators] [--json]: prints a filtered, paged slice
  of a built packet
- exits: 0 when the packet exists
- run: invoke(argv=["-C", "qa-scratch", "qa", "context-show", "--spec", "s1", "--ids-only"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="demo-greet:exits:1")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/context.py::select_obligations@08db3c322d31

### ostler-qa-compile-plan
- usage: ostler qa compile-plan --spec SPEC [--out PATH] [--replace] [--select ID ...] [--cover AC=ID[,ID...] ...]
  [--story STORY] [--run-id ID] [--base-url URL] [--json]: compiles a qa_plan.py skeleton from the packet,
  reading no source
- flags:
  - --out (write the plan here; an existing file is overwritten only with --replace, and without
    it the plan is printed)
  - --replace (let --out overwrite an existing plan)
  - --select (repeatable; keep only the owed obligations whose id or book node is the given id, and
    report no gap on the others; with none given every owed obligation compiles; an id that matches
    no owed obligation or book node is an error naming it)
  - --cover (repeatable; AC=ID[,ID...] names an acceptance criterion the packet lists and the owed
    obligations or book nodes that prove it, matched as --select matches; every compiled check
    whose covers list names one of those obligations, and the scenario holding it, then covers AC
    too, without a duplicate. A criterion the packet does not list, an id that matches no owed
    obligation or book node, an id that compiled to no check in this plan, such as book debt or an
    obligation --select dropped, and an argument that is not AC=ID[,ID...] are each an error
    naming the value, and nothing is written. A criterion no obligation proves is left for a
    scenario written by hand)
  - --story (the story name for the plan; default is the one the packet was built for)
  - --run-id (the run id for the plan)
  - --base-url (the entry URL for a surface whose book states none)
  - --json (print the counts and the gaps)
- exits: 0 when the plan compiles
- run: invoke(argv=["-C", "qa-scratch", "qa", "compile-plan", "--spec", "s1", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="owed", equals=3)
- verify: json_path(path="declared", equals=1)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/book_index.py::captures_by_node@3461b43ebf37
- code: ostler/ostler/qa/compile.py::cmd_compile_plan@a0f77ff012ce
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@cf06f3c86495
- code: ostler/ostler/qa/compile_grpc.py::grpc_scenarios@af1d3303dcf6
- code: ostler/ostler/qa/compile_http.py::api_scenarios@4dc4547ef07a
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@89108ef98180
- code: ostler/ostler/qa/compile_maestro.py::device_state_walks@f685bb9e79dc
- code: ostler/ostler/qa/compile_moves.py::move_walks@c8463448d0ef
- code: ostler/ostler/qa/compile_page.py::page_scenarios@fba8efba86f1
- code: ostler/ostler/qa/compile_support.py::on_href@dd9915c8e301
- code: ostler/ostler/qa/dispatch.py::claim_driver@7c6d2995f39d
- code: ostler/ostler/qa/navigation.py::navigation_rows@4df2fbcf356b
- code: ostler/ostler/qa/obligation.py::obligation_of@b558662c2212
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/packet.py::packet_of@6f73061e9eed
- code: ostler/ostler/qa/plan_source.py::arrangement_of@9dcaf902b06a

### ostler-qa-context-web-journey
- usage: ostler qa context --base BASE --spec SPEC --json, BASE naming a commit before a screen's
  interaction and state both changed production code on a `driver: web` surface
- exits: 0 when the packet is built and no health finding is an error
- run: invoke(argv=["-C", "qa-web-scratch", "qa", "context", "--base", "HEAD", "--spec", "s1", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-web-scratch/art", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="available", equals=true)
- verify: json_path(path="status", equals="passed")
- verify: json_path(path="changedCode[0].path", equals="src/frontend.py")
- fixture: [qa web journey repo](fixtures/qa-web-journey-repo.md)
- code: ostler/ostler/qa/context.py::book_files@223cd8ab76ef
- code: ostler/ostler/qa/dispatch.py::claim_driver@7c6d2995f39d

### ostler-qa-compile-plan-web-journey
- usage: ostler qa compile-plan --spec SPEC --out PATH --json, SPEC naming a packet whose flow
  walks a screen's interaction into a screen state on a `driver: web` surface
- exits: 0 when the plan compiles
- run: invoke(argv=["-C", "qa-web-scratch", "qa", "compile-plan", "--spec", "s1", "--out", "art/specs/s1/qa_plan_compiled.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-web-scratch/art", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- verify: contents(subject="qa-web-scratch/art/specs/s1/qa_plan_compiled.py", matches="qa\\.by_role\\(\"button\", name=\"Open\"\\)")
- verify: contents(subject="qa-web-scratch/art/specs/s1/qa_plan_compiled.py", matches="qa\\.settle\\(")
- fixture: [qa web journey repo](fixtures/qa-web-journey-repo.md)
- code: ostler/ostler/qa/compile_playwright.py::web_walk@40e28af83b41
- code: ostler/ostler/qa/compile_playwright.py::page_locator_expr@4c0ccf24b4c5
- code: ostler/ostler/qa/compile_stops.py::resolve_state@0cd0a5f9d41c
- code: ostler/ostler/qa/compile_stops.py::perceivable@f6ae21c4fb9c

### ostler-qa-lint
- usage: ostler qa lint PLAN [--json]: lints a qa_plan.py by its syntax tree, without importing or
  running it
- exits: 0 when the plan passes the lint
- run: invoke(argv=["-C", "qa-scratch", "qa", "lint", "art/specs/s1/qa_plan.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/lint.py::cmd_lint@73eb987731e2
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3

### ostler-qa-validate
- usage: ostler qa validate PLAN [--spec SPEC] [--json]: loads a qa_plan.py against its packet and
  the book without running it
- exits: 0 when the plan is valid
- run: invoke(argv=["-C", "qa-scratch", "qa", "validate", "art/specs/s1/qa_plan.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/context.py::book_files@223cd8ab76ef
- code: ostler/ostler/qa/harness_host.py::default_interpreter@21a724f89dbc
- code: ostler/ostler/qa/lint.py::cmd_lint@73eb987731e2
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/plan.py::load_plan@9193a20ade5e
- code: ostler/ostler/qa/run.py::cmd_validate@652387ec658e
- code: ostler/ostler/qa/tools.py::catalog@b9ec43ce49bb
- code: ostler/ostler/untyped.py::is_mapping@58e488a40df0

### ostler-qa-run
- usage: ostler qa run PLAN [--spec SPEC] [--stop-on-fail] [--scenario ID] [--out-dir LABEL]
  [--json]: runs a qa_plan.py in batch mode and writes the run ledger, the manifest, the evidence file
  and the report
- flags:
  - --stop-on-fail (stop at the first failed scenario)
  - --scenario (run only this scenario, repeatable)
  - --out-dir (make the run a dry run into the spec's qa/LABEL directory, which the run empties first and a later scored run leaves standing, writing no evidence file and not requiring every acceptance criterion to be covered)
  - --json (print the closing record)
- exits: 0 when every scenario passes
- run: invoke(argv=["-C", "qa-scratch", "qa", "run", "art/specs/s1/qa_plan.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- verify: json_path(path="pass_count", equals=1)
- verify: json_path(path="fail_count", equals=0)
- verify: contents(subject="qa-scratch/art/specs/s1/qa/qa-run.ndjson", matches="\"kind\": \"session_stop\"")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-evidence.json", matches="okf:docs/services/demo/cli.md#demo-greet:exits:1")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/attribution.py::signatures@390aad61dd56
- code: ostler/ostler/qa/book_fixtures.py::resolved@c2327c8c4431
- code: ostler/ostler/qa/context.py::book_files@223cd8ab76ef
- code: ostler/ostler/qa/drivers.py::create_driver@7652064de163
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@5273008138a7
- code: ostler/ostler/qa/fixtures.py::declared@218d9dd9d05a
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa@0acb4f76fed5
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::UrlReading@585f67d0e3dd
- code: ostler/ostler/qa/harness/ostler_qa_resources.py::ResourceDesk@953f0758c607
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa._owe_releases@fd9f865aeb69
- code: ostler/ostler/qa/drivers.py::run_pending_releases@cb8a7479c6bb
- code: ostler/ostler/qa/compile_observe.py::observation_lines@8db0acb37755
- code: ostler/ostler/qa/harness/ostler_qa_files.py::checkout_files@5623e81e6b53
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::DocumentReading@ce936961df83
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::AttributeReading@6e8baa69531a
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::template_pattern@4db02c4ffde6
- code: ostler/ostler/qa/harness/ostler_qa_files.py::Tree@efc09001704c
- code: ostler/ostler/qa/harness/ostler_qa_lap.py::LapRecord@4ff057faf213
- code: ostler/ostler/qa/harness/ostler_qa_paths.py::Wild@e6ee42610d2f
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@de55f6adfd9d
- code: ostler/ostler/qa/harness/ostler_qa_settle.py::Settled@fca033cc48d0
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::paste@5278310185fb
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@2e9d64d79798
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@e0792d3a1d2a
- code: ostler/ostler/qa/harness_host.py::capped_argv@bfeef6bc1ff0
- code: ostler/ostler/qa/lint.py::cmd_lint@73eb987731e2
- code: ostler/ostler/qa/manifest.py::RunManifest@39012ecc04b9
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/plan.py::check_runtime_requirements@076b9e807404
- code: ostler/ostler/qa/repeats.py::pages@e916ba15c0c6
- code: ostler/ostler/qa/report.py::build_report@37a6da59f531
- code: ostler/ostler/qa/run.py::cmd_run@a96c0f7685d2
- code: ostler/ostler/qa/run_log.py::failing_log_refs@c597bebbcd3b
- code: ostler/ostler/qa/sensitivity.py::trial@b1443f118000
- code: ostler/ostler/qa/session.py::_check_scenario_verdict@0cee10420eeb
- code: ostler/ostler/qa/tools.py::catalog@b9ec43ce49bb
- code: ostler/ostler/qa/v2.py::run_plan@38eb59b5533e
- code: ostler/ostler/qa/v2.py::_write_evidence@fb3ed4029e77
- code: ostler/ostler/qa/verdict.py::judge@ce8a35c1087f
- code: ostler/ostler/untyped.py::is_mapping@58e488a40df0
- code: ostler/ostler/util.py::is_mapping@12fd23931817
- detail: [Running and reporting a QA run](concepts/running-and-reporting-a-qa-run.md)
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-qa-run-playwright-target
- usage: ostler qa run PLAN --json, PLAN naming a target whose driver is `playwright` — a run
  opens that target's browser before its one scenario's body ever runs, so declaring the driver
  is the whole claim
- args: none
- exits: 1 when the scenario cannot record a passing check, which is every outcome short of a
  real browser opening a real page
- run: invoke(argv=["-C", "qa-scratch", "qa", "run", "art/specs/s1/qa_plan_browser.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- fixture: [qa browser scratch plan](fixtures/qa-browser-scratch-plan.md)
- code: ostler/ostler/qa/harness/ostler_qa.py::_open_browser@a5ccf0c48a8e
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::Browser@3bf83bae53f9
- detail: [Running and reporting a QA run](concepts/running-and-reporting-a-qa-run.md)

### ostler-qa-run-maestro-target
- usage: ostler qa run PLAN --json, PLAN naming a target whose driver is `maestro` — settling a
  screen on that target reads the device through one resident `maestro mcp` session per run, so
  the claim that settles is the whole claim
- args: none
- exits: 1 when the claim that settles raises before any state it names is ever checked, which
  is every outcome short of a real device answering the resident `maestro mcp` session, and with
  no `maestro` on PATH the claim still raises
- run: invoke(argv=["-C", "qa-scratch", "qa", "run", "art/specs/s1/qa_plan_device.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- fixture: [qa maestro scratch plan](fixtures/qa-maestro-scratch-plan.md)
- code: ostler/ostler/qa/harness/ostler_qa.py::settle@e8ab67f257dd
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::DeviceScreen@ddbe7b318607
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::resident_reader@6b312ede8e81
- detail: [Running and reporting a QA run](concepts/running-and-reporting-a-qa-run.md)

### ostler-qa-run-grpc-target
- usage: ostler qa run PLAN --json, PLAN naming a scenario that calls `qa.grpc` on a target with
  no `base_url` — the client needs an address before it can make the call, so the call that needs
  it is the whole claim
- args: none
- exits: 1 when the gRPC client has no address to call
- run: invoke(argv=["-C", "qa-scratch", "qa", "run", "art/specs/s1/qa_plan_grpc.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- fixture: [qa grpc scratch plan](fixtures/qa-grpc-scratch-plan.md)
- code: ostler/ostler/qa/harness/ostler_qa_grpc.py::Grpc@255bd25a056c
- detail: [Running and reporting a QA run](concepts/running-and-reporting-a-qa-run.md)

### ostler-qa-run-scenario-timeout
- usage: ostler qa run PLAN --json, PLAN naming a scenario whose body goes silent past its own
  `timeout=` — the runner kills it and retires any session record the kill leaves mid-start,
  before the run ever reports it failed
- args: none
- exits: 1 when a scenario goes silent past its timeout
- run: invoke(argv=["-C", "qa-scratch", "qa", "run", "art/specs/s1/qa_plan_timeout.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- fixture: [qa timeout scratch plan](fixtures/qa-timeout-scratch-plan.md)
- code: ostler/ostler/qa/drivers.py::LocalLauncher.execute@1479d0383bd8
- code: ostler/ostler/qa/maestro_sessions.py::retire_dead_sessions@f39e8b1a115d
- detail: [Running and reporting a QA run](concepts/running-and-reporting-a-qa-run.md)

### ostler-qa-report
- usage: ostler qa report --spec SPEC [--out-dir LABEL] [--ledger]: renders a run per acceptance
  criterion and obligation, and rewrites the spec's qa-report.md
- flags:
  - --out-dir (render the dry run in the spec's qa/LABEL directory)
  - --ledger (print the flat, time-ordered ledger instead and write nothing)
- exits: 0 when the run ledger exists
- run: invoke(argv=["-C", "qa-scratch", "qa", "report", "--spec", "s1"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="Status \\| \\*\\*PASSED\\*\\*")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-report.md", matches="PASSED")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@5273008138a7
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@de55f6adfd9d
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@2e9d64d79798
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@e0792d3a1d2a
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/report.py::build_report@37a6da59f531
- code: ostler/ostler/qa/run.py::cmd_report@2feca403e7fc
- code: ostler/ostler/qa/run_log.py::read_records@372a3e98dbea
- code: ostler/ostler/qa/sensitivity.py::trial@b1443f118000
- code: ostler/ostler/util.py::is_mapping@12fd23931817

### ostler-qa-evidence-map
- usage: ostler qa evidence-map [--spec SPEC] [--out-dir LABEL] [--status STATUS] [--out PATH]
  [--json]: joins the packet, the run log, the manifest and the evidence file into one status per
  obligation
- flags:
  - --status (print only the obligations with this status)
  - --out (also write the map as JSON here)
  - --out-dir (read the dry run's ledger instead of the scored one)
  - --json (print the map as JSON)
- exits: 1 when an obligation owed evidence is uncovered, contradicted, unproven or insensitive,
  else 0
- run: invoke(argv=["-C", "qa-scratch", "qa", "evidence-map", "--spec", "s1", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- verify: json_path(path="overall", equals="Pass")
- verify: json_path(path="counts.covered", equals=1)
- verify: json_path(path="counts.uncovered", equals=2)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@5273008138a7
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@de55f6adfd9d
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@2e9d64d79798
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@e0792d3a1d2a
- code: ostler/ostler/qa/run_log.py::read_records@372a3e98dbea
- code: ostler/ostler/qa/sensitivity.py::trial@b1443f118000
- code: ostler/ostler/util.py::is_mapping@12fd23931817

### ostler-qa-sensitivity
- usage: ostler qa sensitivity [--node SUBSTR] [--json]: reports which declared checks could have
  gone red
- flags:
  - --node (only claims whose id or book path contains this substring)
  - --json (print the verdict per claim)
- exits: 0 when no declared check is insensitive
- run: invoke(argv=["-C", "qa-scratch", "qa", "sensitivity", "--node", "demo", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="sensitive")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@de55f6adfd9d
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@2e9d64d79798
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@e0792d3a1d2a
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/sensitivity.py::cmd_sensitivity@98b7251d8c51

### ostler-qa-replay
- usage: ostler qa replay --spec SPEC: prints a shell script that replays the steps of a run from
  its log
- exits: 0 when the run ledger exists
- run: invoke(argv=["-C", "qa-scratch", "qa", "replay", "--spec", "s1"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^#!/usr/bin/env bash")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/run.py::cmd_replay@ba435f9598dd
- code: ostler/ostler/qa/run_log.py::read_records@372a3e98dbea

### ostler-qa-frames
- usage: ostler qa frames --spec SPEC (--step STEP | --at SECONDS) [--target T] [--around SECONDS]
  [--fps N] [--out-dir LABEL]: writes the frames of a run's recording around a step
- exits: 1 when the run has no recording
- run: invoke(argv=["-C", "qa-scratch", "qa", "frames", "--spec", "s1", "--step", "greet-exits-zero"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@5273008138a7
- code: ostler/ostler/qa/frames.py::extract_frames@17801d4185c0
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@de55f6adfd9d
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@2e9d64d79798
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@e0792d3a1d2a
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/report.py::build_report@37a6da59f531
- code: ostler/ostler/qa/run.py::cmd_frames@05c250130b2e
- code: ostler/ostler/qa/run_log.py::read_records@372a3e98dbea
- code: ostler/ostler/qa/sensitivity.py::trial@b1443f118000
- code: ostler/ostler/util.py::is_mapping@12fd23931817

### ostler-qa-clean
- usage: ostler qa clean --spec DIR [--yes] [--json]: lists, and with --yes deletes, the legacy qa-*
  scratch directories the old sibling layout left beside a spec
- exits: 0 always
- run: invoke(argv=["-C", "qa-scratch", "qa", "clean", "--spec", "s1", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="removed", equals=false)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/clean.py::cmd_clean@caa5b8678b25
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3

### ostler-qa-fixtures-migrate
- usage: ostler qa fixtures migrate --in DIR [--json]: writes the fixture nodes a repo declared
  under `qa: {fixtures:}` into DIR
- exits: 0 when the repo declares no fixtures or the migration writes
- run: invoke(argv=["-C", "qa-scratch", "qa", "fixtures", "migrate", "--in", "migrated", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/fixtures.py::cmd_migrate@997ab43e30ec
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3

### ostler-qa-stack-up
- usage: ostler qa stack up: brings the stack the book declares to ready
- exits: 0 when the book declares no stack (nothing to bring up) or the stack comes up
- run: invoke(argv=["-C", "qa-scratch", "qa", "stack", "up"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="declares no runbook")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/environments/leases.py::books_near@f3dc55131ce7
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/runbook.py::cmd_stack_up@d2bb4506563e

### ostler-qa-stack-down
- usage: ostler qa stack down: runs the teardown recipe the book declares
- exits: 0 when the book declares no stack (nothing to tear down) or the teardown runs
- run: invoke(argv=["-C", "qa-scratch", "qa", "stack", "down"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="declares no runbook")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/environments/leases.py::books_near@f3dc55131ce7
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/runbook.py::cmd_stack_down@9622f73c5557

### ostler-qa-stack-up-no-probe
- usage: ostler qa stack up: brings a runbook with no `entry-url:` up by its launch command's
  own exit code, since there is no HTTP probe to poll
- exits: 0 when the launch command exits zero (a blocking bring-up handed off to something
  this run does not own)
- run: invoke(argv=["-C", "qa-stack-scratch", "qa", "stack", "up"])
- verify: exit_status(code=0)
- verify: stdout(matches="^stack brought up and healthy at \\(no entry url\\)$")
- fixture: [qa stack no-probe repo](fixtures/qa-stack-no-probe-repo.md) — a runbook whose one
  service step launches `true` and declares no `entry-url:`
- code: ostler/ostler/qa/runbook.py::cmd_stack_up@d2bb4506563e
- code: ostler/ostler/qa/stack.py::ensure_stack@2562d217d605
- code: ostler/ostler/qa/stack.py::boot_app@e08996ac308e
- code: ostler/ostler/qa/stack.py::_boot_without_probe@83391bc598d1
- code: ostler/ostler/_vendor/stablemate_core/clock.py::SYSTEM_CLOCK@99322cfda640

### ostler-qa-start
- usage: ostler qa start RUN_ID --story STORY --spec SPEC [--env KEY=VALUE] [--daemon NAME:ARGV]:
  opens a hand-driven QA session and starts its daemons
- flags:
  - --story (the story the run belongs to)
  - --spec (the spec directory or story id)
  - --env (an environment variable for the session, repeatable)
  - --daemon (a background daemon to start, repeatable)
- exits: 0 when the session opens
- run: invoke(argv=["-C", "qa-scratch", "qa", "start", "run2", "--story", "s2", "--spec", "s2"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^QA session started: run_id=run2, story=s2$")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/manifest.py::RunManifest@39012ecc04b9
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/run.py::cmd_start@2b9497471805
- code: ostler/ostler/qa/session.py::_now@5145bcfad514

### ostler-qa-step
- usage: ostler qa step --id ID --label LABEL --mechanism {live,fixture} --cmd CMD --spec SPEC
  [--timeout S] [--capture KEY=$.path] [--out PATH] [--allow-fail]: runs a command and records it in
  the run log
- exits: 0 when the command exits 0 or --allow-fail is set
- run: invoke(argv=["-C", "qa-scratch", "qa", "step", "--id", "a", "--label", "say hi", "--mechanism", "live", "--cmd", "echo hi", "--spec", "s2"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^step 'a' recorded$")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/manifest.py::RunManifest@39012ecc04b9
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/run.py::cmd_step@b2c4501d858f
- code: ostler/ostler/qa/session.py::_expand@53fc47a524ca

### ostler-qa-assert
- usage: ostler qa assert --id ID --label LABEL --check CHECK --spec SPEC [KEY=VALUE ...]: runs a
  named check and records PASS or FAIL
- exits: 0 when the check passes
- run: invoke(argv=["-C", "qa-scratch", "qa", "assert", "--id", "b", "--label", "hi was said", "--check", "field_equal", "--spec", "s2", "actual=1", "expected=1"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^assert 'b': PASS$")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/manifest.py::RunManifest@39012ecc04b9
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/run.py::cmd_assert@83e8404a4fb5
- code: ostler/ostler/qa/session.py::_check_field_equal@c47e1882a91f

### ostler-qa-stop
- usage: ostler qa stop --spec SPEC: kills the session's daemons and writes its closing record
- exits: 0 when every assertion passed
- run: invoke(argv=["-C", "qa-scratch", "qa", "stop", "--spec", "s2"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^QA run complete: PASS")
- verify: contents(subject="qa-scratch/art/specs/s2/qa/qa-run.ndjson", matches="session_stop")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/manifest.py::RunManifest@39012ecc04b9
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3
- code: ostler/ostler/qa/run.py::cmd_stop@924d13c43e6a
- code: ostler/ostler/qa/session.py::_now@5145bcfad514

### ostler-qa-compile-gaps
- usage: ostler qa compile-gaps --spec SPEC --story STORY --page PAGE [--page PAGE ...] [--json]:
  reports the blocking compile gaps on the pages a story touched
- flags:
  - --spec (directory containing the refreshed qa-okf-context.json)
  - --story (story identity passed to the compiler)
  - --page (required and repeatable; a repo-relative book page whose readiness the caller must prove)
  - --json (print each blocking gap with its code, obligation, message and page)
- exits: 0 when no blocking gap belongs to a given page
- run: invoke(argv=["-C", "qa-scratch", "qa", "compile-gaps", "--spec", "s1", "--story", "demo-story", "--page", "docs/services/demo/api.md", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="gaps", equals="[]")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/readiness.py::cmd_compile_gaps@f2be3f75e500
- detail: [Compiling a book into a QA plan](concepts/compiling-a-book-into-a-qa-plan.md)
- tests: ostler/tests/test_qa_readiness.py::test_the_cli_exposes_the_workflow_verdict

### ostler-qa-assess
- usage: ostler qa assess --book BOOK [--spec SPEC] [--json]: assesses one book
  directory's surface completeness — capability, sensitivity and evidence for every
  owed obligation — without running anything
- flags:
  - --book (the repo-relative services directory to assess; required)
  - --spec (an existing run's spec directory whose recorded evidence the assessment reads)
  - --json (print the verdict as JSON)
- does:
  - builds a whole-book context for the selected directory, compiles it with the real compiler, puts every declared check to synthetic sensitivity trials, joins any recorded run evidence, and exits 1 while the surface is incomplete, reporting one row per owed obligation.
- run: invoke(argv=["-C", "qa-scratch", "qa", "assess", "--book", "docs/services/demo", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- verify: json_path(path="complete", equals=false)
- verify: json_path(path="sensitivity_complete", equals=true)
- verify: json_path(path="required_count", equals=7)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- does:
  - refuses an empty or missing scope with exit 2 before assessing anything.
- run: invoke(argv=["-C", "qa-scratch", "qa", "assess", "--book", "docs/services/missing"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=2)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/assessment.py::cmd_assess@f2c6d797750e
- code: ostler/ostler/qa/assessment.py::contract_fingerprint@7d26a1e09b67
- code: ostler/ostler/qa/gap_owner.py::gap_owner@67cbabc05472
- code: ostler/ostler/qa/gap_owner.py::doctor_finding_owner@cd526e562e3c
- detail: [surface completeness](concepts/surface-completeness.md)
