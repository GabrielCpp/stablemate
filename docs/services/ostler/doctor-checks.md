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
- code: ostler/ostler/cli.py::main@97fced506443

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
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/keys.py::pressable@a22c2b93f53b
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@d769665467aa
- code: ostler/ostler/qa/stack.py::shell_syntax_error@49f8647f79af
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@a44a1ff496dd
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/vet/placement.py::parse_placement@fa7b7986f813

### ostler-doctor-launch-screen
- usage: ostler doctor --path PATH --json: refuses a fixture that names a launch screen the screen's
  own page cannot support
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/launch", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-launch-screen-lifetime\"")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@d769665467aa
- code: ostler/ostler/qa/stack.py::shell_syntax_error@49f8647f79af
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@a44a1ff496dd
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/vet/placement.py::parse_placement@fa7b7986f813

### ostler-doctor-ui-defects
- usage: ostler doctor --path PATH --json: refuses a component whose name describes the label, a
  check that presses a key no browser can press, and a dialog answer that is neither accept nor
  dismiss
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/ui", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"prose-name\"")
- verify: stdout(matches="\"code\": \"unparsed-check\"")
- verify: stdout(matches="\"code\": \"unparsable-bullet-value\"")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/locator_findings.py::ProseName@7318d29e242e
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@d769665467aa
- code: ostler/ostler/qa/stack.py::shell_syntax_error@49f8647f79af
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@a44a1ff496dd
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/vet/placement.py::parse_placement@fa7b7986f813

### ostler-doctor-unknown-driver
- usage: ostler doctor --path PATH --json: refuses a runbook whose driver is not one of the drivers
  a book can name
- exits: 1 when the book holds an error finding
- run: invoke(argv=["-C", "doctor-scratch", "doctor", "--path", "docs/services/ops", "--json"])
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"unknown-driver\"")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/drivers.py::DRIVERS@cc0927c9bd8e
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@d769665467aa
- code: ostler/ostler/qa/stack.py::shell_syntax_error@49f8647f79af
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@a44a1ff496dd
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/vet/placement.py::parse_placement@fa7b7986f813

### ostler-doctor-malformed-ids
- usage: ostler doctor --json: warns when the id registry does not match its schema, and still exits
  0
- exits: 0 when the registry is the only finding, because a schema finding is a warning
- run: invoke(argv=["-C", "doctor-ids-scratch", "doctor", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="warnings", equals=1)
- verify: json_path(path="findings[0].code", equals="schema")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@d769665467aa
- code: ostler/ostler/qa/stack.py::shell_syntax_error@49f8647f79af
- code: ostler/ostler/schemas.py::validate@17d011398cb2
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@a44a1ff496dd
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/vet/placement.py::parse_placement@fa7b7986f813

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
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/census.py::code_sites@9c71f5a187f2
- code: ostler/ostler/qa/fixture_browser.py::is_browser_step@d769665467aa
- code: ostler/ostler/qa/stack.py::shell_syntax_error@49f8647f79af
- code: ostler/ostler/step_commands.py::check_fixture_launch_screen@a44a1ff496dd
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/vet/placement.py::parse_placement@fa7b7986f813

### ostler-doctor-register-links
- usage: ostler doctor --json: refuses a register record that does not parse, and a decision and its evidence records that do not name each other
- exits: 1 when the register or a decision holds an error finding
- run: invoke(argv=["-C", "doctor-register-scratch", "doctor", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "doctor-register-scratch/art"})
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=4)
- verify: json_path(path="findings[0].code", equals="register-record-unreadable")
- verify: json_path(path="findings[0].path", matches="^.*/backlog/api-service/billing/X-2/record\\.md$")
- verify: json_path(path="findings[1].code", equals="decision-back-link-missing")
- verify: json_path(path="findings[1].message", equals="decision 'D-1' lists record 'X-1', whose `decision` is 'D-9'")
- verify: json_path(path="findings[2].code", equals="decision-evidence-unresolved")
- verify: json_path(path="findings[2].message", equals="decision 'D-1' cites evidence 'X-7', which resolves to no record on the shelf")
- verify: json_path(path="findings[3].code", equals="decision-back-link-missing")
- verify: json_path(path="findings[3].message", equals="record 'X-1' names decision 'D-9', and no decision file has that id")
- fixture: [doctor scratch repo](fixtures/doctor-scratch-repo.md) with a broken register beside an empty book
- code: ostler/ostler/doctor.py::_check_register_records@99b46802793c
- code: ostler/ostler/doctor.py::_check_decisions@99b46802793c
- code: ostler/ostler/adr.py::decisions@0616ec2d019d
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
- code: ostler/ostler/milestones.py::check_layout@03e29bd2aeb7
- code: ostler/ostler/registry.py::RESERVED_FILES@bfa3450ef60d
