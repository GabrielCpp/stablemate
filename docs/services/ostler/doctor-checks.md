---
type: cli
slug: doctor-checks
title: ostler doctor defects
---
# ostler doctor defects

The defects `ostler doctor` refuses in a book, each proved on a scratch book that holds one kind of
defect. Every claim runs in a repository of its own under the checkout, so no scenario sees these
defects in the book of the checkout. A caller reads the finding code, the page and the exit status.

- binary: ostler
- code: ostler/ostler/cli.py::main@e56ee756ce4b

## Commands

### ostler-doctor-unparsable-step
- usage: ostler doctor --path PATH --json: refuses a fixture step whose run line is not a shell
  command, and names the step
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/shell", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=1)
- verify: json_path(path="findings[0].code", equals="unparsable-command")
- verify: json_path(path="findings[0].path", equals="docs/services/shell/fixtures/prepare.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@c5e91020c76a
- code: ostler/ostler/keys.py::pressable@c60cef0f162a
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@f348085e1eeb
- code: ostler/ostler/qa/stack.py::shell_syntax_error@bc81067f4925
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@d161c8ab9dcd
- code: ostler/ostler/values.py::dialog_answer@e0f43edd44dc
- code: ostler/ostler/vet/placement.py::parse_placement@557c406d181b

### ostler-doctor-launch-screen
- usage: ostler doctor --path PATH --json: refuses a fixture that names a launch screen the screen's
  own page cannot support
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/launch", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-launch-screen-lifetime\"")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@c5e91020c76a
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@f348085e1eeb
- code: ostler/ostler/qa/stack.py::shell_syntax_error@bc81067f4925
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@d161c8ab9dcd
- code: ostler/ostler/values.py::dialog_answer@e0f43edd44dc
- code: ostler/ostler/vet/placement.py::parse_placement@557c406d181b

### ostler-doctor-ui-defects
- usage: ostler doctor --path PATH --json: refuses a component whose name describes the label, a
  check that presses a key no browser can press, a dialog answer that is neither accept nor
  dismiss, and a `visible(text=)` check on a text field, which shows its content as a value and
  never as text (`text-of-a-field`)
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/ui", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"prose-name\"")
- verify: stdout(matches="\"code\": \"unparsed-check\"")
- verify: stdout(matches="\"code\": \"unparsable-bullet-value\"")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@c5e91020c76a
- code: ostler/ostler/locator_findings.py::ProseName@8173300180b6
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@f348085e1eeb
- code: ostler/ostler/qa/stack.py::shell_syntax_error@bc81067f4925
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@d161c8ab9dcd
- code: ostler/ostler/values.py::dialog_answer@e0f43edd44dc
- code: ostler/ostler/vet/placement.py::parse_placement@557c406d181b

### ostler-doctor-unknown-driver
- usage: ostler doctor --path PATH --json: refuses a runbook whose driver is not one of the drivers
  a book can name
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/ops", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"unknown-driver\"")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@c5e91020c76a
- code: ostler/ostler/drivers.py::DRIVERS@cc0927c9bd8e
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@f348085e1eeb
- code: ostler/ostler/qa/stack.py::shell_syntax_error@bc81067f4925
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@d161c8ab9dcd
- code: ostler/ostler/values.py::dialog_answer@e0f43edd44dc
- code: ostler/ostler/vet/placement.py::parse_placement@557c406d181b

### ostler-doctor-census
- usage: ostler doctor --census: prints how many finding codes the checker defines, how many fired
  on this book, and which the run never entered
- exits: 0 always
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--census"])
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^\\d+ codes defined")
- verify: stdout(matches="(?m)^\\s+\\d+ dormant-unreachable")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@c5e91020c76a
- code: ostler/ostler/census.py::code_sites@0d0cee8fee15
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@f348085e1eeb
- code: ostler/ostler/qa/stack.py::shell_syntax_error@bc81067f4925
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@d161c8ab9dcd
- code: ostler/ostler/values.py::dialog_answer@e0f43edd44dc
- code: ostler/ostler/vet/placement.py::parse_placement@557c406d181b

### ostler-doctor-register-links
- usage: ostler doctor --json: refuses a register record that does not parse, and a decision and its evidence records that do not name each other
- exits: 1 when the register or a decision holds an error finding
- run: invoke(argv=["-C", "doctor-register-scratch", "doctor", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "doctor-register-scratch/art"})
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=4)
- verify: json_path(path="findings[0].code", equals="register-record-unreadable")
- verify: json_path(path="findings[0].path", matches="^.*/backlogs/api-service/billing/X-2/record\\.md$")
- verify: json_path(path="findings[1].code", equals="decision-back-link-missing")
- verify: json_path(path="findings[1].message", equals="decision 'D-1' lists record 'X-1', whose `decision` is 'D-9'")
- verify: json_path(path="findings[2].code", equals="decision-evidence-unresolved")
- verify: json_path(path="findings[2].message", equals="decision 'D-1' cites evidence 'X-7', which resolves to no record on the shelf")
- verify: json_path(path="findings[3].code", equals="decision-back-link-missing")
- verify: json_path(path="findings[3].message", equals="record 'X-1' names decision 'D-9', and no decision file has that id")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a broken register beside an empty book
- code: ostler/ostler/doctor.py::_check_register_records@fb4e8dec596b
- code: ostler/ostler/doctor.py::_check_decisions@1c443528c84a
- code: ostler/ostler/adr.py::decisions@02dde8a1ad94
- detail: [The debt register](concepts/the-debt-register.md)

