---
type: concept
slug: coder-genesis-bootstrap
title: Coder genesis bootstrap
---
# Coder genesis bootstrap

The genesis package is the deterministic bootstrap layer entered directly by the coder
workflow. It classifies a target, creates or reuses its repository, merges service
configuration, runs stack-provided initialization and scaffolds, then validates the complete
precondition set expected by the main coder loop. It has no agent turn and carries no stack
knowledge: packs, scaffolds, initialization commands, markers, assistants, workflows, and gates
are input values.

- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::resolve_genesis_target`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_repo_skips_git_init_but_still_builds_the_new_service`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_service_skips_the_skeleton_and_never_re_runs_the_init_command`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_blank_target_fails_before_anything_mutates`
- detail: [coder service contract](coder-service-contract.md)

## Fields

### target

- type: string
- default: empty string
- required: false
- semantics: absolute or relative target directory supplied to the bootstrap run
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### service

- type: string
- default: empty string
- required: false
- semantics: logical service name written as the workspace and service-gate key
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### service_root

- type: string
- default: empty string
- required: false
- semantics: repository-relative directory in which the service marker and native initialization are evaluated
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### packs

- type: comma-separated string
- default: empty string
- required: false
- semantics: farrier pack ids are split before installation
- verify: exit_status(code=0)
- semantics: an empty pack list means no pack installation
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### scaffolds

- type: comma-separated string of `<id>[:<directory>]` entries
- default: empty string
- required: false
- semantics: farrier scaffold entries enabled in `agents.yml` and rendered in order
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### init_cmd

- type: shell command string
- default: empty string
- required: false
- semantics: stack-owned native initialization command run in the service directory when its marker is absent
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### marker

- type: string
- default: empty string
- required: false
- semantics: file whose presence proves the native service initialization succeeded
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### markers

- type: comma-separated string
- default: empty string
- required: false
- semantics: complete service marker list
- verify: exit_status(code=0)
- semantics: when empty, the singular marker is used
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### workflows

- type: comma-separated string
- default: `coder`
- required: false
- semantics: workflow ids merged into the repository configuration
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### assistants

- type: comma-separated string
- default: `claude`
- required: false
- semantics: assistant backends enabled in the farrier configuration
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

### gates

- type: comma-separated string of `<gate>=<command>` entries
- default: empty string
- required: false
- semantics: service-specific deterministic commands are merged under `services:`
- verify: exit_status(code=0)
- semantics: malformed entries are reported and omitted
- verify: json_path(path="note", matches="gate\\(s\\).*dropped")
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- detail: [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)

## Methods

### start

- sig: `Genesis.start() -> Continue`
- does: classifies the target before any mutation
- does: routes an existing repository to configuration refresh without running Git initialization
- raises: `WorkflowFailed` when the target is empty or unusable
- returns: the classification result and the next build state
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis.start`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_blank_target_fails_before_anything_mutates`

### git_init

- sig: `Genesis.git_init() -> Continue`
- does: initializes a local repository and lands an initial commit when the target has no committed HEAD
- does: leaves a committed repository unchanged
- returns: the Git result and the configuration state
- verify: persists(subject="the target repository initial commit")
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis.git_init`

### config

- sig: `Genesis.config() -> Continue`
- does: round-trip-merges the service, packs, workflows, scaffolds, assistants, workspace markers, and gates into `agents.yml`
- does: routes an existing service past native initialization
- returns: the configuration result and the next build state
- verify: persists(subject="the target agents.yml configuration")
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis.config`

### skeleton

- sig: `Genesis.skeleton() -> Continue`
- does: runs the supplied native initialization command in the service directory when the marker is absent
- does: skips native initialization when the marker already exists
- returns: the skeleton result and the farrier state
- verify: persists(subject="the declared service marker")
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis.skeleton`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_service_skips_the_skeleton_and_never_re_runs_the_init_command`

### farrier

