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

- binary: ostler
- code: ostler/ostler/cli.py::main@03c9e301c36d

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
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/tools.py::catalog@6a440152c6e4

### ostler-qa-context
- usage: ostler qa context --base BASE --spec SPEC [--head HEAD] [--features-root DIR]
  [--source-root SURFACE=PATH] [--story-file FILE] [--json]: maps the code that changed since BASE to
  the book nodes that own it and writes the context packet into the spec directory
- flags:
  - --base (the revision to compare from)
  - --head (the revision to compare to; default is the working tree)
  - --spec (the spec directory or story id the packet is written into)
  - --features-root (the book directory, when the config does not name it)
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
- code: ostler/ostler/qa/book_index.py::captures_by_node@34df4e06f504
- code: ostler/ostler/qa/captures.py::CaptureDecl/parse_bullet@248120ebb77f
- code: ostler/ostler/qa/compile.py::annotate_deferred_obligations@0cb8f8e9d882
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@003bdbe757de
- code: ostler/ostler/qa/compile_http.py::api_scenarios@7b561de0b90a
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@8075f6afe6b5
- code: ostler/ostler/qa/compile_maestro.py::device_state_walks@f72e453ea0dc
- code: ostler/ostler/qa/compile_moves.py::move_walks@357b72ed93c7
- code: ostler/ostler/qa/compile_page.py::page_scenarios@86e11d4ad1cb
- code: ostler/ostler/qa/compile_support.py::on_href@d73966f66e36
- code: ostler/ostler/qa/context.py::book_files@ae1dfb851ad2
- code: ostler/ostler/qa/dispatch.py::claim_driver@d44c624e5b21
- code: ostler/ostler/qa/fixture_provides.py::closure@9053b42918c0
- code: ostler/ostler/qa/fixtures.py::parse_bullet@a4b91574f193
- code: ostler/ostler/qa/grounding_health.py::resolve_groundings@da8a0b8f6c0f
- code: ostler/ostler/qa/journey_steps.py::journey_steps@0794ea6c9659
- code: ostler/ostler/qa/navigation.py::navigation_rows@9f36c4d2fcd8
- code: ostler/ostler/qa/obligation.py::obligation_of@f238f8b8f458
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@c6e8278e4f37
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/owners.py::book_relative@de26fdbd12b7
- code: ostler/ostler/qa/packet.py::packet_of@b67a80c9a6e3
- code: ostler/ostler/qa/plan_source.py::arrangement_of@fa73bba2be06
- code: ostler/ostler/qa/runbook.py::bullet_text@b0b4e9245916
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
- code: ostler/ostler/qa/context.py::cmd_context_validate@ae1dfb851ad2
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c

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
- code: ostler/ostler/qa/context.py::select_obligations@ae1dfb851ad2

### ostler-qa-compile-plan
- usage: ostler qa compile-plan --spec SPEC [--out PATH] [--story STORY] [--run-id ID] [--base-url
  URL] [--json]: compiles a qa_plan.py skeleton from the packet, reading no source
- flags:
  - --out (write the plan here; an existing file is never overwritten, and without it the plan is
    printed)
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
- code: ostler/ostler/qa/book_index.py::captures_by_node@34df4e06f504
- code: ostler/ostler/qa/compile.py::cmd_compile_plan@0cb8f8e9d882
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@003bdbe757de
- code: ostler/ostler/qa/compile_http.py::api_scenarios@7b561de0b90a
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@8075f6afe6b5
- code: ostler/ostler/qa/compile_maestro.py::device_state_walks@f72e453ea0dc
- code: ostler/ostler/qa/compile_moves.py::move_walks@357b72ed93c7
- code: ostler/ostler/qa/compile_page.py::page_scenarios@86e11d4ad1cb
- code: ostler/ostler/qa/compile_support.py::on_href@d73966f66e36
- code: ostler/ostler/qa/dispatch.py::claim_driver@d44c624e5b21
- code: ostler/ostler/qa/navigation.py::navigation_rows@9f36c4d2fcd8
- code: ostler/ostler/qa/obligation.py::obligation_of@f238f8b8f458
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/packet.py::packet_of@b67a80c9a6e3
- code: ostler/ostler/qa/plan_source.py::arrangement_of@fa73bba2be06

### ostler-qa-lint
- usage: ostler qa lint PLAN [--json]: lints a qa_plan.py by its syntax tree, without importing or
  running it
