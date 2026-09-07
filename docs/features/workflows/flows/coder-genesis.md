---
type: flow
slug: coder-genesis
title: Coder genesis flow
---
# Coder genesis flow

- The directly-entered [Genesis workflow](../../../../workflows/src/workhorse_workflows/coder/genesis/flow.py)
  bootstraps a target directory into the repository and service preconditions expected by the
  Coder and Author workflows. It contains deterministic tooling only: no agent turn, product
  decision, or repair branch occurs in this flow. Stack-specific packs, scaffolds, init command,
  marker, workflow, assistant, and gate values arrive as workflow parameters and are written or
  executed without stack-specific interpretation.

- start: the run has a non-empty target path and checkpointed genesis parameters for the target service
- verify: count(subject="genesis target classification", equals=1)
- steps:
  - [classify](#classify)
  - [git-init](#git-init)
  - [config](#config)
  - [skeleton](#skeleton)
  - [farrier](#farrier)
  - [verify](#verify)
- end: the target passes all repository, service, tooling-context, documentation-root, and backlog precondition checks
- verify: exit_status(code=0)
- detail: [coder workflow composition root](../concepts/coder-workflow-composition-root.md)
- detail: [coder genesis bootstrap](../concepts/coder-genesis-bootstrap.md)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_repo_skips_git_init_but_still_builds_the_new_service`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_service_skips_the_skeleton_and_never_re_runs_the_init_command`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_blank_target_fails_before_anything_mutates`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_invalid_repo_fails_the_run_with_no_repair_turn`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_run_killed_in_the_farrier_step_resumes_on_that_state_alone`

## Steps

### classify

- kind: prepare

`start` calls `resolve_genesis_target` before any mutation. A missing or empty target fails the
flow immediately. Otherwise the node resolves the absolute target directory, classifies repository
state as `absent`, `partial` (content without `agents.yml`), or `existing` (an `agents.yml` is
present), and separately classifies the declared service as `absent` or `existing` from its marker
file. The resolved marker list uses `markers` when supplied and otherwise the singular `marker`.
An existing repository skips only `git-init`; an existing service skips only `skeleton`.

### git-init

- kind: prepare

For a non-existing repository, `genesis_git_init` creates the target, initializes local Git, creates
`README.md` when absent, and lands an initial commit. A repository with an existing committed HEAD
is left unchanged, while an unborn repository receives the initial commit. No remote is configured.

### config

- kind: prepare

`write_agents_yml` round-trip-merges the service into `agents.yml`, preserving existing values and
comments. It ensures the repository name, assistant map, requested pack/workflow/scaffold ids,
`workspace.type`, service roots, service markers, and service-specific gate commands are present.
Existing configuration is not replaced, and malformed gate entries or unknown assistant names are
reported in the result rather than interpreted.

### skeleton

- kind: seed

For an absent service, `init_skeleton` creates the service directory and runs the supplied native
init command there. The command must leave the supplied marker file in place; a non-zero command or
a missing marker is reported for terminal validation. If the marker already exists, initialization
is skipped so a re-run cannot clobber a live service.

### farrier

- kind: seed

`install_farrier` runs Farrier install unless no packs were requested, then renders each supplied
`<scaffold-id>[:<directory>]` in order. Install produces the agent context and each scaffold seeds
its requested directory. A failed install or scaffold is recorded and later validation reports the
missing precondition; the flow does not call an agent to repair deterministic tooling failures.

### verify

- kind: verify

`validate_genesis` checks that the target is a committed Git repository bound as the current Ostler
root, that the service marker exists, that the agent context has a non-empty instructions map, and
that Ostler resolves both the epics root and backlog. It reuses the shared service contract for
service markers. A missing lint target is advisory only. Warnings are logged; any error raises
`WorkflowFailed` with the complete validation report, otherwise the report is returned as the
terminal result.
