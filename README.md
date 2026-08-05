# stablemate

[![CI](https://github.com/GabrielCpp/stablemate/actions/workflows/ci.yml/badge.svg)](https://github.com/GabrielCpp/stablemate/actions/workflows/ci.yml)
[![workhorse-agent](https://img.shields.io/pypi/v/workhorse-agent?label=workhorse-agent)](https://pypi.org/project/workhorse-agent/)
[![farrier](https://img.shields.io/pypi/v/farrier?label=farrier)](https://pypi.org/project/farrier/)
[![ostler](https://img.shields.io/pypi/v/ostler?label=ostler)](https://pypi.org/project/ostler/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A [uv](https://docs.astral.sh/uv/) workspace housing the publishable Python
packages that work alongside an agent prompt library:

| Package | PyPI | Role |
| --- | --- | --- |
| [`workhorse/`](workhorse/) | [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) | Fail-soft engine (a library, not a command) that drives an agent CLI — Claude, Codex or Copilot — through a checkpointed Python state machine, unattended for days. |
| [`workflows/`](workflows/) | [`workhorse-workflows`](https://pypi.org/project/workhorse-workflows/) | The workflows themselves — `hello-world`, `author`, `coder`, `okf-builder`, `research` — as Python, each declaring its own `workhorse-<name>` command. |
| [`farrier/`](farrier/) | [`farrier`](https://pypi.org/project/farrier/) | Renders an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters and launcher. |
| [`ostler/`](ostler/) | [`ostler`](https://pypi.org/project/ostler/) | Tends a repo's `docs/` knowledge graph — the CLI several base workflows shell out to. |
| [`groom/`](groom/) | — (unpublished) | Local dashboard + OTLP collector for running workflows: answers operator gates from the browser and pages you when a run stalls. Optional. |
| [`saddlebag/`](saddlebag/) | `saddlebag` (unpublished) | Credentials and environment manifests a workflow needs at run time, kept out of the repo. Optional. |
| [`core/`](core/) | — (vendored, never published) | Shared plumbing the tools must agree on: the home config, base-library discovery, the base-library cache. `make vendor` copies it into `workhorse` and `farrier`, which ship it inside their own wheels; there is nothing to install. |

And two directories that are **not** packages:

| Directory | Role |
| --- | --- |
| [`base-library/`](base-library/) | The **base library**: the skills farrier renders, and the packs that select them. Plain data — `library/`, `packs/` — markdown and YAML, with nothing to import and no dependencies. Tools find it on disk, by path. |
| [`benchmarks/`](benchmarks/) | Scores a workflow chain's output against a backlog of user-observable bullets — one number, comparable across runs. Run with `uv run python benchmarks/bench.py score`. |

Library content resolves across two layers: the **base** (`base-library/`, above) and an
optional private **overlay** that shadows it name-for-name. Point a repo at an overlay
with:

```bash
farrier config set-library /path/to/the/overlay
```

You never install the base — see [Installing](#installing). Because it is data rather
than a distribution, nothing depends on it in either direction, so content versions on
its own clock; the tools a workflow needs are declared by the workflow's own package.

## Installing

Install the engines. **The base library is not something you install** — it is content,
and a tool fetches it on demand (see
[Finding the base library](#finding-the-base-library)).

Everything a workflow needs travels with the workflow package. `workhorse-workflows`
declares the engine and the tools its workflows import — `workhorse-agent`, `ostler` — as
ordinary dependencies, so one install lands the lot and puts all five `workhorse-<name>`
commands on your `PATH`:

```bash
uv tool install workhorse-workflows     # or: pipx install workhorse-workflows
uv tool install farrier                 # renders the library into a repository
workhorse-hello-world run --dry-run     # the install check; needs no agent CLI
```

That last line is the whole install check — see [Your first run](#your-first-run). The
other workflows are `author`, `coder`, `okf-builder` and `research`, and they want a
repository and an agent CLI.

`farrier` is a second `uv tool install` rather than a `--with farrier` on the first,
because a tool install only exposes the entry points of the package you *named*: `--with`
would put farrier in that venv and leave its command unreachable. `ostler` needs no line
of its own — it arrives inside the workflows venv, which is the only place it has to be.
Install it separately (`uv tool install ostler`) only if you want to run it by hand.

That "inside the workflows venv" part is not incidental. Workflow code runs **in
workhorse's own interpreter** and imports its tools in-process, so `ostler` on your `PATH`
from some other venv is not enough — it has to be importable *there*. Declaring it a
dependency of `workhorse-workflows` is what makes the venv that runs a workflow the same
venv that has it. See [Tools a workflow needs](#tools-a-workflow-needs).

**Working on stablemate itself** wants a checkout instead — one venv with every member
installed from source, and the git hooks this repo depends on:

```bash
git clone https://github.com/GabrielCpp/stablemate.git && cd stablemate
make install                                 # the workspace venv + the git hooks
uv run workhorse-hello-world run --dry-run
```

`groom` and `saddlebag` are optional add-ons — no base workflow requires either — and
neither is on PyPI: the name `groom` on the index belongs to an unrelated project, and
`saddlebag` is not in scope yet. Both run from a checkout.

`stablemate-core` is on neither list because it is not a distribution at all: `workhorse`
and `farrier` each carry a copy of it, so an install resolves from the index alone with
nothing built locally first.

### Finding the base library

Tools resolve the base in this order, highest precedence first — the cache is last, so a
fetched copy can never shadow a checkout you are editing:

1. `$STABLEMATE_BASE_DIR` — an explicit path to the content on disk.
2. `<tool> config set-base <path>` — the persisted form of that path.
3. a configured `stablemate_dir` checkout (`<checkout>/base-library`).
4. the shared cache at `~/.cache/stablemate/library`.

A checkout install gets route 3 for free. Under `pipx`, where each tool is its own venv
and the base is data with no package to import, route 4 is what makes it reachable
without configuring anything.

**`farrier install` populates and updates the cache.** It is the one command that does.
On install the base is fetched if absent and brought up to `main` if present, so a `pipx`
user gets a working base library by running the command they were going to run anyway:

```bash
farrier --repo .          # fetches the base if absent, updates it if stale, then renders
farrier --repo . --check  # fetches if absent, but never updates — see below
```

What lands is a sparse checkout of `base-library/` alone, with `.git` dropped once the
commit is recorded into a `.commit` sidecar. `STABLEMATE_FETCH_BASE=0` forbids the network
entirely (air-gapped hosts), and `STABLEMATE_CACHE_DIR` relocates the cache. An update
first asks the remote for the head of `main` — a few hundred bytes — so an already-current
cache costs one round-trip rather than a re-clone.

**Everything else freezes, and that is deliberate.** No lookup, no resume and no
background timer refreshes the cache; `farrier install` is the automated form of the
`rm -rf ~/.cache/stablemate` that used to be the only upgrade path, not a new polling
behaviour. A workhorse run is meant to survive a week unattended and to resume into a
checkpointed state machine after a crash, and a cache tracking `main` live could resume a
run into a different library than it started with. The corollary worth knowing: running
`farrier install` while a long run is in flight on the same machine can move the library
out from under its next resume.

`--check` fetches but does not update, because it writes nothing and runs in CI — a
library moving underneath the comparison would make a drift report depend on the hour the
job ran rather than on the commit it ran against.

Failure is soft, and in the direction of keeping what works: an unreachable remote, a
refused fetch or a broken clone each leave the existing cache in place, so `farrier
install` on a plane renders the library the machine already has. Nothing fetched is
executable either: markdown and YAML, no `.py` anywhere, so code still reaches you only as
a wheel from an index under whatever supply-chain posture you already apply to `pip`/`uv`.

A base you named yourself is never fetched over. Routes 1–3 win outright — not even the
remote probe fires — so a checkout you are editing cannot have a download appear
underneath it.

Either way the cache is a **mirror, not a workspace**: never edit it in place. Overlay
authoring belongs in a `library_dir` (below).

### Tools a workflow needs

The base library declares **no dependencies** — it is content, and importing it pulls in
nothing. The tools its workflows need are a property of *running* a workflow, not of
having the library, and a workflow is a distribution now, so they are ordinary
`[project.dependencies]` on `workhorse-workflows`. Installing that distribution installs
them with it; there is no second manifest to satisfy, and none that can disagree with
what is actually importable.

Which is the whole reason the workflows must land in workhorse's own venv rather than
beside it — and why the install above names `workhorse-workflows` rather than
`workhorse-agent`. Installing the workflows pulls the engine in as *their* dependency, so
the venv the resolver builds is by construction the venv that runs them. Installing the
engine first and adding workflows to it is the same venv reached backwards, and only if
you remember the second step. `make sync` arranges the same thing for a checkout.

### Config

Every tool reads and writes one file, `~/.config/stablemate/config.toml` (override with
`$STABLEMATE_CONFIG`), so `library_dir` / `stablemate_dir` / `base_dir` mean the same
thing to each. Per-tool files (`~/.config/workhorse`, `~/.config/farrier`) are still read
when it is absent, and the first write folds them in.

The file carries a `config_version`, and **that** is what keeps the tools honest with each
other. They install separately and version independently — `pipx install farrier` and
`pipx install ostler` are two venvs, each with its own copy of the config code — while
the config path is per *user*, not per venv. So no packaging arrangement can make
them agree; the guard has to live on the file:

- a tool **refuses to write** a config newer than it understands, rather than serializing
  back a schema it cannot represent and dropping the keys it does not know;
- a newer tool **migrates** an older config forward on its first write (keeping a
  `config.toml.v<n>.bak`), which closes the door behind it;
- **reads never fail** on a newer config — they warn. `resolve_power` re-reads per node,
  and a week-long unattended run must not die because another tool was upgraded.

If a tool refuses, upgrade it — that is the mechanism working, not a bug.

An overlay library shadows the base name-for-name via `farrier config set-library`, or
`$FARRIER_LIBRARY_DIR` for a one-off.

## Your first run

`hello-world` is the smallest workflow that runs: two states, one node, one agent turn.
It needs no repository, no context manifest and — under `--dry-run` — no agent CLI at
all, so it is the one command that tells you the install worked.

```bash
workhorse-hello-world run --dry-run     # from a checkout: uv run workhorse-hello-world …
```

```
[workhorse] starting 'hello-world' HelloWorld (run: hello-world-dry-run)
[workhorse.engine] [workhorse] state  → start
[workhorse.engine] [workhorse] call   → measure (dry-run)
[workhorse.engine] [workhorse] state  → greet
[workhorse.engine] [workhorse] agent  → greet (dry-run)
[workhorse.engine] Hello from a dry run.
[workhorse] dry-run ok — every node ran its stand-in — artifacts in …/.agents/runs/hello-world-dry-run
```

The four `state`/`call`/`agent` lines are the whole model. A **state** is a method that
returns the next state; a **node** is a plain function `self.call` runs; an **agent turn**
renders a Jinja prompt, runs an agent CLI and validates the reply into a declared model.
Every one of them left a directory behind:

```bash
ls .agents/runs/hello-world-dry-run/
# checkpoint.json  context.json  events.jsonl  run.json  measure/  greet/
```

`--dry-run` answered both seams from stand-ins the workflow declares itself, which is what
let it finish with nothing installed — so `greet/prompt.md` holds a placeholder rather than
a rendered prompt. Drop the flag and it all happens for real; that one needs an agent CLI
(`claude` by default; `--cli codex|copilot|cline|opencode`):

```bash
uv run workhorse-hello-world run --params '{"name": "globex"}'
```

```
[workhorse.engine] [workhorse] call   → measure
[workhorse.engine] measuring 'globex'
[workhorse.engine] [workhorse] agent  → greet
[greet] 🚀 Invoking claude (model: claude-sonnet-5)
[greet] ✓ result received (10921 ms)
[workhorse.engine] Hello, globex — what a great name, and it's got 6 letters!
```

That run gets its own directory (`hello-world-<id>`), and this time `greet/prompt.md` is
the prompt as the agent received it — `{{ name }}` and `{{ letters }}` filled in:

```bash
cat .agents/runs/hello-world-*/greet/prompt.md
uv run workhorse-hello-world dot           # the same machine as a graphviz diagram
```

Now read the source, which is under 90 lines and commented to be read in this order:
[`workflows/src/workhorse_workflows/hello_world/workflow.py`](workflows/src/workhorse_workflows/hello_world/workflow.py).
Copy that directory, rename it, and give it a console script of its own —
[Shipping your own, outside this repo](workhorse/docs/AUTHORING.md#shipping-your-own-outside-this-repo)
is the whole `pyproject.toml` and the one install command it takes, and it does not
require a checkout of this repository.

**Then:** [workhorse/docs/AUTHORING.md](workhorse/docs/AUTHORING.md) is the reference
for everything the quick start leaves out — the three tiers of state, checkpoints and
resume, sub-flows, operator gates, telemetry labels. Holding a `workflow.yaml` from the
retired YAML engine instead? [workhorse/docs/WORKFLOW.md](workhorse/docs/WORKFLOW.md)
maps every construct in that schema to what replaces it, and [Why a workflow is Python and
not a config file](workhorse/README.md#why-a-workflow-is-python-and-not-a-config-file) is
why that schema is gone.

## Development

```bash
make install                         # once per clone: the workspace venv + the git hooks
make sync                            # just the venv, when that is all that changed
make test                            # every suite + the benchmark tests + check-public
make build                           # wheels + sdists for core, workhorse, workflows, farrier
make -C farrier check                # inspect a built wheel's contents
make -C <pkg> test                   # one package (core, workhorse, workflows, ostler, farrier, groom)
```

`make install` is `sync` plus `hooks`, because git carries no hook configuration: a
fresh clone has `core.hooksPath` unset, so the private-name guard and the
Conventional Commits check are both silently off until something sets it.

`make sync` runs `uv sync --all-packages` so every member is installed. (Plain
`uv sync` targets the workspace root, which is an intentionally non-packaged
anchor — it has a `[project]` table but no `[build-system]`, so uv never builds
or installs the root itself.) Use `uv run --package <name>` to run within a
specific member.

`make test` is the aggregate: each member's suite, then `make test-bench` (the benchmark
harness's own tests — a benchmark whose scoring is wrong is worse than none) and
`make check-public`, the guard that no private overlay name reached this public repo and
that the base library still stands alone. `make okf-verify` is separate and slower: it
checks every OKF book's coverage against its source.

Each package that ships is independently versioned and released from CI. Nothing is
published from a laptop. See each package's README for details, and
[Releasing](#releasing) for the mechanism.

## Releasing

A release is **proposed in a pull request and shipped by merging it**. Two things follow
from that, and both are the point:

- **The version is reviewable before it exists.** [release-please](https://github.com/googleapis/release-please)
  reads the [Conventional-Commit](https://www.conventionalcommits.org) history since each
  package's last tag and opens one PR carrying the computed version bumps and the
  generated `CHANGELOG.md` files. You read what would ship before it ships.
- **There is no PyPI token anywhere.** The upload runs in
  [`.github/workflows/release.yml`](.github/workflows/release.yml) under
  [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub mints a
  short-lived OIDC token that PyPI verifies against a publisher registered as
  *(GabrielCpp, stablemate, `release.yml`, environment `pypi`)*. No long-lived secret
  exists to leak, in the repo or in a dotfile.

```bash
make release        # dispatch the workflow; a release PR appears in ~30s
gh pr list --label 'autorelease: pending'
# …review it, then merge it. Merging is what publishes.
```

`make release` builds nothing and uploads nothing — it only dispatches. The workflow does
not run on ordinary pushes to `main`, so a release happens when you ask for one and never
by accident.

### What merging does

Merging the release PR re-triggers the same workflow, which then creates the tags
(`<dist-name>-v<version>`, e.g. `farrier-v1.5.1`) and GitHub releases, runs `make test`
against the merged tree, and uploads the packages that were actually released — in
dependency order, since an install of a release has to resolve:

```
ostler → workhorse-agent → farrier → workhorse-workflows
```

`stablemate-core` is not in that chain and never will be: it is vendored, not published
(see [`core/README.md`](core/README.md)). A change to it is committed together with the
copies `make vendor` writes under `workhorse/` and `farrier/`, which is what makes
release-please bump both tools — it decides what to ship from the paths a commit touched,
so a fix committed only under `core/` would reach nobody.

`groom` and `saddlebag` are versioned and get changelogs but have no upload step: the name
`groom` on PyPI belongs to an unrelated project, and `saddlebag` is not in scope yet.
Adding either means registering its trusted publisher on PyPI and adding its two steps to
the workflow.

| Commit since last tag | Bump |
| --- | --- |
| `feat!:` / `fix(x)!:` / `BREAKING CHANGE:` in body | major |
| `feat:` | minor |
| `fix:` / `perf:` / `refactor:` | patch |
| `docs:` / `test:` / `build:` / `ci:` / `chore:` / anything unparseable | **none — no release** |

`refactor:` is in the patch row only because `changelog-sections` in
[`.release-please-config.json`](.release-please-config.json) puts it there. Release-please
hides that type by default, and a hidden type bumps nothing — so before that section
existed, a commit that rewrote a package shipped to nobody while reading as though it had
released. The section is written out in full because declaring it replaces the defaults
rather than extending them: a type left off the list is a type that silently stops
releasing.

That last row is the change of consequence. Under the old shell scripts a
non-conventional subject still produced a patch bump, so *any* commit released. Now the
commit message is what decides whether a package is released at all, and a
`Restructure the workflows` subject bumps nothing. If `make release` returns an empty PR,
that is why.

Baselines live in [`.release-please-manifest.json`](.release-please-manifest.json) and the
package map in [`.release-please-config.json`](.release-please-config.json); a new
distribution is one entry in each, plus its build/publish steps in the workflow.

### One-time setup (not in the repo)

1. On PyPI, add a trusted publisher to each project — owner `GabrielCpp`, repository
   `stablemate`, workflow `release.yml`, environment `pypi`. `workhorse-workflows` does
   not exist on the index yet, so it gets a **pending** publisher, which the first upload
   converts into the project.
2. Create the `pypi` [environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
   in the repository settings. Adding yourself as a required reviewer turns the merge into
   an explicit "approve the upload", which is the cheapest safety net available.
3. Settings → Actions → General → **Allow GitHub Actions to create and approve pull
   requests**, or release-please cannot open the PR with the default token.

## License

MIT — see [LICENSE](LICENSE).