- sig: `Genesis.farrier() -> Continue`
- does: installs declared farrier packs unless the pack list is empty
- does: renders each declared scaffold in input order
- returns: the installation result and the verification state
- verify: persists(subject="the farrier agent context")
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis.farrier`

### verify

- sig: `Genesis.verify() -> Done`
- does: checks repository binding, committed Git state, service markers, agent instructions, epics root, and backlog
- does: logs warnings without failing for a missing lint target
- raises: `WorkflowFailed` when any required genesis precondition is absent
- returns: the validation report when all required checks pass
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis.verify`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_invalid_repo_fails_the_run_with_no_repair_turn`

### resolve_genesis_target

- sig: `resolve_genesis_target(logger, target="", service="", service_root="", marker="", markers=()) -> TargetClassification`
- does: returns an unsuccessful classification without touching the filesystem when `target` is empty
- does: resolves a supplied target to an absolute path before classification
- does: classifies the repository as `absent` when the directory is missing or empty
- does: classifies the repository as `partial` when it has content but no `agents.yml`
- does: classifies the repository as `existing` when `agents.yml` is present
- does: classifies the declared service as `existing` only when its marker file exists under `service_root`
- does: resolves `markers` as the declared marker list, falling back to the singular `marker` when the list is empty
- returns: one classification carrying the resolved target, service, marker list, repository state, service state, and operator note
- verify: count(subject="target classification", equals=1)
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::resolve_genesis_target`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_blank_target_fails_before_anything_mutates`

### genesis_git_init

- sig: `genesis_git_init(logger, target_dir="") -> GitInit`
- does: returns an unready result without mutation when `target_dir` is empty
- does: creates the target directory when it does not exist
- does: initializes a local Git repository when the target has no `.git` directory
- does: creates `README.md` from the target directory name when the target has no README
- does: commits the initial tree when the target has no committed HEAD
- does: leaves an already committed repository unchanged and configures no remote
- returns: readiness, the current or created initial commit, and an operator note
- verify: persists(subject="the target repository initial commit")
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::genesis_git_init`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_repo_skips_git_init_but_still_builds_the_new_service`

### write_agents_yml

- sig: `write_agents_yml(logger, target_dir="", service="", packs=(), service_root="", markers=(), workflows=("coder",), scaffolds=(), assistants=("claude",), gates=()) -> AgentsYml`
- does: returns an explanatory result without mutation when `target_dir` is empty or is not a directory
- does: preserves existing `agents.yml` values, comments, key order, and scalar style while merging
- does: sets the repository name from the target directory when no repository name exists
- does: declares the three supported assistant names as enabled or disabled from `assistants`, while preserving an existing assistant choice
- does: unions requested packs, workflows, and scaffold identifiers with existing lists without duplicates
- does: stores `workspace.type` as `mono` and unions service roots and markers into the workspace block
- does: stores each valid `<gate>=<command>` pair under the named service's `services` block without replacing an existing gate command
- does: reports unknown assistants and malformed gate entries as dropped configuration instead of interpreting them
- does: reports gates as dropped when no service name is supplied
- returns: whether the file changed, its relative path, and an operator note describing retained or dropped configuration
- verify: persists(subject="the target agents.yml configuration")
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::write_agents_yml`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_agents_yml_carries_the_workspace_block_the_planner_reads`

### init_skeleton

- sig: `init_skeleton(logger, target_dir="", service_root="", init_cmd="", marker="") -> Skeleton`
- does: returns an explanatory result without mutation when `target_dir` is empty or is not a directory
- does: creates the service directory under `service_root` when it is absent
- does: skips the native initialization command when the marker already exists
- does: reports a missing initialization command when the marker is absent and no command is supplied
- does: runs the supplied initialization command in the service directory with a 900-second timeout when the marker is absent
- does: reports the command output when initialization exits non-zero
- does: reports failure when initialization exits successfully but does not create the marker
- does: marks the skeleton ready only when the declared marker exists after initialization
- returns: marker readiness, the repository-relative marker path, and an operator note
- verify: persists(subject="the declared service marker")
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::init_skeleton`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_existing_service_skips_the_skeleton_and_never_re_runs_the_init_command`

### install_farrier

- sig: `install_farrier(logger, target_dir="", scaffolds=(), skip_install=False) -> FarrierInstall`
- does: returns an explanatory result without invoking Farrier when `target_dir` is empty or is not a directory
- does: runs `farrier install --repo <target>` before rendering scaffolds unless `skip_install` is true
- does: renders each non-empty `<scaffold-id>[:<directory>]` entry in input order
- does: stops at the first failed install or scaffold invocation
- does: reports the identifiers rendered before a scaffold failure
- returns: installation status, rendered scaffold identifiers, and an operator note containing tool failures
- verify: persists(subject="the farrier agent context")
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::install_farrier`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_agents_yml_carries_the_workspace_block_the_planner_reads`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_failed_farrier_install_still_fails_at_verify`

### validate_genesis

- sig: `validate_genesis(logger, target_dir="", service_root="", markers=()) -> GenesisReport`
- does: returns an invalid report without filesystem checks when `target_dir` is empty or is not a directory
- does: reports an error when the target has no `.git` directory or no committed HEAD
- does: reports an error when Ostler binds to a repository other than the target
- does: reports the shared service-contract errors for missing declared service markers
- does: reports an error when `.agents/agents-context.json` is absent or has an empty `instructions` map
- does: reports an error when the Ostler-resolved epics root is absent
- does: reports an error when the Ostler-resolved backlog is absent
- does: reports a missing `lint` Make target as a warning rather than an error
- returns: validity plus newline-separated complete error and warning reports
- verify: count(subject="genesis validation report", equals=1)
- code: `workflows/src/workhorse_workflows/coder/genesis/nodes.py::validate_genesis`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept`
- tests: `workflows/tests/coder/genesis/test_flow.py::test_an_invalid_repo_fails_the_run_with_no_repair_turn`