### ostler-doctor-milestone-layout
- usage: ostler doctor --path PATH --json: refuses a milestone filed as a single file instead of its
  own `<slug>/milestone.md` folder
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/milestones", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=1)
- verify: json_path(path="findings[0].code", equals="legacy-milestone-file")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/milestones.py::check_layout@9bb701183e61
- code: ostler/ostler/registry.py::RESERVED_FILES@eded04d48db4

### ostler-doctor-resource-reach-shape
- usage: ostler doctor --path PATH --json: refuses a resource page whose `reach:` is neither `http` nor `cli`, that lacks the `base:` or `binary:` its reach takes, that carries a key of the other reach, or whose `secret:` is not an environment variable name
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/resources", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"resource-reach-shape\"")
- verify: stdout(matches="docs/services/resources/reach-ftp.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_resources@4642faef62de
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-resource-probe-shape
- usage: ostler doctor --path PATH --json: refuses a resource page whose `## Probe` does not hold exactly one step of `kind: probe` in the form its reach takes
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/resources", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"resource-probe-shape\"")
- verify: stdout(matches="docs/services/resources/probe-kind.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_resources@4642faef62de
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-resource-observation-shape
- usage: ostler doctor --path PATH --json: refuses an observation that is not `kind: observe`, lacks the form its reach takes, or sends a request whose method is not GET
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/resources", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"resource-observation-shape\"")
- verify: stdout(matches="docs/services/resources/observation-post.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_resources@4642faef62de
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-fixture-probe-local
- usage: ostler doctor --path PATH --json: refuses a resource page whose `base:` names localhost, 127.0.0.1, 0.0.0.0 or [::1], because whatever answers on this machine may be someone else's
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/resources", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-probe-local\"")
- verify: stdout(matches="docs/services/resources/local-base.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_resources@4642faef62de
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-step-request-shape
- usage: ostler doctor --path PATH --json: refuses a step whose `request:` is not `<METHOD> /path`, that also states `run:`, that has no `on:`, or whose `body:` is not a JSON object
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/borrowing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"step-request-shape\"")
- verify: stdout(matches="docs/services/borrowing/fixtures/bad-request.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_request_step@02e7743e4f99
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-step-reach-mismatch
- usage: ostler doctor --path PATH --json: refuses a step that states `request:` on a `cli` resource or `run:` on an `http` resource
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/borrowing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"step-reach-mismatch\"")
- verify: stdout(matches="docs/services/borrowing/fixtures/mismatched.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_request_step@02e7743e4f99
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-fixture-borrow-lifetime
- usage: ostler doctor --path PATH --json: refuses a fixture with a `kind: borrow` step that does not state `lifetime: scenario`
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/borrowing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-borrow-lifetime\"")
- verify: stdout(matches="docs/services/borrowing/fixtures/no-lifetime.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_lifetimes@66ac83b7e61e
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-fixture-fixed-id
- usage: ostler doctor --path PATH --json: refuses a fixture step that writes a literal id, or a provided id asserted with a literal `is:` rather than a generated one such as `$(uuidgen)`, because two fixtures that fix the same id rewrite each other's rows on one copy of the stack
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/fixed-id", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-fixed-id\"")
- verify: stdout(matches="docs/services/fixed-id/fixtures/fixed-row.md")
- verify: stdout(matches="docs/services/fixed-id/fixtures/asserted-id.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/step_commands.py::check_fixture_fixed_id@ad03710191e5
- code: ostler/ostler/step_commands.py::check_fixture_asserted_id@38876a32a69b
- detail: [Compiling a book into a QA plan](concepts/compiling-a-book-into-a-qa-plan.md)

### ostler-doctor-fixture-release-without-borrow
- usage: ostler doctor --path PATH --json: refuses a fixture with a `kind: release` step and no `kind: borrow` step
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/borrowing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-release-without-borrow\"")
- verify: stdout(matches="docs/services/borrowing/fixtures/release-only.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_lifetimes@66ac83b7e61e
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-unknown-observation
- usage: ostler doctor --path PATH --json: refuses an `observe:` that names no resource page, or an observation the page does not hold
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/observing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"unknown-observation\"")
- verify: stdout(matches="docs/services/observing/cli.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_observations@07b075289f09
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-unparsed-observation
- usage: ostler doctor --path PATH --json: refuses an `observe:` whose value is not `@<resource>.<observation>`
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/observing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"unparsed-observation\"")
- verify: stdout(matches="docs/services/observing/cli.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_observations@07b075289f09
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-doctor-within-off-observation
- usage: ostler doctor --path PATH --json: refuses a `within=` on a `verify:` row that no `observe:` bullet holds
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/observing", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"within-off-observation\"")
- verify: stdout(matches="docs/services/observing/cli.md")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo whose books each carry one kind of defect
- code: ostler/ostler/resource_checks.py::check_observations@07b075289f09
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)
