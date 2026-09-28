# farrier

The package behind the `farrier` command. It renders the layered prompt library into a repository's agent adapters, git hooks and `.agents/` launcher.

## Map

- `cli.py`: argument parsing and verb dispatch for the `farrier` command, including finding the repo's `agents.yml`.
- `doctor.py`: what a repo's `agents.yml` leaves a workflow unable to do, and the advice `farrier doctor` prints.
- `drift.py`: the report `--check` prints when a generated file no longer matches its source.
- `frontmatter.py`: parsing YAML front matter and banners, and reading the `localInstructions` entries of `agents.yml`.
- `hook_managers.py`: wiring farrier's pre-commit runner into the repo's hook manager through a fenced block.
- `hooks.py`: the managed QA-evidence `.gitignore` block that ships with the staged-files gate.
- `init.py`: the starter `agents.yml` that `farrier init` writes.
- `install.py`: the console-script entry point and the module's public re-exports.
- `launcher.py`: the generated `.agents/agents.mk` launcher and the launcher file paths.
- `layers.py`: the library layer stack, overlay before base, and which layer answers a lookup.
- `library_check.py`: front-matter validation of a library's skills and prompts.
- `library_view.py`: the read side of the layer stack: the catalog of items and the text of one item.
- `naming.py`: pure name transforms: kebab case, prefixes, source ids and quoting.
- `outputs.py`: the full render run and the repo writes that install it: conflicts, sweeps, `.gitignore` and Makefile edits.
- `ownership.py`: which files farrier generated, so it may delete them and must not overwrite others.
- `pipx.py`: which workflows this machine can run, according to `pipx list`.
- `renderer.py`: turning one library source into the adapter text each agent harness expects.
- `scaffolds.py`: scaffold definitions: loading, params, tree flattening and fetching.
- `selection_errors.py`: the one error message for an `agents.yml` entry the library does not have.
- `skill_hooks.py`: a skill's `hooks:` declaration of a script that must run at a git hook.
- `sources.py`: the `Source` record, loading sources across layers, and resolving packs into a selection.
- `template_values.py`: merging `vars:` and `template:` from `agents.yml` into one mapping.
- `user_library.py`: the `[user_library.*]` config tables a user installs for every project.
