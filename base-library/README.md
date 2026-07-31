# The stablemate base library

**The scaffolds and toolchain skills that ship with stablemate. This is data, not a
package — there is nothing here to install or import.**

```bash
farrier install              # fetches this content on first use, then renders it
```

## What's in it

| Path | Contents |
|---|---|
| `scaffolds/` | the definitions `farrier scaffold <id>` applies |
| `library/skills/stablemate/` | the skills documenting the toolchain |

That's the whole payload — markdown and YAML, and **not a line of Python**. No
`__init__.py`, no `pyproject.toml`, no dependencies, nothing executable.

It used to hold `workflows/` too: four directories of workflow YAML plus the
`scripts/*.py` its nodes ran. A workflow is a Python package now, resolved through the
`workhorse.workflows` entry-point group and shipped in a wheel — so the code left, and
what stayed is documents.

## How the tools find it

They look, in order, for `$STABLEMATE_BASE_DIR` → the `base_dir` config key → a
configured `stablemate_dir` checkout (`<checkout>/base-library`, i.e. this directory) →
a shared cache. Nothing found means overlay-only, exactly as before a base existed.

The cache is the interesting one: with none of the above set, the tools **fetch this
content from GitHub into `~/.cache/stablemate`** and use it from there — a sparse
checkout of this directory alone, with `.git` dropped once the commit is recorded, so
what lands is documents rather than a repository. It is fetched once and then frozen —
`rm -rf ~/.cache/stablemate` is the upgrade path. See the
[monorepo README](../README.md#installing).

A directory counts as a library if it holds `library/`. That is the whole contract;
`stablemate_core.layout.is_library_dir` is the one implementation of it.

## Layering

The base is the **lowest-precedence** library layer. farrier and workhorse both resolve
content across a search path:

```
1. --library / $FARRIER_LIBRARY_DIR  (explicit override)
2. the configured overlay            (farrier config set-library <dir>)
3. this content                      (the base)
```

An overlay shadows the base name-for-name: define a skill or pack with the
same id and yours wins. So a private library can extend the base without forking it, and
the base can be absent entirely (the tools fall back to overlay-only behaviour).

## No dependencies, in either direction

This directory used to be a wheel that pinned `workhorse-agent`, `farrier` and `ostler`.
That was wrong, and the pin was load-bearing wrongness: it closed a dependency cycle,
broke `--no-deps` installs, and made "fetch the content when it's missing"
unimplementable.

The tools those workflows need are real, but they were declared at the wrong level.
Needing `ostler` is a property of **running** a workflow, not of **having** the library.
While workflows were YAML in here, each `workflow.yaml` declared its own in a `requires:`
block that workhorse checked before the first node ran — a hand-rolled dependency
manifest, because data cannot have dependencies.

Workflows are a Python package now
([`workhorse-workflows`](../workflows/)), so that need is an ordinary
`dependencies = [...]` entry that `pip` and `uv` resolve. Nothing in this directory
declares anything. With no dependency running in either direction, content versions on
its own clock: a reworded prompt never drags a tool release behind it.

## Versioning

There is no version number — this is git. What you get is a commit, and
`cat ~/.cache/stablemate/library/.commit` says which one. (There is no `.git` in the
cache to `rev-parse`; the fetch writes that sidecar instead.)

The **layout contract** (`library/skills/<group>/<name>/SKILL.md`,
`scaffolds/<id>.yml`) is what the tools depend on; changing it is a breaking change to
them, not to a version string here.
