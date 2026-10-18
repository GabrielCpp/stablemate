---
type: concept
slug: running-and-reporting-a-qa-run
title: Running and reporting a QA run
---
# Running and reporting a QA run

Before a book is compiled at all, `ostler qa context` decides what it owes a proof for.
`context.py`'s `build_context` diffs a repository between a base and head revision
(`_repository_changes`), maps each changed unit to the book nodes that cite it via
`owners.py`'s `map_changes` (scored by `citing_family_counts`/`shared_citations`, so a change
cited by many unrelated nodes degrades to a weaker reason instead of selecting every citing
node), decides which of those nodes are newly in scope (`_selection`, `_close_over_passages`,
`_close_over_state_perceivables`), and mints the `Obligation` dicts (`_minted_obligations`,
`node_obligations`) that [Compiling a book into a QA plan](compiling-a-book-into-a-qa-plan.md)
turns into scenarios; `write_context`/`cmd_context` persist the result as the `ContextPacket`
file a later compile reads, and `cmd_context_validate`/`validate_context` catch an obligation
with no matching book node before it ever reaches a compile. `packet.py`'s `ContextPacket` and
`packet_of` parse that persisted dict back into typed `Passage`/`DataState`/`Move` collections.
`grounding_health.py`'s `resolve_groundings` and `relation_fanout_warnings` check that a node's
declared relations are each grounded in a real citation, flagging source cited by far more nodes
than its content plausibly supports. `references.py`'s `find_references`/`parse_reference`
recognize the `{node-id}`/`{node-id.capture}` template syntax both `context.py`'s obligation
minting and `compile_http.py`'s `read_back` resolve against a capture's producer.
`source_context.py`'s `SourceScope`/`SourceRepository` declare which repository and path
prefixes a context build is allowed to diff in the first place.

Running the compiled plan is `ostler qa run`, `run.py`'s `cmd_run` (alongside `cmd_start`,
`cmd_step`, `cmd_assert`, `cmd_stop`, `cmd_report`, `cmd_replay`, `cmd_validate`). Each opens a
`session.py` `QaSession`, the object a running scenario's `Qa` instance talks to: `_run_command`
executes one subprocess step, `_poll_ready` waits for a declared daemon to answer before a check
runs against it, `_redact` scrubs a declared secret's value out of anything recorded, and
`_execute_check` (dispatching to `_check_http_status`, `_check_field_equal`,
`_check_no_duplicate`, …) is where a check's reading is actually judged. `dispatch.py`'s
`dispatch_target`/`claim_driver` decide, for one obligation, which of the four drivers can
observe it, and `hosts_observation`/`owes_live_evidence` decide whether a node type can be
proven by a QA run at all. `drivers.py`'s `QaDriver` and concrete `PythonDriver` actually run a
compiled `qa_plan.py`'s scenario functions inside a session; `create_driver` picks the
implementation, `Launcher`/`LocalLauncher` start and stop the scenario subprocess, and
`DisplayRecorder`/`DeviceRecorder` capture the video evidence a report later embeds.
`harness_host.py`'s `load_harness_module` is how a running scenario reaches the flat
`ostler_qa*` modules documented in
[Authoring QA scenarios](authoring-qa-scenarios.md) by name; `default_interpreter`/
`harness_argv`/`harness_env` assemble the subprocess command and environment for one scenario,
and `describe` introspects a plan module without running it. `run_log.py`'s `read_records` and
`run_log_tally` read back the JSONL log a session writes, and `passing_log_ref`/
`failing_log_refs` report whether a given assertion id passed on its most recent attempt.

A declarative plan skips code generation entirely. `plan.py`'s `PlanDocument`/`load_plan` read a
plan's v2 JSON form, and `validate_v2`/`check_runtime_requirements` catch drift between what it
asserts and what the book's obligations or background declarations require. `v2.py`'s `run_plan`
is the runtime that executes that `PlanDocument`'s instances directly, writing an evidence record
per instance (`_write_evidence`) and starting or restarting any declared background daemon
(`_start_daemon`, `_restart_daemon`, `_daemon_cwd`) or declared secret (`_secret_value`) the plan
needs along the way. `captures.py`'s `CaptureDecl`/`parse_bullet` parse a `captures:` bullet into
the typed record naming the field a step captures and where the capture is written.

