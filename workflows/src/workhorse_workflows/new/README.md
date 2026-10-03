# new

The `workhorse-new` command. It is not a workflow. It writes one: a standalone distribution whose single agent turn loops until a shell check exits 0.

## Map

- `scaffold.py`: the `workhorse-new` command, which renders `template/` into `./NAME`.
- `template/`: the files a new workflow starts from. `package/` becomes `src/<package>/`, and `pyproject.toml.tmpl` becomes `pyproject.toml`.
- `template/package/workflow.py`: the `CheckLoop` states and the `run_check` node every scaffolded workflow starts with.
