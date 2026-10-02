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
| `packs/stablemate.yml` | the toolchain skills, which a repo opts into with `packs: [stablemate]` |
| `packs/general.yml` | the method skills, the cross-language contracts and the two `implement-plan` commands |
| `agents.example.yml` | an annotated starting `agents.yml` |

[AGENTS.md](AGENTS.md) is the companion to that table: what may be *added* here, and
what ships with the package that reads it instead.

That's the whole payload: markdown, YAML and a few standalone helper scripts that a
skill ships beside its `SKILL.md`. There is no `__init__.py`, no `pyproject.toml` and
no dependency. Workflows are distributed
separately as [`workhorse-workflows`](../workflows/), and an optional overlay may
also provide `scaffolds/` for farrier to apply.

## How the tools find it

They look, in order, for `$STABLEMATE_BASE_DIR` → the `base_dir` config key → a
configured `stablemate_dir` checkout (`<checkout>/base-library`, i.e. this directory) →
a shared cache. If no base is found, an explicitly configured overlay can still operate
alone.

The cache is the interesting one: it is **fetched from GitHub into the user cache
directory** (`~/.cache/stablemate` on Linux, or `$STABLEMATE_CACHE_DIR`)
and used from there — a sparse checkout of this directory alone, with `.git` dropped once
the commit is recorded, so what lands is documents rather than a repository.
`farrier install` is what populates it, and the only thing that updates it: on install the
base is fetched if absent and moved to the installed farrier's release tag if stale (`main` for a farrier installed
from a checkout). Every other caller — every
lookup, and every workhorse resume — reads it frozen, so a run cannot resume into a
different library than it started with. See the
[docs/INSTALL.md](../docs/INSTALL.md#finding-the-base-library).

A directory counts as a library if it holds `library/`. That is the whole contract;
`stablemate_core.layout.is_library_dir` is the one implementation of it.

## Layering

The base is the **lowest-precedence** library layer. farrier renders content across a
search path, and workhorse looks for coder-turn overrides across the same one (see
[overriding a coder-workflow turn](#overriding-a-coder-workflow-turn-librarypromptscoder)
— a workflow's own prompts stay in its wheel):

```
1. --library / $FARRIER_LIBRARY_DIR  (explicit override)
2. the configured overlay            (farrier config set-library <dir>)
3. this content                      (the base)
```

An overlay shadows the base name-for-name: define a skill or pack with the
same id and yours wins. So a private library can extend the base without forking it, and
the base can be absent entirely (the tools fall back to overlay-only behaviour).

## Overriding a coder-workflow turn (`library/prompts/coder/`)

**The base ships none of these, and that is the design.** A workflow distribution is
standalone: `workhorse-workflows` is installed on its own, every prompt it renders is
inside its wheel, and a machine that never ran farrier runs every story end to end. If the
defaults lived here, an optional install would be load-bearing for every turn. The rest of
`library/prompts/` is the other thing. It holds commands for the *person* using farrier,
and a repo gets one as a slash command when a pack selects it.

In an **overlay**, this directory is an override slot. Each coder turn is two
halves: the *envelope* (`coder/<flow>/prompts/<role>.md`, in the workflow's own
distribution — one copy per flow that renders it)
renders the inputs, the exit condition and the result schema the state machine parses
back, and it pulls a *body* in with `{% include body_template %}`. The envelope is a
contract the state machine reads its own replies against, so a repo editing it would be
editing the parser. The body is how the job is done *here* — the part that knows a stack, a
test runner and a house style — so it is exactly the part a repo must be able to replace.
Drop `library/prompts/coder/<role>.md` into an overlay and that role's body becomes yours.

Resolution order, highest first: the repo's `agents.yml`
(`prompts: {dev-fix: prompts/fix-go-tests.md}`), then each library layer above, then the
default the workflow shipped. Resolving nothing is the ordinary case, not a failure.

They are not installable prompts. Nothing selects `coder/*` in a pack, and a repo that
listed it would get a slash command whose text addresses a workflow turn. Their audience
is `workhorse_workflows.coder.shared.roles`, and that module is the list of roles.

## No dependencies, in either direction

This directory declares no dependencies because it is data. Workflow tools belong in
the workflow distribution's `dependencies = [...]`, where `pip` and `uv` resolve them.
No dependency runs from the library to the tools or back, so content can version on its
own clock without forcing a package release.

## Versioning

There is no version number of its own. `farrier install` fetches the library at
farrier's release tag, `farrier-v<version>`, or at `main` for a farrier installed from
a checkout. What lands is a commit, and `cat ~/.cache/stablemate/library/.commit` says
which one. (There is no `.git` in the
cache to `rev-parse`; the fetch writes that sidecar instead.)

The **layout contract** (`library/skills/<group>/<name>/SKILL.md`, `packs/<pack>.yml`)
is what the tools depend on; changing it is a breaking change to them, not to a version
string here. `farrier/docs/LAYOUT.md` in this workspace is where that contract is
written down.
