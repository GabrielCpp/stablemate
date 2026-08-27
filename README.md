# stablemate

[![CI](https://github.com/GabrielCpp/stablemate/actions/workflows/ci.yml/badge.svg)](https://github.com/GabrielCpp/stablemate/actions/workflows/ci.yml)
[![workhorse-agent](https://img.shields.io/pypi/v/workhorse-agent?label=workhorse-agent)](https://pypi.org/project/workhorse-agent/)
[![farrier](https://img.shields.io/pypi/v/farrier?label=farrier)](https://pypi.org/project/farrier/)
[![ostler](https://img.shields.io/pypi/v/ostler?label=ostler)](https://pypi.org/project/ostler/)
[![workhorse-workflows](https://img.shields.io/pypi/v/workhorse-workflows?label=workhorse-workflows)](https://pypi.org/project/workhorse-workflows/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Why

The cheapest way to run an agent for hours is a bash loop around `claude -p`. That
works right up until it doesn't, and the four ways it doesn't are the reason this
toolchain exists:

- **A loop dies with its process.** workhorse checkpoints every state transition, so a
  crash — or a deliberate stop — resumes days later exactly where it left off, with the
  same inputs it started with.
- **A loop retries blindly, or not at all.** The engine escalates through a recovery
  ladder — transient retries with backoff, context compaction, prompt reframing — and
  when a subscription cap bites, it reads the reset time and sleeps until the window
  reopens instead of dying inside it.
- **A loop leaves no trace.** Every run leaves a directory: each prompt exactly as the
  agent received it, each reply validated into a declared model, the event log, the
  checkpoint — the artifacts that turn "it did something weird at 3am" into a diff you
  can read.
- **A loop can't ask you anything.** Operator gates park a run on a question only a
  human can answer and resume when it is answered — from the browser, hours later,
  via [groom](groom/).

The composite is the point: **multi-day, unattended runs on subscription-billed agent
CLIs** — Claude, Codex, Copilot, Cline, OpenCode — with a repo-local planning graph and
asynchronous human gates.

## What's in the box

A [uv](https://docs.astral.sh/uv/) workspace housing the publishable Python
packages that work alongside an agent prompt library:

| Package | PyPI | Role |
| --- | --- | --- |
| [`workhorse/`](workhorse/) | [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) | Fail-soft engine (a library, not a command) that drives an agent CLI — Claude, Codex, Copilot, Cline or OpenCode — through a checkpointed Python state machine, unattended for days. |
| [`workflows/`](workflows/) | [`workhorse-workflows`](https://pypi.org/project/workhorse-workflows/) | The workflows themselves — `hello-world`, `author`, `coder`, `okf-builder`, `research` — as Python, each declaring its own `workhorse-<name>` command. |
| [`farrier/`](farrier/) | [`farrier`](https://pypi.org/project/farrier/) | Renders an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters and launcher. |
| [`ostler/`](ostler/) | [`ostler`](https://pypi.org/project/ostler/) | Tends a repo's `docs/` knowledge graph through its CLI and the in-process facade workflows use. |
| [`groom/`](groom/) | — (unpublished) | Local dashboard + OTLP collector for running workflows: answers operator gates from the browser and pages you when a run stalls. Optional. |
| [`saddlebag/`](saddlebag/) | `saddlebag` (unpublished) | Credentials and environment manifests a workflow needs at run time, kept out of the repo. Optional. |
| [`core/`](core/) | — (vendored, never published) | Shared plumbing the tools must agree on: the home config, base-library discovery, the base-library cache. `make vendor` copies it into `workhorse`, `farrier` and `ostler`, which ship it inside their own wheels; there is nothing to install. |

And two directories that are **not** packages:

| Directory | Role |
| --- | --- |
| [`base-library/`](base-library/) | The **base library**: the skills farrier renders, and the packs that select them. Plain data — `library/`, `packs/` — markdown and YAML, with nothing to import and no dependencies. Tools find it on disk, by path. |
| [`paddock/`](paddock/) | The one benchmark harness, and in [`paddock/data/`](paddock/data/README.md) the tasks it runs: a workflow chain's output scored against a backlog of user-observable bullets — one number, comparable across runs. Run with `uv run paddock run <task>`. |

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
[What the install resolves against](#what-the-install-resolves-against)).

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
venv that has it. See [What the install resolves against](#what-the-install-resolves-against).

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

### What the install resolves against

**The base library is content, not a package.** Tools look for it in four places — an
explicit `$STABLEMATE_BASE_DIR`, a persisted `<tool> config set-base <path>`, a configured
`stablemate_dir` checkout, and last the shared cache at `~/.cache/stablemate/library` — so
a fetched copy can never shadow a checkout you are editing. `farrier install` is the one
command that populates or updates that cache; nothing else refreshes it on a timer, because
a library moving under a week-long run could resume it into a different library than it
started with.

**A workflow's tools travel with the workflow.** They are ordinary
`[project.dependencies]` on `workhorse-workflows`, not a second manifest — which is why the
install above names the workflows rather than the engine. Workflow code runs in workhorse's
own interpreter and imports its tools in-process, so `ostler` on your `PATH` from some other
venv is not enough; it has to be importable *there*.

**Every tool reads one config file**, `~/.config/stablemate/config.toml` (override with
`$STABLEMATE_CONFIG`), carrying a `config_version` that keeps independently-versioned tools
honest with each other: a tool refuses to write a config newer than it understands, migrates
an older one forward on first write, and never *fails* a read.

The four routes in full, the fetch and failure behaviour, and the config-version rules are
in [docs/INSTALL.md](docs/INSTALL.md).

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
# checkpoint.json  context.json  events.jsonl  launch.json  run.json  measure/  greet/  resume_generation
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
make install                         # once per clone: venv + git hooks + test browsers
make sync                            # just the venv, when that is all that changed
make test                            # every suite + the benchmark tests + check-public
make build                           # wheels + sdists for ostler, workhorse, farrier, workflows
make -C farrier check                # inspect a built wheel's contents
make -C <pkg> test                   # one package (core, workhorse, workflows, ostler, farrier, groom, saddlebag, paddock)
```

`make install` is `sync` plus `browsers` (the Playwright Chromium some suites drive —
expect a one-time download) plus `hooks`, because git carries no hook configuration: a
fresh clone points `core.hooksPath` nowhere, so the private-name guard, the
Conventional Commits check and the generated-file gate are all silently off until
something installs them. `make hooks` is `farrier hooks`, which reads the `hooks:`
block in `agents.yml` and wires `.githooks/` in.

`make sync` runs `uv sync --all-packages` so every member is installed. (Plain
`uv sync` targets the workspace root, which is an intentionally non-packaged
anchor — it has a `[project]` table but no `[build-system]`, so uv never builds
or installs the root itself.) Use `uv run --package <name>` to run within a
specific member.

`make test` is the aggregate: lint, then every member's suite — paddock's benchmark
tests included, because a benchmark whose scoring is wrong is worse than none — then
the repo guards, among them `make check-public`, which asserts that no private overlay
name reached this public repo and that the base library still stands alone. `make okf-verify` is separate and slower: it
checks every OKF book's coverage against its source.

Each package that ships is independently versioned and released from CI. Nothing is
published from a laptop. See each package's README for details, and
[Releasing](#releasing) for the mechanism.

## Releasing

A release is **proposed in a pull request and shipped by merging it**. Two things follow
from that, and both are the point: the version is reviewable before it exists —
[release-please](https://github.com/googleapis/release-please) reads the
[Conventional-Commit](https://www.conventionalcommits.org) history since each package's
last tag and opens one PR carrying the computed bumps and the generated changelogs — and
there is no PyPI token anywhere, because the upload runs under
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) on a short-lived OIDC
token.

```bash
make release        # dispatch the workflow; a release PR appears in ~30s
gh pr list --label 'autorelease: pending'
# …review it, then merge it. Merging is what publishes.
```

`make release` builds nothing and uploads nothing. The workflow does not run on ordinary
pushes to `main`, so a release happens when you ask for one and never by accident. The one
rule that bites: a commit type outside `feat:` / `fix:` / `perf:` / `refactor:` bumps
nothing at all, so an unparseable subject releases to nobody. If `make release` returns an
empty PR, that is why.

What merging does, the upload order and the isolated smoke test in front of it, the full
type→bump table, and the one-time PyPI setup are in [docs/RELEASING.md](docs/RELEASING.md).

## License

MIT — see [LICENSE](LICENSE).
