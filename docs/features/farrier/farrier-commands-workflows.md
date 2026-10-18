---
type: fragment
slug: farrier-commands-workflows
title: 'farrier — render the agent prompt library into a repository: Commands'
---
# farrier — render the agent prompt library into a repository: Commands

- host: [farrier — render the agent prompt library into a repository](farrier.md)

## Commands

### workflows
- usage: `farrier workflows [--names]`
- flags:
  - `--names` — print only the sorted, space-separated workflow names for the generated
    [make launcher](concepts/generated-agent-launcher.md)
- does:
  - discover installed workflow distributions from `pipx list --json`
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c151/home", "STABLEMATE_CONFIG": "c151/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c151/pipx-stub-bin:$PATH"})
    - verify: stdout(text="coder")
    - fixture: pipx-two-workflows dir=c151
  - when `--names` is given, print the discovered workflow names on one line
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c152/home", "STABLEMATE_CONFIG": "c152/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c152/pipx-stub-bin:$PATH"})
    - verify: stdout(text="coder planner")
    - fixture: pipx-two-workflows dir=c152
  - when `--names` is given, sort the names alphabetically
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c153/home", "STABLEMATE_CONFIG": "c153/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c153/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="^coder planner")
    - fixture: pipx-two-workflows dir=c153
  - when `--names` is given, print a duplicate workflow name only once
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c154/home", "STABLEMATE_CONFIG": "c154/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c154/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="^coder planner\\s*$")
    - fixture: pipx-duplicate-workflow dir=c154
  - when `--names` is given and no workflow is discoverable, print an empty line
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c155/home", "STABLEMATE_CONFIG": "c155/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c155/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="\\A\\n\\Z")
    - fixture: no-pipx dir=c155
  - without `--names`, print each provider's distribution name
    - run: invoke(argv=["workflows"], env={"HOME": "c156/home", "STABLEMATE_CONFIG": "c156/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c156/pipx-stub-bin:$PATH"})
    - verify: stdout(text="workhorse-workflows ")
    - fixture: pipx-two-workflows dir=c156
  - without `--names`, print each provider's version
    - run: invoke(argv=["workflows"], env={"HOME": "c157/home", "STABLEMATE_CONFIG": "c157/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c157/pipx-stub-bin:$PATH"})
    - verify: stdout(text="1.2.0")
    - fixture: pipx-two-workflows dir=c157
  - without `--names`, print each provider's origin
    - run: invoke(argv=["workflows"], env={"HOME": "c158/home", "STABLEMATE_CONFIG": "c158/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c158/pipx-stub-bin:$PATH"})
    - verify: stdout(text="workhorse-workflows 1.2.0  <- ")
    - fixture: pipx-two-workflows dir=c158
  - without `--names`, print each provider's workflow names as indented lines
    - run: invoke(argv=["workflows"], env={"HOME": "c159/home", "STABLEMATE_CONFIG": "c159/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c159/pipx-stub-bin:$PATH"})
    - verify: stdout(text="    planner")
    - fixture: pipx-two-workflows dir=c159
  - without `--names` and with no discoverable workflows, print guidance to install a workflow
    distribution
    - run: invoke(argv=["workflows"], env={"HOME": "c160/home", "STABLEMATE_CONFIG": "c160/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c160/pipx-stub-bin:$PATH"})
    - verify: stdout(text="No workflows installed.")
    - fixture: no-pipx dir=c160
  - without `--names`, mark a provider whose local source directory is missing with
    `** source directory is gone **`
    - run: invoke(argv=["workflows"], env={"HOME": "c161/home", "STABLEMATE_CONFIG": "c161/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c161/pipx-stub-bin:$PATH"})
    - verify: stdout(text="** source directory is gone **")
    - fixture: pipx-missing-source dir=c161
