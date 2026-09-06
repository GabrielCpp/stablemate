---
type: concept
slug: workflow-prompt-static-contracts
title: Workflow prompt static contracts
---
# Workflow prompt static contracts

The shared static checks inspect every literal `self.agent(...)` call in the author, coder,
OKF-builder, and research packages. They reject a prompt path that does not name a packaged
file, a prompt reference that no rendering call can supply, and a hand-written JSON example
whose top-level keys differ from the model declared at the turn. They intentionally inspect
source so nested and gated turns are covered before a live run reaches them.

`{{ result_schema }}` is generated from the declared result model and is therefore exempt from
the hand-written-example comparison. Prompt variables inside a Jinja raw block are likewise not
render-time references. Any turn arguments the static reader cannot resolve fail separately,
rather than silently weakening the variable check.

- code: `workflows/tests/test_prompts_exist.py::test_the_prompt_file_is_there`
- code: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- code: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`
- tests: `workflows/tests/test_prompts_exist.py::test_the_sweep_found_turns_in_every_workflow`
- tests: `workflows/tests/test_prompt_variables.py::test_no_turn_is_unreadable`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_sweep_found_turns_in_every_workflow`
