# The stablemate base library

**The skills and commands that ship with stablemate, and the packs that select them.
This is data, not a package. There is nothing here to install or import.**

```bash
farrier config set-base /path/to/this/directory   # this directory itself
farrier config set-stablemate /path/to/checkout   # or the stablemate checkout around it
farrier install                                   # renders it into a repo
```

## What's in it

| Path | Contents |
|---|---|
| `library/skills/{farrier,groom,ostler,workhorse}/` | the skills documenting the toolchain |
| `library/skills/method/` | ways of working that hold in any repo: decompose, grill, review, diagnose |
| `library/skills/{architecture,testing,ui}/` | the cross-language contracts |
| `library/prompts/` | the `implement-plan-worktree` and `implement-plan-here` commands |
| `library/prompts/stablemate/` | the `babysit-run` command, which no pack selects yet |
| `packs/stablemate.yml` | the toolchain skills, which `farrier init` proposes for the user library |
| `packs/general.yml` | the method skills, the cross-language contracts and the two `implement-plan` commands |
| `agents.example.yml` | an annotated starting `agents.yml` |

[AGENTS.md](AGENTS.md) is the companion to that table: what may be *added* here, and
what ships with the package that reads it instead.

That's the whole payload: markdown, YAML and a few standalone helper scripts that a
skill ships beside its `SKILL.md`. Workflows are distributed separately as
[`workhorse-workflows`](../workflows/).

## How the tools find it

A directory counts as a library if it holds `library/`. Without a path you configured,
`farrier install` fetches this directory from GitHub into a shared cache, at farrier's
release tag. [docs/INSTALL.md](../docs/INSTALL.md#finding-the-base-library) gives the
lookup order and how the cache updates.

## Layering

The base is the **lowest-precedence** library layer. farrier renders content across a
search path, and workhorse looks for coder-turn overrides across the same one:

```
1. --library / $FARRIER_LIBRARY_DIR  (explicit override)
2. the configured overlay            (farrier config set-library <dir>)
3. this content                      (the base)
```

An overlay shadows the base name-for-name: define a skill or pack with the
same id and yours wins. So a private library can extend the base without forking it, and
the base can be absent entirely (the tools fall back to overlay-only behaviour). An
overlay may also provide `scaffolds/` for farrier to apply.

## Overriding a coder-workflow turn (`library/prompts/coder/`)

The base ships no coder-turn prompts. A coder turn renders a body that says how the job
is done in your repo: its stack, its test runner, its house style. Drop
`library/prompts/coder/<role>.md` into an overlay and that role's body becomes yours.
The roles are listed in
[`roles.py`](../workflows/src/workhorse_workflows/coder/shared/roles.py).

Resolution order, highest first: the repo's `agents.yml`
(`prompts: {dev-fix: prompts/fix-go-tests.md}`), then each library layer above, then the
default the workflow shipped. Resolving nothing is the ordinary case, not a failure.

## Versioning

There is no version number of its own. `farrier install` fetches the library at
farrier's release tag, `farrier-v<version>`, or at `main` for a farrier installed from
a checkout. What lands is a commit, and `cat ~/.cache/stablemate/library/.commit` says
which one. The layout contract is
[`farrier/docs/LAYOUT.md`](../farrier/docs/LAYOUT.md).
