# The stablemate base library

**The workflows, scaffolds and toolchain skills that ship with stablemate. This is
data, not a package — there is nothing here to install or import.**

```bash
workhorse run coder          # fetches this content on first use, then runs it
```

## What's in it

| Path | Contents |
|---|---|
| `workflows/` | the workflow graphs `workhorse run <name>` executes |
| `scaffolds/` | the definitions `farrier scaffold <id>` applies |
| `library/skills/stablemate/` | the skills documenting the toolchain |

That's the whole payload — markdown, YAML, and the Python scripts workflow nodes run.
No `__init__.py`, no `pyproject.toml`, no dependencies.

## How the tools find it

They look, in order, for `$STABLEMATE_BASE_DIR` → the `base_dir` config key → a
configured `stablemate_dir` checkout (`<checkout>/base-library`, i.e. this directory) →
a shared cache. Nothing found means overlay-only, exactly as before a base existed.

The cache is the interesting one: with none of the above set, the tools **clone this
content from GitHub into `~/.cache/stablemate`** and use it from there. It is fetched
once and then frozen — `rm -rf ~/.cache/stablemate` is the upgrade path. See the
[monorepo README](../README.md#installing).

A directory counts as a library if it holds `library/` or `workflows/`. That is the
whole contract; `stablemate_core.layout.is_library_dir` is the one implementation of it.

## Layering

The base is the **lowest-precedence** library layer. farrier and workhorse both resolve
content across a search path:

```
1. --library / $FARRIER_LIBRARY_DIR  (explicit override)
2. the configured overlay            (farrier config set-library <dir>)
3. this content                      (the base)
```

An overlay shadows the base name-for-name: define a skill, pack or workflow with the
same id and yours wins. So a private library can extend the base without forking it, and
the base can be absent entirely (the tools fall back to overlay-only behaviour).

## No dependencies, in either direction

This directory used to be a wheel that pinned `workhorse-agent`, `farrier` and `ostler`.
That was wrong, and the pin was load-bearing wrongness: it closed a dependency cycle,
broke `--no-deps` installs, and made "fetch the content when it's missing"
unimplementable.

The tools those workflows need are real, but they were declared at the wrong level.
Needing `ostler` is a property of **running** a workflow, not of **having** the library —
so each `workflow.yaml` declares its own, and workhorse checks them before the first node
runs:

```yaml
requires:
  - dist: ostler          # importable by the interpreter that runs script nodes
    version: ">=0.1.0"
```

See [workhorse/docs/WORKFLOW.md](../workhorse/docs/WORKFLOW.md#11-requires--declaring-the-tools-a-workflow-uses).
With no dependency running in either direction, content versions on its own clock: a
reworded prompt never drags a tool release behind it.

## Versioning

There is no version number — this is git. What you get is a commit, and
`git -C ~/.cache/stablemate/library rev-parse HEAD` says which one.

The **layout contract** (`library/skills/<group>/<name>/SKILL.md`,
`workflows/<name>/workflow.yaml`) is what the tools depend on; changing it is a breaking
change to them, not to a version string here.
