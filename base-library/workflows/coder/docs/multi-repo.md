# Multi-Repo Operation Guide

The coder workflow supports both mono-repo and multi-repo workspaces. This guide covers configuration, operating modes, and the planner contract for multi-repo stories.

## Configuration

### Workspace File (Optional)

A VSCode `.code-workspace` file provides the list of repo paths. Its location is passed via an environment variable.

```json
{
  "folders": [
    { "name": "api-service", "path": "api-service" },
    { "name": "vigilant-octo", "path": "../workspace-other/vigilant-octo" },
    { "name": "web-app", "path": "web-app" },
    { "name": "mobile-app", "path": "mobile-app" }
  ]
}
```

Scripts resolve relative paths against the workspace file's parent directory.

### Workspace Environment Variable

The coder workflow reads the workspace-file path from a single, fixed env var: **`CODER_WORKSPACE`**. Its value is the path to the `.code-workspace` file. When unset (or the file is missing), scripts fall back to CWD as a single-folder (mono-repo) workspace.

### Checkout Is Automatic, Not a Workflow Step

Cloning/updating every `url`-bearing folder listed in the workspace file happens once,
before the workflow graph starts — `entrypoint.sh` invokes
`workhorse.scriptutil.checkout_workspace()` as part of container startup. Neither
`coder/workflow.yaml` nor `author/workflow.yaml` has (or needs) a `setup` node; by the
time the graph runs, every folder's working tree already exists under
`/workspace/<folder name>`. Folders without a `url` (e.g. a plain documentation
directory that isn't a git repo) are left untouched by checkout — their content only
reaches the container via the optional workspace-directory bind mount in
`workhorse/compose.yaml` (`WORKSPACE_DIR_HOST`), not a clone.

The orchestrating repo only needs to forward `CODER_WORKSPACE` into the run environment:

```yaml
# vigilant-octo/agents.yml
workflow:
  coder:
    envPassthrough:
      - CODER_WORKSPACE
```

The operator sets it before running:

```bash
export CODER_WORKSPACE=/path/to/example.code-workspace
```

### Per-Repo `agents.yml` — `workspace:` Section

Each repo declares its service structure in a `workspace:` section of its `agents.yml`:

```yaml
# api-service/agents.yml
workspace:
  type: go-monorepo
  service_roots: ["cmd/*"]
  infra_roots: ["tf/modules/apps/*"]
  service_markers: ["main.go"]
  qa_mode: cli
  qa_skills: [qa-api-service-cli, qa-api-service-local]
  verification: "api-service status --build --format --lint --modules"
```

**Fields:**

| Field             | Description                               | Example                                               |
| ----------------- | ----------------------------------------- | ----------------------------------------------------- |
| `type`            | Identifier for the repo layout            | `go-monorepo`, `svelte-monorepo`, `flutter-app`       |
| `service_roots`   | Glob patterns for where services live     | `["cmd/*"]`, `["packages/*"]`, `["."]`                |
| `infra_roots`     | Glob patterns for infra modules           | `["tf/modules/apps/*"]`                               |
| `service_markers` | Files that prove a directory is a service | `["main.go"]`, `["package.json"]`, `["pubspec.yaml"]` |
| `qa_mode`         | QA modality                               | `cli`, `playwright`, `maestro`                        |
| `qa_skills`       | Skill names loaded during QA              | `[qa-api-service-cli, qa-api-service-local]`                  |
| `verification`    | Build/lint/test command                   | `"api-service status --build --format --lint --modules"`  |

---

## Operating Modes

### No Workspace File (Mono-Repo)

If the workspace env var is unset or empty, the script treats CWD as a single-folder workspace. The planner sees one repo with its own `agents.yml` and discovers services from `service_roots`.

This is the default — no extra configuration needed for mono-repo workflows.

### With Workspace File (Multi-Repo)

When the workspace file is set:

1. **Planning**: The planner decides which repos/services are relevant, and outputs `plan-context.json` with the `services` array
2. **Validation**: `validate-plan-context.py` confirms each service path exists and has the expected marker file
3. **Implementation**: The layer loop iterates over services, setting CWD to each service's repo for the implement agent
4. **Review**: Holistic review with `add_dirs` access to all affected repos
5. **QA**: Mode-aware QA (cli/playwright/maestro × local/dev)
6. **Git**: Multi-repo branching, committing, and PR creation with cross-references

---

## Planner Contract

### `plan-context.json` Schema

```json
{
  "services": [
    {
      "repo": "api-service",
      "path": "cmd/alert",
      "type": "go",
      "skills": ["api-service", "api-service-grpc", "api-service-events"],
      "plan_file": "plan-api-service-alert.md"
    }
  ],
  "implementation_order": ["api-service::cmd/alert", "web-app::packages/discover"],
  "shared_packages": [
    { "repo": "api-service", "path": "pkg/db/alert", "type": "go-lib" }
  ],
  "required_instructions": ["api-service", "api-service-grpc", "web-app"],
  "qa_stack": {}
}
```

### `repo::path` Notation

Service paths use `repo::path` format for unambiguous identification:

- `api-service::cmd/alert` — the alert service in the api-service repo
- `web-app::packages/discover` — the discover app in the web-app repo
- `mobile-app::.` — the root Flutter app in mobile-app

### Implementation Order Rules

Dependencies must be implemented first:

1. Proto/API definitions
2. Backend services (Go)
3. Infrastructure (Terraform)
4. Frontend (Svelte)
5. Mobile (Flutter)

### Per-Service Plan Files

Each service gets its own plan file:

- Single-service: `plan.md` (root is the only plan)
- Multi-service: `plan.md` (root overview) + per-service files (e.g., `plan-api-service-alert.md`, `plan-web-app-discover.md`)

---

## QA Modes

### Target Environment

| `target_env` | When                            | Stack Setup                       | Skills                              |
| ------------ | ------------------------------- | --------------------------------- | ----------------------------------- |
| `local`      | Your own story, running locally | Required (localstack, dev server) | `qa-api-service-local`, local endpoints |
| `dev`        | Someone else's story on DEV     | None — already deployed           | `qa-api-service-cli`, DEV endpoints     |

### Per-Modality Behavior

| `qa_mode`    | Tools                                       | Typical Repo |
| ------------ | ------------------------------------------- | ------------ |
| `cli`        | grpcurl, koios, phi, curl, eventbridge-tail | api-service      |
| `playwright` | Playwright browser automation               | web-app       |
| `maestro`    | Maestro YAML flows via semantics tree       | mobile-app       |

### Multi-Service QA

Every affected repository is passed to `ostler qa context` as a named source root. One
mandatory `<spec_dir>/qa-plan.yml` contains all command, Playwright, and Maestro targets;
Ostler orders and executes the scenarios and owns their common ledger/manifest/evidence.
The interpreting agent does not run a modality directly.

---

## Git Operations

### Branching

All affected repos get the same branch name: `story/<slug>`.

```bash
# scripts/branch-multi-repo.py creates:
# api-service:         story/persist-profile
# web-app:          story/persist-profile
# vigilant-octo:   story/persist-profile
```

### Committing

`commit-multi-repo.py` stages and commits in each repo that has changes. Repos with no changes are skipped.

### Pull Requests

`open-multi-repo-pr.py` pushes and opens PRs in each committed repo. PRs include cross-references as comments linking to sibling PRs in other repos.

---

## Troubleshooting

### Validation gate rejected my plan

The `validate-plan-context.py` script checks:

1. **Repo exists in workspace** — verify the `repo` field matches a folder name in the workspace file
2. **Service path exists** — check the directory actually exists at `<repo_root>/<path>`
3. **Service marker present** — confirm the directory contains the expected file (`main.go`, `package.json`, etc.)
4. **Plan file written** — verify the plan file was written to the spec dir

Fix the planner output and re-run.

### Workspace env var not set

Expected behavior: scripts fall back to CWD as a single-folder workspace. The story runs against one repo only.

### Repo in workspace has no `agents.yml`

Repos without `agents.yml` are included in the workspace resolution but have no service metadata. The planner should not select services from repos without `agents.yml` — validation will fail since there are no service markers defined.

---

## Migration from Old Format

The old `plan-context.json` format (`touched_layers`, `LAYER_META`) is removed. This is a breaking change.

**What to do:**

1. Delete any existing `plan-context.json` files using the old format
2. Re-plan affected stories — the planner now outputs the `services` array format
3. Create `agents.yml` in each repo with the `workspace:` section
4. Set the workspace env var (or run without it for mono-repo)

**What was removed:**

- `LAYER_META` dict in `resolve-impl-context.py`
- `touched_layers` field in `plan-context.json`
- Technology-category layer keys (`go`, `react-router`, `flutter`, `pulumi`)
- Per-technology plan file names (`plan-go.md`, `plan-web.md`, `plan-mobile.md`)

**Replaced by:**

- Per-repo `agents.yml` `workspace:` section for metadata
- `services` array with concrete `repo::path` entries
- Per-service plan files named by repo and service (e.g., `plan-api-service-alert.md`)
