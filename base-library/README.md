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
| `library/skills/{farrier,groom,ostler,saddlebag,workhorse}/` | the skills documenting the toolchain |
| `library/skills/method/` | ways of working that hold in any repo: decompose, grill, review, diagnose |
| `library/skills/{architecture,testing,ui}/` | the cross-language contracts |
| `packs/stablemate.yml` | the toolchain skills, which `farrier init` proposes for the user library |
| `packs/general.yml` | the method skills and the cross-language contracts |
| `agents.example.yml` | an annotated starting `agents.yml` |

[AGENTS.md](AGENTS.md) is the companion to that table: what may be *added* here, and
what ships with the package that reads it instead.

That's the whole payload: markdown, YAML and a few standalone helper scripts that a
skill ships beside its `SKILL.md`. Workflows are distributed separately as
[`workhorse-workflows`](../workflows/).

## How the tools find it

A directory counts as a library if it holds `library/`. farrier ships this directory
inside its wheel. Without a path you configured, farrier renders that copy, and
`farrier install` mirrors it into a shared cache for the tools that do not ship it.
[docs/INSTALL.md](../docs/INSTALL.md#finding-the-base-library) gives the lookup order
and how the cache updates.

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

There is no version number of its own. Each farrier release carries the library as it
stood at that release, so the library version is the farrier version. A change here
releases farrier, because `make vendor` stamps its digest into
`farrier/farrier/_vendor/base_library.sha256`. `cat ~/.cache/stablemate/library/.digest`
says which copy the cache holds. The layout contract is
[`farrier/docs/LAYOUT.md`](../farrier/docs/LAYOUT.md).
