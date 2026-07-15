# Repo Modes: Mono-Repo vs Multi-Repo — Intended Behavior

This is the canonical description of how the coder workflow reasons about "which
repo(s) am I touching" and "where do my docs live". Read this before changing any
`cwd:`/`add_dirs:` on an agent node, or any script that resolves repo paths
(`resolve-impl-context.py`, `resolve-review-context.py`, `scriptutil.resolve_workspace`,
`find_repo_root`, `find_docs_root`).

## The two modes

**Mono-repo mode.** Workhorse has all services _and_ the docs folder in the same
repository — one root to rule them all. `CODER_WORKSPACE` is unset. The workflow's
CWD is the root of that one repo, and stays there for the whole run.

**Multi-repo mode.** Workhorse consumes a VSCode `.code-workspace` file, whose path
comes from the `CODER_WORKSPACE` env var. That file lists every repo path the run
supports (see `multi-repo.md` for the file format and the per-repo `agents.yml`
`workspace:` section). `resolve_workspace()` in `workhorse.scriptutil` is what reads
it and returns `{repo_name: {path, ...}}`.

## The docs root is a separate concept from "a workspace folder"

The docs root (`docs_path`) is **not** just another entry in the workspace-folder
list, and it has none of the guarantees a service repo has:

- It **may or may not** be one of the folders listed in the `.code-workspace` file.
- It **may or may not** be a git repository at all.
- There is **no guarantee** it has an `agents.yml` at its root (so
  `resolve_workspace()`'s per-folder `agents.yml` merge may simply not apply to it).

What _is_ guaranteed: every artifact the workflow generates for **any** repo —
`story.md`, `plan-context.json`, `plan*.md`, `review.json`, `qa.json`, QA evidence —
is written under the docs root (`docs/specs/<slug>/`, `docs/epics/<epic>/stories/<slug>/`).
Every agent node that needs to read or write those files needs filesystem access to
the docs root, regardless of mode.

**Consequence for path resolution:** don't infer the docs root by walking up from
CWD looking for `.git` or `agents.yml` (`find_repo_root()`'s fallback path) — that
heuristic assumes markers that a bare documentation directory is not required to
have. The only trustworthy source is the explicit `docs_path` var (or its
`AGENT_REPO_DIR`-env fallback when `docs_path` is empty — see
`find_docs_root(docs_path)` in `workhorse.scriptutil`). A script that needs the docs
root should receive `docs_path` as an explicit argument and call `find_docs_root()`
with it, the same way `prepare-story.py` does — not re-derive it independently.

## The affected-repos list is not always available

The planner produces a list of affected repos (`plan-context.json`'s `services`
array, reduced to repo names by `get_affected_repos()`):

- **Mono-repo mode:** always resolves inside the one repo, as one or many
  subfolders (the services).
- **Multi-repo mode:** a subset of the workspace's repos.

**You cannot rely on this list always being present or accurate**, because a flow
can be invoked standalone (see below) without ever running the planner — there may
be no `plan-context.json` at all. Every consumer of `affected_repos` /
`affected_repo_paths` must degrade gracefully (empty list, or a single fallback
repo) rather than assume the planner ran in this invocation. `build_dispatch_list()`
already does this (`fallback=` parameter); any new consumer of the affected-repos
data must do the same.

## What a "flow" is

A **flow** (`flows: <name>: ...` in `workflow.yaml`) is a modular subunit of the
workflow — a self-contained subgraph with its own `vars:`, `start:`, and `nodes:`.
It can be:

1. **Invoked as part of the main pipeline** — the parent graph populates the flow's
   `vars` from `get_node_output()`/parent-var references in its `args:` block (e.g.
   `dev`, `review`, `qa` invoked from the top-level story/epic pipeline).
2. **Invoked standalone** — `workhorse run coder <flow-name> --params '{...}'`. Its
   own `prepare_story` (or equivalent) node resolves `story_path`/`spec_dir` from
   just the `story` slug (+ optional `docs_path`/`epic`), so a standalone run needs
   only the minimal params. See `WORKFLOW.md`'s "Standalone Flow Invocation" section
   for exact commands.

Because a flow must work both ways, its own `vars:` block is the single source of
truth for what it needs — never assume a var/output produced by a _different_ flow
or by the parent pipeline is available; a standalone run never executed that node.

## Practical checklist when touching cross-repo access

- [ ] Does this node's `cwd` differ from the docs root? If so, it needs `add_dirs`
      including the docs root — sourced from `docs_path`/`find_docs_root()`, not a
      cwd-walk heuristic.
- [ ] Does this node's `cwd` differ from _other_ affected repos it needs to read
      (e.g. a cross-repo reference)? Same treatment via `affected_repo_paths`.
- [ ] Does the node (or the script that computes its `add_dirs` input) assume
      `plan-context.json` exists? If this flow is standalone-invokable, it must not.
- [ ] Is the new/changed output key added to the node's `outputs:` list? Workhorse
      only threads through explicitly declared output keys — see
      `workhorse/runner/script.py`'s `_extract_outputs`.
