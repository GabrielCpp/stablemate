---
type: concept
slug: skill-examples-compile
title: Skill examples compile
---
# Skill examples compile

An author copies a skill's example into a book, so an example that the tools refuse teaches a line
that fails on first use. The skills, the parsers and the compiler move together because the ostler
test run judges every skill example with the same code that judges a real book. An example that
drifts from that code fails the test run before the skill ships.

- rule: every `verify:`, `arrange:` and `intercept:` line in a skill example parses with the
  parser that reads a real book.
- rule: every example page and fragment goes through the doctor and the plan compiler, and earns
  no finding beyond what it declares. A fragment gets a stub host, and only gaps on its own
  headings count.
- rule: an example that shows a mistake on purpose names every code it earns in `expect=` on its
  fence. The comparison is an exact set, so a wrong example stays marked and cannot earn a second
  mistake unnoticed.
- rule: a finding an example cannot avoid is excused by code with a written reason. A fictional
  project holds no source to cite, and a stub host lists nothing else.
- rule: every `ostler` command a skill spells is checked against the real command line, including
  its flags, its subcommands and the fixed choices of its positionals.
- rule: a rule sentence with no example stays unprotected. A prose rule gains this protection when
  an example beside it shows the rule's compiled result.
- tests: ostler/tests/test_skill_examples.py::test_every_claim_line_parses
- tests: ostler/tests/test_skill_examples.py::test_every_example_earns_only_what_it_declares
- tests: ostler/tests/test_skill_examples.py::test_every_command_a_skill_spells_exists
- tests: ostler/tests/test_skill_examples.py::test_a_command_the_cli_refuses_goes_red
- tests: ostler/tests/test_skill_examples.py::test_a_command_the_cli_takes_stays_green