- errors:
  - treat a missing `pipx` executable as an empty discoverable workflow set
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c162/home", "STABLEMATE_CONFIG": "c162/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c162/pipx-stub-bin:$PATH"})
    - verify: stdout(text="\n")
    - fixture: no-pipx dir=c162
  - treat a nonzero `pipx list --json` result as an empty discoverable workflow set
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c163/home", "STABLEMATE_CONFIG": "c163/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c163/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="planner")
    - fixture: pipx-failing dir=c163
  - treat malformed `pipx list --json` output as an empty discoverable workflow set
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c164/home", "STABLEMATE_CONFIG": "c164/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c164/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stderr", text="Traceback")
    - fixture: pipx-malformed dir=c164
- exits:
  - return `0` for successful discovery output
    - run: invoke(argv=["workflows"], env={"HOME": "c165/home", "STABLEMATE_CONFIG": "c165/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c165/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: pipx-two-workflows dir=c165
  - return `0` for an empty `--names` result
    - run: invoke(argv=["workflows", "--names"], env={"HOME": "c166/home", "STABLEMATE_CONFIG": "c166/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c166/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: no-pipx dir=c166
  - return `1` in human-readable mode when any discovered provider has a missing local source
    directory
    - run: invoke(argv=["workflows"], env={"HOME": "c167/home", "STABLEMATE_CONFIG": "c167/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c167/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: pipx-missing-source dir=c167
- code: `farrier/farrier/cli.py::_run_workflows` @0244d6a97e3b
- detail: [generated agent launcher](concepts/generated-agent-launcher.md)
- detail: [installed workflow discovery](concepts/installed-workflow-discovery.md)
- tests: `farrier/tests/test_pipx.py::test_discover_reads_the_json_pipx_actually_emits`
- tests: `farrier/tests/test_pipx.py::test_pipx_not_installed_means_no_workflows_not_a_broken_build`
- tests: `farrier/tests/test_pipx.py::test_pipx_failing_or_emitting_junk_means_no_workflows`
- tests: `farrier/tests/test_launcher_make.py::test_a_discovered_workflow_becomes_a_real_target`

### doctor
- usage: `farrier doctor [--repo DIR]`
- flags:
  - `--repo <dir>` — repository root whose `agents.yml` is diagnosed. Default: current working
    directory.
- does:
  - report an error when `<repo>/agents.yml` is absent
    - run: invoke(argv=["doctor", "--repo", "c168"], env={"HOME": "c168/home", "STABLEMATE_CONFIG": "c168/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c168/pipx-stub-bin:$PATH"})
    - verify: stdout(text="no agents.yml in")
    - fixture: empty-dir dir=c168
  - report an error when `agents.yml` cannot be read or parsed as YAML
    - run: invoke(argv=["doctor", "--repo", "c169"], env={"HOME": "c169/home", "STABLEMATE_CONFIG": "c169/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c169/pipx-stub-bin:$PATH"})
    - verify: stdout(text="agents.yml could not be read")
    - fixture: broken-agents-yml dir=c169
  - report an error when the parsed `agents.yml` value is not a mapping
    - run: invoke(argv=["doctor", "--repo", "c170"], env={"HOME": "c170/home", "STABLEMATE_CONFIG": "c170/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c170/pipx-stub-bin:$PATH"})
    - verify: stdout(text="agents.yml is not a YAML mapping.")
    - fixture: list-agents-yml dir=c170
  - warn when `workspace.service_roots` is empty
    - run: invoke(argv=["doctor", "--repo", "c171"], env={"HOME": "c171/home", "STABLEMATE_CONFIG": "c171/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c171/pipx-stub-bin:$PATH"})
    - verify: stdout(text="workspace.service_roots is empty")
    - fixture: bare-agents-yml dir=c171
  - warn when `workspace.service_markers` is empty
    - run: invoke(argv=["doctor", "--repo", "c172"], env={"HOME": "c172/home", "STABLEMATE_CONFIG": "c172/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c172/pipx-stub-bin:$PATH"})
    - verify: stdout(text="workspace.service_markers is empty")
    - fixture: bare-agents-yml dir=c172
  - warn when no top-level `services:` mapping or `workflow.services:` mapping exists
    - run: invoke(argv=["doctor", "--repo", "c173"], env={"HOME": "c173/home", "STABLEMATE_CONFIG": "c173/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c173/pipx-stub-bin:$PATH"})
    - verify: stdout(text="no services: block")
    - fixture: bare-agents-yml dir=c173
  - warn when a service entry is not a mapping
    - run: invoke(argv=["doctor", "--repo", "c174"], env={"HOME": "c174/home", "STABLEMATE_CONFIG": "c174/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c174/pipx-stub-bin:$PATH"})
    - verify: stdout(text="services.api is not a mapping")
    - fixture: scalar-service-agents-yml dir=c174
  - warn when a declared service omits a `lint` or `test` command, while accepting the
    legacy top-level `lint` mapping as a lint declaration
    - run: invoke(argv=["doctor", "--repo", "c175"], env={"HOME": "c175/home", "STABLEMATE_CONFIG": "c175/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c175/pipx-stub-bin:$PATH"})
    - verify: stdout(text="services.api declares no test command")
    - fixture: lint-only-agents-yml dir=c175
  - warn when a workspace service root matches neither a service key nor its complete root
    path
    - run: invoke(argv=["doctor", "--repo", "c176"], env={"HOME": "c176/home", "STABLEMATE_CONFIG": "c176/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c176/pipx-stub-bin:$PATH"})
    - verify: stdout(text="these service roots match no services: key")
    - fixture: orphan-root-agents-yml dir=c176
  - print each finding with its severity and operator-facing message
    - run: invoke(argv=["doctor", "--repo", "c177"], env={"HOME": "c177/home", "STABLEMATE_CONFIG": "c177/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c177/pipx-stub-bin:$PATH"})
    - verify: stdout(text="warning: ")
    - fixture: bare-agents-yml dir=c177
  - print an error and warning count summary when findings exist
    - run: invoke(argv=["doctor", "--repo", "c178"], env={"HOME": "c178/home", "STABLEMATE_CONFIG": "c178/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c178/pipx-stub-bin:$PATH"})
    - verify: stdout(text=" error(s), ")
    - fixture: bare-agents-yml dir=c178
- exits:
  - return `0` for a readable mapping, including when it has warnings
    - run: invoke(argv=["doctor", "--repo", "c179"], env={"HOME": "c179/home", "STABLEMATE_CONFIG": "c179/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c179/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: bare-agents-yml dir=c179
  - return `1` when the repository configuration produces an error finding
    - run: invoke(argv=["doctor", "--repo", "c180"], env={"HOME": "c180/home", "STABLEMATE_CONFIG": "c180/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c180/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: empty-dir dir=c180
- code: `farrier/farrier/doctor.py::report` @21fff6ebd077
- detail: [repository diagnosis](concepts/doctor-diagnosis.md)
- tests: `farrier/tests/test_doctor_command.py::test_a_repo_with_no_services_block_is_warned_that_nothing_is_gated`
- tests: `farrier/tests/test_doctor_command.py::test_a_missing_agents_yml_is_the_one_error`
- tests: `farrier/tests/test_doctor_command.py::test_warnings_alone_exit_zero`

`doctor` does not resolve a library, render files, or fail merely because a repository has not
adopted a workflow gate. Its only nonzero result is an unreadable or invalid `agents.yml`.

`doctor` hands the `--repo` path to `doctor.report` and prints what it returns.

### hooks

The hook-wiring behaviour is implemented by `_run_hooks_install` and `_run_hooks_list`, the two
actions of the `hooks` command group.

- usage: `farrier hooks install [--repo DIR] [--dry-run]` and `farrier hooks list [--repo DIR]`
- flags:
  - `--repo <dir>` — repository root whose hook manager is wired or listed. Default: current working
    directory.
  - `--dry-run` — `install` only. Print every action the verb would take, each line prefixed
    `[dry-run] `, and write nothing.
- does:
  - read `<repo>/agents.yml` when it exists, otherwise use an empty configuration
    - run: invoke(argv=["hooks", "install", "--repo", "c181"], env={"HOME": "c181/home", "STABLEMATE_CONFIG": "c181/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c181/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stderr", text="no agents.yml in")
    - fixture: empty-dir dir=c181
  - choose `hooks.manager` when declared as one of `pre-commit`, `lefthook`, `husky`,
    `githooks`, or `none`
    - run: invoke(argv=["hooks", "install", "--repo", "c182"], env={"HOME": "c182/home", "STABLEMATE_CONFIG": "c182/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c182/pipx-stub-bin:$PATH"})
    - verify: created(subject="c182/.husky/pre-commit")
    - fixture: husky-repo dir=c182
  - detect the repository's hook manager from marker files when `hooks.manager` is absent
    - run: invoke(argv=["hooks", "install", "--repo", "c183"], env={"HOME": "c183/home", "STABLEMATE_CONFIG": "c183/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c183/pipx-stub-bin:$PATH"})
    - verify: stdout(text="hooks wired through: pre-commit")
    - fixture: precommit-repo dir=c183
  - reject a declared manager outside the accepted manager vocabulary
    - run: invoke(argv=["hooks", "install", "--repo", "c184"], env={"HOME": "c184/home", "STABLEMATE_CONFIG": "c184/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c184/pipx-stub-bin:$PATH"})
    - verify: stderr(text="is not one of pre-commit, lefthook, husky, githooks, none")
    - fixture: bad-manager-repo dir=c184
  - remove Farrier's fenced hook entry from every supported manager file when the manager is
    `none`
    - run: invoke(argv=["hooks", "install", "--repo", "c185"], env={"HOME": "c185/home", "STABLEMATE_CONFIG": "c185/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c185/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Removed farrier's hook entry from .husky/pre-commit")
    - fixture: fenced-husky-repo dir=c185
  - write the manager-specific fenced entry that delegates to `make farrier-run-hook`
    - run: invoke(argv=["hooks", "install", "--repo", "c186"], env={"HOME": "c186/home", "STABLEMATE_CONFIG": "c186/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c186/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c186/.husky/pre-commit", text="make farrier-run-hook")
    - fixture: husky-repo dir=c186
  - preserve user-owned lines outside Farrier's fenced region
    - run: invoke(argv=["hooks", "install", "--repo", "c187"], env={"HOME": "c187/home", "STABLEMATE_CONFIG": "c187/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c187/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c187/lefthook.yml", text="pre-push:")
    - fixture: user-lefthook-repo dir=c187
  - create missing `husky` and `githooks` shell hook files with an executable preamble
    - run: invoke(argv=["hooks", "install", "--repo", "c188"], env={"HOME": "c188/home", "STABLEMATE_CONFIG": "c188/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c188/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c188/.githooks/pre-commit", text="#!/bin/sh")
    - fixture: githooks-repo dir=c188
  - ensure a newly created pre-commit configuration begins with `repos:`
    - run: invoke(argv=["hooks", "install", "--repo", "c189"], env={"HOME": "c189/home", "STABLEMATE_CONFIG": "c189/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c189/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c189/.pre-commit-config.yaml", matches="^repos:")
    - fixture: precommit-declared-repo dir=c189
  - print messages for changed or removed hook-manager files
    - run: invoke(argv=["hooks", "install", "--repo", "c190"], env={"HOME": "c190/home", "STABLEMATE_CONFIG": "c190/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c190/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Wired `make farrier-run-hook` into .husky/pre-commit")
    - fixture: husky-repo dir=c190
  - print the selected manager as `hooks wired through: <manager>`
    - run: invoke(argv=["hooks", "install", "--repo", "c191"], env={"HOME": "c191/home", "STABLEMATE_CONFIG": "c191/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c191/pipx-stub-bin:$PATH"})
    - verify: stdout(text="hooks wired through: husky")
    - fixture: husky-repo dir=c191
  - perform hook wiring without resolving a library or rendering repository outputs
    - run: invoke(argv=["hooks", "install", "--repo", "c192"], env={"HOME": "c192/home", "STABLEMATE_CONFIG": "c192/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c192/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c192/.agents/agents.mk")
    - fixture: husky-repo dir=c192
  - with `--dry-run`, print each action prefixed `[dry-run] ` and write no file
    - run: invoke(argv=["hooks", "install", "--dry-run", "--repo", "c193"], env={"HOME": "c193/home", "STABLEMATE_CONFIG": "c193/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c193/pipx-stub-bin:$PATH"})
    - verify: stdout(text="[dry-run] Wired `make farrier-run-hook` into .husky/pre-commit")
    - fixture: husky-repo dir=c193
  - with `list`, print each stage followed by the hooks the selected skills declare there, or
    `(none)`
    - run: invoke(argv=["hooks", "list", "--repo", "c194"], env={"HOME": "c194/home", "STABLEMATE_CONFIG": "c194/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c194/pipx-stub-bin:$PATH"})
    - verify: stdout(text="pre-commit:")
    - fixture: husky-repo dir=c194
  - with `list`, print `manager: none — these hooks are not wired` first when the manager is `none`
    - run: invoke(argv=["hooks", "list", "--repo", "c195"], env={"HOME": "c195/home", "STABLEMATE_CONFIG": "c195/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c195/pipx-stub-bin:$PATH"})
    - verify: stdout(text="manager: none — these hooks are not wired")
    - fixture: fenced-husky-repo dir=c195
  - with `list`, refuse a missing, unreadable or non-mapping `agents.yml` with an error on stderr
    - run: invoke(argv=["hooks", "list", "--repo", "c196"], env={"HOME": "c196/home", "STABLEMATE_CONFIG": "c196/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c196/pipx-stub-bin:$PATH"})
    - verify: stderr(text="no agents.yml in")
    - fixture: empty-dir dir=c196
- exits:
  - return `0` after wiring completes, including when no `agents.yml` exists
    - run: invoke(argv=["hooks", "install", "--repo", "c197"], env={"HOME": "c197/home", "STABLEMATE_CONFIG": "c197/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c197/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: husky-repo dir=c197
  - terminate nonzero when `hooks.manager` is invalid
    - run: invoke(argv=["hooks", "install", "--repo", "c198"], env={"HOME": "c198/home", "STABLEMATE_CONFIG": "c198/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c198/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: bad-manager-repo dir=c198
- errors:
  - print the invalid `hooks.manager` value and the accepted manager names when configuration names
    an unsupported manager
    - run: invoke(argv=["hooks", "install", "--repo", "c199"], env={"HOME": "c199/home", "STABLEMATE_CONFIG": "c199/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c199/pipx-stub-bin:$PATH"})
    - verify: stderr(text="svn")
    - fixture: bad-manager-repo dir=c199
- code: `farrier/farrier/cli.py::_run_hooks_install` @0244d6a97e3b
- code: `farrier/farrier/cli.py::_run_hooks_list` @0244d6a97e3b
- detail: [hook manager wiring](concepts/hook-manager-wiring.md)
- tests: `farrier/tests/test_hook_managers.py::test_the_hooks_command_wires_a_repo_whose_packs_do_not_resolve`
- tests: `farrier/tests/test_hook_managers.py::test_the_hooks_command_falls_back_to_detection_with_no_agents_yml`

A legacy whole-file Farrier hook is replaced before the new fenced entry is written. For the `githooks` manager, `hooks install` sets Git `core.hooksPath` to `.githooks`. When a library resolves, it also regenerates `.agents/hooks/pre-commit` from the hooks the selected skills declare. None of the three leaves a trace that a stdout, stderr or working-tree check can name.