- exits: 0 when the plan passes the lint
- run: invoke(argv=["-C", "qa-scratch", "qa", "lint", "art/specs/s1/qa_plan.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/lint.py::cmd_lint@7072719988f2
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c

### ostler-qa-validate
- usage: ostler qa validate PLAN [--spec SPEC] [--json]: loads a qa_plan.py against its packet and
  the book without running it
- exits: 0 when the plan is valid
- run: invoke(argv=["-C", "qa-scratch", "qa", "validate", "art/specs/s1/qa_plan.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/context.py::book_files@ae1dfb851ad2
- code: ostler/ostler/qa/harness_host.py::default_interpreter@9aece567e098
- code: ostler/ostler/qa/lint.py::cmd_lint@7072719988f2
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/plan.py::load_plan@08754cc7e1a2
- code: ostler/ostler/qa/run.py::cmd_validate@166d32882457
- code: ostler/ostler/qa/tools.py::catalog@6a440152c6e4
- code: ostler/ostler/untyped.py::is_mapping@c964a61d4a94

### ostler-qa-run
- usage: ostler qa run PLAN [--spec SPEC] [--stop-on-fail] [--scenario ID] [--out-dir LABEL]
  [--json]: runs a qa_plan.py in batch mode and writes the run ledger, the manifest, the evidence file
  and the report
- flags:
  - --stop-on-fail (stop at the first failed scenario)
  - --scenario (run only this scenario, repeatable)
  - --out-dir (make the run a dry run into the spec's qa/LABEL directory, writing no evidence file)
  - --json (print the closing record)
- exits: 0 when every scenario passes
- run: invoke(argv=["-C", "qa-scratch", "qa", "run", "art/specs/s1/qa_plan.py", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- verify: json_path(path="pass_count", equals=1)
- verify: json_path(path="fail_count", equals=0)
- verify: contents(subject="qa-scratch/art/specs/s1/qa/qa-run.ndjson", matches="\"kind\": \"session_stop\"")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-evidence.json", matches="okf:docs/features/demo/cli.md#demo-greet:exits:1")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/attribution.py::signatures@038d2f518503
- code: ostler/ostler/qa/book_fixtures.py::resolved@360f74516536
- code: ostler/ostler/qa/context.py::book_files@ae1dfb851ad2
- code: ostler/ostler/qa/drivers.py::create_driver@6720c03c3ec2
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@b2b27057b604
- code: ostler/ostler/qa/fixtures.py::declared@a4b91574f193
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa@5e8e1ba15732
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::UrlReading@753b30ac1b84
- code: ostler/ostler/qa/harness/ostler_qa_checkout.py::copy_checkout@d2d64738e2dc
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::DocumentReading@c7b9f1b585d5
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::AttributeReading@4618eb430b45
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::template_pattern@883f5792bbcd
- code: ostler/ostler/qa/harness/ostler_qa_files.py::Tree@1c99efa3cc05
- code: ostler/ostler/qa/harness/ostler_qa_lap.py::LapRecord@908f9ce8d348
- code: ostler/ostler/qa/harness/ostler_qa_paths.py::Wild@e595be5f2bf9
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@1d4c7f6bc802
- code: ostler/ostler/qa/harness/ostler_qa_settle.py::Settled@6216d3ba5cda
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::paste@02ae85efa7b7
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@a84e0c3ae95a
- code: ostler/ostler/qa/harness_host.py::capped_argv@9aece567e098
- code: ostler/ostler/qa/lint.py::cmd_lint@7072719988f2
- code: ostler/ostler/qa/manifest.py::RunManifest@2d00c95675d5
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/plan.py::check_runtime_requirements@08754cc7e1a2
- code: ostler/ostler/qa/repeats.py::pages@1074839ca608
- code: ostler/ostler/qa/report.py::build_report@0d73d5c319d1
- code: ostler/ostler/qa/run.py::cmd_run@166d32882457
- code: ostler/ostler/qa/run_log.py::failing_log_refs@b2d1c68eaf42
- code: ostler/ostler/qa/sensitivity.py::trial@bc503e0d42f7
- code: ostler/ostler/qa/session.py::_check_scenario_verdict@b93f384fd8c4
- code: ostler/ostler/qa/tools.py::catalog@6a440152c6e4
- code: ostler/ostler/qa/v2.py::run_plan@fd118c311bc5
- code: ostler/ostler/qa/verdict.py::judge@667c513201c2
- code: ostler/ostler/untyped.py::is_mapping@c964a61d4a94
- code: ostler/ostler/util.py::is_mapping@6c753ed2df8c
- detail: [Running and reporting a QA run](concepts/running-and-reporting-a-qa-run.md)

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
- code: ostler/ostler/qa/harness/ostler_qa.py::_open_browser@5e8e1ba15732
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::Browser@27603f8dc6e3
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
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@b2b27057b604
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@1d4c7f6bc802
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@a84e0c3ae95a
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/report.py::build_report@0d73d5c319d1
- code: ostler/ostler/qa/run.py::cmd_report@166d32882457
- code: ostler/ostler/qa/run_log.py::read_records@b2d1c68eaf42
- code: ostler/ostler/qa/sensitivity.py::trial@bc503e0d42f7
- code: ostler/ostler/util.py::is_mapping@6c753ed2df8c

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
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@b2b27057b604
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@1d4c7f6bc802
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@a84e0c3ae95a
- code: ostler/ostler/qa/run_log.py::read_records@b2d1c68eaf42
- code: ostler/ostler/qa/sensitivity.py::trial@bc503e0d42f7
- code: ostler/ostler/util.py::is_mapping@6c753ed2df8c

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
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@1d4c7f6bc802
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@a84e0c3ae95a
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/sensitivity.py::cmd_sensitivity@bc503e0d42f7

### ostler-qa-replay
- usage: ostler qa replay --spec SPEC: prints a shell script that replays the steps of a run from
  its log
- exits: 0 when the run ledger exists
- run: invoke(argv=["-C", "qa-scratch", "qa", "replay", "--spec", "s1"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^#!/usr/bin/env bash")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/run.py::cmd_replay@166d32882457
- code: ostler/ostler/qa/run_log.py::read_records@b2d1c68eaf42

### ostler-qa-frames
- usage: ostler qa frames --spec SPEC (--step STEP | --at SECONDS) [--target T] [--around SECONDS]
  [--fps N] [--out-dir LABEL]: writes the frames of a run's recording around a step
- exits: 1 when the run has no recording
- run: invoke(argv=["-C", "qa-scratch", "qa", "frames", "--spec", "s1", "--step", "greet-exits-zero"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=1)
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@b2b27057b604
- code: ostler/ostler/qa/frames.py::extract_frames@fb07c5fc799e
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@1d4c7f6bc802
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@a84e0c3ae95a
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/report.py::build_report@0d73d5c319d1
- code: ostler/ostler/qa/run.py::cmd_frames@166d32882457
- code: ostler/ostler/qa/run_log.py::read_records@b2d1c68eaf42
- code: ostler/ostler/qa/sensitivity.py::trial@bc503e0d42f7
- code: ostler/ostler/util.py::is_mapping@6c753ed2df8c

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
- code: ostler/ostler/qa/clean.py::cmd_clean@96a5108c86d5
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c

### ostler-qa-fixtures-migrate
- usage: ostler qa fixtures migrate --in DIR [--json]: writes the fixture nodes a repo declared
  under `qa: {fixtures:}` into DIR
- exits: 0 when the repo declares no fixtures or the migration writes
- run: invoke(argv=["-C", "qa-scratch", "qa", "fixtures", "migrate", "--in", "migrated", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/fixtures.py::cmd_migrate@a4b91574f193
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/tools.py::qa_block@6a440152c6e4

### ostler-qa-stack-up
- usage: ostler qa stack up: brings the stack the book declares to ready
- exits: 0 when the book declares no stack (nothing to bring up) or the stack comes up
- run: invoke(argv=["-C", "qa-scratch", "qa", "stack", "up"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="declares no runbook")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/environments/leases.py::books_near@479047ef621a
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/runbook.py::cmd_stack_up@b0b4e9245916

### ostler-qa-stack-down
- usage: ostler qa stack down: runs the teardown recipe the book declares
- exits: 0 when the book declares no stack (nothing to tear down) or the teardown runs
- run: invoke(argv=["-C", "qa-scratch", "qa", "stack", "down"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="declares no runbook")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/environments/leases.py::books_near@479047ef621a
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/runbook.py::cmd_stack_down@b0b4e9245916

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
- code: ostler/ostler/qa/runbook.py::cmd_stack_up@b0b4e9245916
- code: ostler/ostler/qa/stack.py::ensure_stack@10c66bad65f4
- code: ostler/ostler/qa/stack.py::boot_app@10c66bad65f4
- code: ostler/ostler/qa/stack.py::_boot_without_probe@10c66bad65f4
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
- code: ostler/ostler/qa/manifest.py::RunManifest@2d00c95675d5
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/run.py::cmd_start@166d32882457
- code: ostler/ostler/qa/session.py::_now@b93f384fd8c4

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
- code: ostler/ostler/qa/manifest.py::RunManifest@2d00c95675d5
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/run.py::cmd_step@166d32882457
- code: ostler/ostler/qa/session.py::_expand@b93f384fd8c4

### ostler-qa-assert
- usage: ostler qa assert --id ID --label LABEL --check CHECK --spec SPEC [KEY=VALUE ...]: runs a
  named check and records PASS or FAIL
- exits: 0 when the check passes
- run: invoke(argv=["-C", "qa-scratch", "qa", "assert", "--id", "b", "--label", "hi was said", "--check", "field_equal", "--spec", "s2", "actual=1", "expected=1"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^assert 'b': PASS$")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/manifest.py::RunManifest@2d00c95675d5
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/run.py::cmd_assert@166d32882457
- code: ostler/ostler/qa/session.py::_check_field_equal@b93f384fd8c4

### ostler-qa-stop
- usage: ostler qa stop --spec SPEC: kills the session's daemons and writes its closing record
- exits: 0 when every assertion passed
- run: invoke(argv=["-C", "qa-scratch", "qa", "stop", "--spec", "s2"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: stdout(matches="^QA run complete: PASS")
- verify: contents(subject="qa-scratch/art/specs/s2/qa/qa-run.ndjson", matches="session_stop")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/manifest.py::RunManifest@2d00c95675d5
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/run.py::cmd_stop@166d32882457
- code: ostler/ostler/qa/session.py::_now@b93f384fd8c4