Once a run finishes, three files turn its log into something readable. `report.py`'s
`build_report` assembles one run's report from its log and recordings (`_scenarios`,
`_place_in_recordings`), `render_report` turns that into the markdown a story's QA page embeds,
and `write_report`/`report_path` own where the report file lives. `verdict.py`'s `Verdict` is the
pass/fail/blocked outcome every obligation's check resolves to, and `merged` folds several
scenarios' per-claim verdicts into one map where a failure anywhere always wins over a pass
recorded elsewhere. `outcome.py`'s `QaOutcome` is the single return type every `ostler qa`
subcommand produces, carrying its exit code and message uniformly whether the command succeeded,
found drift, or refused to run. `evidence_map.py`'s `build_evidence_map` cross-references a run's
declared `covers:` claims against its log and published artifacts (`_artifacts_by_scenario`,
`_published`) so a report can point from a claim with no evidence to one that has it, and
`render_evidence_map` prints that filtered to one scenario. `attribution.py`'s `attribute` reads
one `CheckEvidence` (and the `Cause` it carries) into an `Attribution` naming which side — book,
app, or harness — a failure belongs to, and `signatures` groups repeated failures sharing an
`Attribution` into one row instead of one per occurrence. `frames.py`'s `extract_frames` pulls
the video frame window around one failing assertion (`frame_window`, `find_step`) for a report to
embed. `repeats.py`'s `RepeatWatch`/`watch_for` flag an obligation whose `covers:` claims repeat
past a threshold across scenarios, a sign the book is asserting the same fact redundantly.
`manifest.py`'s `RunManifest` is the typed identity (run id, label, book digest) `report.py` and
`evidence_map.py` both read to confirm they describe the same run.

The remaining files are standalone `ostler qa` subcommands that support a run without being part
of its core loop. `sensitivity.py`'s `trial`/`report`/`render`, run by `ostler qa sensitivity`,
synthesize text that would make each of a check's string-matching assertions pass or fail
(`_plan_json_path`, `_plan_omits`, `_plan_printed`, …), catching an assertion pattern loose
enough to pass on nonsense; `cmd_sensitivity` is its CLI entry. `lint.py`'s `PlanLintVisitor`
walks a compiled `qa_plan.py`'s AST for `ostler qa lint`, and `lint_source`/`cmd_lint` report a
settle call missing its required verb (`_settle_verb`) or another structural mistake. `clean.py`'s
`cmd_clean` finds legacy scratch run directories (`legacy_scratch_roots`) left behind by old runs
and deletes them under `--apply`, reporting the disk space each held (`_human`). `tools.py`'s
`catalog`/`opted_in_tools` read a repo's QA tool configuration to resolve which external binaries
a run may shell out to, and `resolved_commands`/`preflight_errors` fail a run early when an
opted-in tool's command cannot be found. `fixtures.py`'s `declared`/`resolved` read a story's
declared external fixtures, `migrate`/`cmd_migrate` upgrade an old-format fixtures file, and
`preflight_errors`/`referenced` check that every required fixture is both declared and used.
`addresses.py`'s `substitute`/`resolve_now` expand a `{name}` placeholder in a declared address
against a resolved address book (`read_book`/`write_book`), and `leased` is the context manager
holding a lease for the duration of one resolution. `stack.py`'s `ensure_stack`/`teardown_stack`
(via `boot_app`/`teardown_app`) bring up and tear down the local app process a run needs when it
is not using `ostler env`, `health_probe` polling a health URL until it answers and `_reap_pgid`
ensuring every child process the stack launched is gone afterward. `runbook.py`'s
`select_runbook`/`select_stack`/`select_server` resolve which book node describes the stack to
bring up near a given path, and `step_command`/`stack_runbooks` turn a runbook node's steps into
the literal shell commands `stack.py`'s boot sequence runs. The package's `__init__.py`
re-exports the public surface of all of the above (`cmd_run`, `cmd_compile_plan`, `cmd_lint`,
`cmd_sensitivity`, `cmd_clean`, `build_report`, `build_evidence_map`, `build_context`, …) as
`ostler.qa`'s flat namespace.

