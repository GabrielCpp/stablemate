# Ambient path threading — `repo_dir`, `docs_path`, `workspace_file`

The three are run **inputs**, listed once as `paths.AMBIENT` and declared as the class's
`injects`. A node that needs one just declares a parameter of the same name; `self.call`
and `self.handoff` fill it from the workflow, so the ordinary callsite says nothing. A
callsite value always wins, and an empty field injects nothing, so the target's own default
stands. None of them is ever read from the environment — that is prohibited across every
workflow (`workflows/README.md`, and the `workhorse-scripting` skill) and
enforced by `make check-no-env`; the CLI translates `$FOO` into `--params` at the process
boundary instead.

`paths.py` keeps **three** repo-root resolvers on purpose, because the YAML's scripts did not
agree and the disagreement is behavioral: a run launched from a subdirectory, or from a repo
whose `docs/epics/` exists but whose `.git` does not, lands on a different root under each.
Each takes `repo_dir` first and only falls back to a `cwd` walk when it is empty. Call the
one the node's semantics need:

| Resolver | Marker when `repo_dir` is empty | Used by |
|---|---|---|
| `kit.find_repo_root(repo_dir)` | `agents.yml`/`.git` upward from `cwd` | the consuming code repo |
| `paths.epics_repo_root(repo_dir)` | `agents.yml` or a `docs/epics/` **directory** | `prune_epic` — a docs checkout with no `.git` still gets its queue popped |
| `paths.launch_repo_root(repo_dir)` | `cwd` if project-shaped, else upward | the operator gates — its `cwd`-first probe is what lets a test point a gate at a sandbox by chdir alone |

Docs specifically: `find_docs_root(docs_path, repo_dir)` from `workhorse_workflows.kit` — the
explicit path when given, else the repo root, i.e. docs beside the code.