- code: ostler/ostler/qa/context.py::build_context@d86d0f82a92b
- code: ostler/ostler/qa/context.py::write_context@d86d0f82a92b
- code: ostler/ostler/qa/context.py::cmd_context@d86d0f82a92b
- code: ostler/ostler/qa/context.py::cmd_context_validate@d86d0f82a92b
- code: ostler/ostler/qa/context.py::validate_context@d86d0f82a92b
- code: ostler/ostler/qa/context.py::node_obligations@d86d0f82a92b
- code: ostler/ostler/qa/packet.py::ContextPacket@c725537831f8
- code: ostler/ostler/qa/packet.py::packet_of@c725537831f8
- code: ostler/ostler/qa/grounding_health.py::resolve_groundings@da8a0b8f6c0f
- code: ostler/ostler/qa/grounding_health.py::relation_fanout_warnings@da8a0b8f6c0f
- code: ostler/ostler/qa/owners.py::map_changes@de26fdbd12b7
- code: ostler/ostler/qa/owners.py::citing_family_counts@de26fdbd12b7
- code: ostler/ostler/qa/owners.py::shared_citations@de26fdbd12b7
- code: ostler/ostler/qa/references.py::find_references@087a925ce811
- code: ostler/ostler/qa/references.py::parse_reference@087a925ce811
- code: ostler/ostler/qa/source_context.py::SourceScope@c8ac0146f0b0
- code: ostler/ostler/qa/source_context.py::SourceRepository@c8ac0146f0b0
- code: ostler/ostler/qa/run.py::cmd_run@166d32882457
- code: ostler/ostler/qa/run.py::cmd_start@166d32882457
- code: ostler/ostler/qa/run.py::cmd_step@166d32882457
- code: ostler/ostler/qa/run.py::cmd_assert@166d32882457
- code: ostler/ostler/qa/run.py::cmd_stop@166d32882457
- code: ostler/ostler/qa/run.py::cmd_report@166d32882457
- code: ostler/ostler/qa/run.py::cmd_replay@166d32882457
- code: ostler/ostler/qa/run.py::cmd_validate@166d32882457
- code: ostler/ostler/qa/session.py::QaSession@b93f384fd8c4
- code: ostler/ostler/qa/session.py::_execute_check@b93f384fd8c4
- code: ostler/ostler/qa/dispatch.py::dispatch_target@d44c624e5b21
- code: ostler/ostler/qa/dispatch.py::claim_driver@d44c624e5b21
- code: ostler/ostler/qa/dispatch.py::hosts_observation@d44c624e5b21
- code: ostler/ostler/qa/dispatch.py::owes_live_evidence@d44c624e5b21
- code: ostler/ostler/qa/drivers.py::QaDriver@a902a4939789
- code: ostler/ostler/qa/drivers.py::PythonDriver@a902a4939789
- code: ostler/ostler/qa/drivers.py::create_driver@a902a4939789
- code: ostler/ostler/qa/drivers.py::Launcher@a902a4939789
- code: ostler/ostler/qa/drivers.py::LocalLauncher@a902a4939789
- code: ostler/ostler/qa/drivers.py::DisplayRecorder@a902a4939789
- code: ostler/ostler/qa/drivers.py::DeviceRecorder@a902a4939789
- code: ostler/ostler/qa/harness_host.py::load_harness_module@9aece567e098
- code: ostler/ostler/qa/harness_host.py::default_interpreter@9aece567e098
- code: ostler/ostler/qa/harness_host.py::harness_argv@9aece567e098
- code: ostler/ostler/qa/harness_host.py::harness_env@9aece567e098
- code: ostler/ostler/qa/harness_host.py::describe@9aece567e098
- code: ostler/ostler/qa/run_log.py::read_records@b2d1c68eaf42
- code: ostler/ostler/qa/run_log.py::run_log_tally@b2d1c68eaf42
- code: ostler/ostler/qa/run_log.py::passing_log_ref@b2d1c68eaf42
- code: ostler/ostler/qa/run_log.py::failing_log_refs@b2d1c68eaf42
- code: ostler/ostler/qa/plan.py::PlanDocument@08754cc7e1a2
- code: ostler/ostler/qa/plan.py::load_plan@08754cc7e1a2
- code: ostler/ostler/qa/plan.py::validate_v2@08754cc7e1a2
- code: ostler/ostler/qa/plan.py::check_runtime_requirements@08754cc7e1a2
- code: ostler/ostler/qa/v2.py::run_plan@fd118c311bc5
- code: ostler/ostler/qa/captures.py::CaptureDecl@248120ebb77f
- code: ostler/ostler/qa/captures.py::parse_bullet@248120ebb77f
- code: ostler/ostler/qa/report.py::build_report@0d73d5c319d1
- code: ostler/ostler/qa/report.py::render_report@0d73d5c319d1
- code: ostler/ostler/qa/report.py::write_report@0d73d5c319d1
- code: ostler/ostler/qa/report.py::report_path@0d73d5c319d1
- code: ostler/ostler/qa/verdict.py::Verdict@667c513201c2
- code: ostler/ostler/qa/verdict.py::merged@667c513201c2
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c
- code: ostler/ostler/qa/evidence_map.py::build_evidence_map@b2b27057b604
- code: ostler/ostler/qa/evidence_map.py::render_evidence_map@b2b27057b604
- code: ostler/ostler/qa/attribution.py::attribute@038d2f518503
- code: ostler/ostler/qa/attribution.py::Attribution@038d2f518503
- code: ostler/ostler/qa/attribution.py::Cause@038d2f518503
- code: ostler/ostler/qa/attribution.py::signatures@038d2f518503
- code: ostler/ostler/qa/frames.py::extract_frames@fb07c5fc799e
- code: ostler/ostler/qa/frames.py::frame_window@fb07c5fc799e
- code: ostler/ostler/qa/frames.py::find_step@fb07c5fc799e
- code: ostler/ostler/qa/repeats.py::RepeatWatch@1074839ca608
- code: ostler/ostler/qa/repeats.py::watch_for@1074839ca608
- code: ostler/ostler/qa/manifest.py::RunManifest@2d00c95675d5
- code: ostler/ostler/qa/sensitivity.py::trial@bc503e0d42f7
- code: ostler/ostler/qa/sensitivity.py::report@bc503e0d42f7
- code: ostler/ostler/qa/sensitivity.py::render@bc503e0d42f7
- code: ostler/ostler/qa/sensitivity.py::cmd_sensitivity@bc503e0d42f7
- code: ostler/ostler/qa/lint.py::PlanLintVisitor@7072719988f2
- code: ostler/ostler/qa/lint.py::lint_source@7072719988f2
- code: ostler/ostler/qa/lint.py::cmd_lint@7072719988f2
- code: ostler/ostler/qa/clean.py::cmd_clean@96a5108c86d5
- code: ostler/ostler/qa/clean.py::legacy_scratch_roots@96a5108c86d5
- code: ostler/ostler/qa/tools.py::catalog@6a440152c6e4
- code: ostler/ostler/qa/tools.py::opted_in_tools@6a440152c6e4
- code: ostler/ostler/qa/tools.py::resolved_commands@6a440152c6e4
- code: ostler/ostler/qa/tools.py::preflight_errors@6a440152c6e4
- code: ostler/ostler/qa/fixtures.py::declared@a4b91574f193
- code: ostler/ostler/qa/fixtures.py::resolved@a4b91574f193
- code: ostler/ostler/qa/fixtures.py::migrate@a4b91574f193
- code: ostler/ostler/qa/fixtures.py::cmd_migrate@a4b91574f193
- code: ostler/ostler/qa/addresses.py::substitute@910467430420
- code: ostler/ostler/qa/addresses.py::resolve_now@910467430420
- code: ostler/ostler/qa/addresses.py::read_book@910467430420
- code: ostler/ostler/qa/addresses.py::leased@910467430420
- code: ostler/ostler/qa/stack.py::ensure_stack@10c66bad65f4
- code: ostler/ostler/qa/stack.py::teardown_stack@10c66bad65f4
- code: ostler/ostler/qa/stack.py::boot_app@10c66bad65f4
- code: ostler/ostler/qa/stack.py::health_probe@10c66bad65f4
- code: ostler/ostler/qa/runbook.py::select_runbook@69d4a599edff
- code: ostler/ostler/qa/runbook.py::select_stack@69d4a599edff
- code: ostler/ostler/qa/runbook.py::select_server@69d4a599edff
- code: ostler/ostler/qa/runbook.py::step_command@69d4a599edff
- code: ostler/ostler/qa/runbook.py::stack_runbooks@69d4a599edff
- code: ostler/ostler/qa/__init__.py@16c3e096e515
- detail: [ostler](../cli.md)
- detail: [Compiling a book into a QA plan](compiling-a-book-into-a-qa-plan.md)

## Contract

- context precedes compile: `build_context` always runs, and is validated
  (`cmd_context_validate`), before `compile_plan` reads the obligations it minted; a compile never
  diffs the repository itself.
- fanout demotes, never excludes: a change cited by many unrelated nodes in `owners.py` degrades
  to a weaker `MappedChanges` reason instead of selecting every citing node, so a widely-shared
  utility's edit does not force every one of its callers into scope.
- a reading never raises on mismatch: `_execute_check` and every driver treat a failed judgment as
  data (a `Verdict`, an `Attribution`), not an exception; only a harness fault
  (`ClaimFault`/`FixtureFault`, see
  [Authoring QA scenarios](authoring-qa-scenarios.md)) propagates as one.
- outcome is uniform: every `ostler qa` subcommand in `run.py`, `lint.py`, `clean.py` and
  `sensitivity.py` returns a `QaOutcome`, never raises for an expected failure mode, so the CLI
  layer has one shape to render regardless of which subcommand ran.
