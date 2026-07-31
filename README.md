# stablemate

A [uv](https://docs.astral.sh/uv/) workspace housing the publishable Python
packages that work alongside an agent prompt library:

| Package | PyPI | Role |
| --- | --- | --- |
| [`workhorse/`](workhorse/) | [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) | Fail-soft runner that drives an agent CLI — Claude, Codex or Copilot — through a checkpointed Python state machine, unattended for days. |
| [`workflows/`](workflows/) | `workhorse-workflows` (unpublished) | The workflows themselves — `author`, `coder`, `okf-builder`, `research` — as Python, found by the `workhorse.workflows` entry-point group. |
| [`farrier/`](farrier/) | [`farrier`](https://pypi.org/project/farrier/) | Renders an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters and launcher. |
| [`ostler/`](ostler/) | [`ostler`](https://pypi.org/project/ostler/) | Tends a repo's `docs/` knowledge graph — the CLI several base workflows shell out to. |
| [`groom/`](groom/) | — (unpublished) | Local dashboard + OTLP collector for running workflows: answers operator gates from the browser and pages you when a run stalls. Optional. |
| [`saddlebag/`](saddlebag/) | `saddlebag` (unpublished) | Credentials and environment manifests a workflow needs at run time, kept out of the repo. Optional. |
| [`core/`](core/) | `stablemate-core` (unpublished) | Shared plumbing the tools must agree on: the home config, base-library discovery, the base-library cache. Not installed directly. |

And two directories that are **not** packages:

| Directory | Role |
| --- | --- |
| [`base-library/`](base-library/) | The **base library**: the skills farrier renders, and the packs that select them. Plain data — `library/`, `packs/` — markdown and YAML, with nothing to import and no dependencies. Tools find it on disk or fetch it from git. |
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
and the tools fetch it themselves.

**A checkout is the supported install today**, because it is the one arrangement that
puts every piece in a single interpreter:

```bash
git clone https://github.com/GabrielCpp/stablemate.git && cd stablemate
make sync                             # one venv with every member installed
uv run workhorse run <name>           # author, coder, okf-builder, research
```

That single-interpreter part is not incidental. Workflow code runs **in workhorse's own
interpreter** and imports its tools in-process, so `workhorse run <name>` only finds a
workflow through the `workhorse.workflows` entry-point group in that same venv, and
`ostler` being on your `PATH` is not enough — it has to be importable *there*. See
[Tools a workflow needs](#tools-a-workflow-needs).

Two of the tools stand alone and are on PyPI, so `pipx` suits them:

```bash
pipx install farrier
pipx install ostler
```

The rest are not on PyPI yet: `stablemate-core`, `workhorse-workflows` and `saddlebag`
are unpublished, the name `groom` on the index belongs to an unrelated project, and the
last `workhorse-agent` release predates the Python-workflow engine. A `pipx install
./workhorse` therefore also needs core built locally first (`make -C core build`, then
`--pip-args="--find-links core/dist"`), which is why the checkout above is the path this
README vouches for.

`groom` and `saddlebag` are optional add-ons — no base workflow requires either.

### The base library fetches itself

The first time workhorse resolves a workflow by name and finds no library, it fetches
one into your cache and uses it from there:

```
[stablemate] fetching base library: https://github.com/GabrielCpp/stablemate.git (main, base-library/ only)
[stablemate] base library cached at ~/.cache/stablemate/library (420e421…)
```

**Nothing fetched is executable.** It is a sparse checkout of `base-library/` — markdown
and YAML, no `.py` anywhere — and the `.git` directory is dropped once the commit is
recorded, so the cache holds documents rather than a repository. Code reaches you only
as a wheel from an index, under whatever supply-chain posture you already apply to
`pip`/`uv`.

**It is fetched once and then frozen.** Nothing refreshes it in the background — to
move to a newer library, delete the cache and let the next run re-fetch:

```bash
rm -rf ~/.cache/stablemate          # the upgrade path
```

That is deliberate. A run is meant to survive a week unattended and to resume into a
checkpointed state machine after a crash; a cache that tracked `main` live could resume a
run into a different library than it started with. The trade is that two machines can
hold different commits of `main` — `cat ~/.cache/stablemate/library/.commit` says which.
Set `STABLEMATE_FETCH_BASE=0` to forbid the fetch (air-gapped hosts), or
`STABLEMATE_CACHE_DIR` to relocate it.

The cache is a **mirror, not a workspace**: deleting it is routine, so never edit it in
place. Overlay authoring belongs in a `library_dir` (below).

Tools resolve the base in this order, highest precedence first — a fetched copy is
last, so it can never shadow a checkout you are editing:

1. `$STABLEMATE_BASE_DIR` — an explicit path to the content on disk.
2. `<tool> config set-base <path>` — the persisted form of that path.
3. a configured `stablemate_dir` checkout (`<checkout>/base-library`).
4. the shared cache above, fetched on first use.

### Tools a workflow needs

The base library declares **no dependencies** — it is content, and importing it pulls in
nothing. The tools its workflows need are a property of *running* a workflow, not of
having the library, and a workflow is a distribution now, so they are ordinary
`[project.dependencies]` on `workhorse-workflows`. Installing that distribution installs
them with it; there is no second manifest to satisfy, and none that can disagree with
what is actually importable.

Which is the whole reason the workflows must land in workhorse's own venv rather than
beside it. `make sync` arranges that for a checkout; a `pipx` layout needs
`pipx inject workhorse-agent <the workflows distribution>` to reach the same place.

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

## Development

```bash
make sync                            # create the workspace venv (all members)
make hooks                           # once per clone: the private-name pre-commit hook
make test                            # every suite + the benchmark tests + check-public
make build                           # wheels + sdists for core, workhorse, workflows, farrier
make -C farrier check                # inspect a built wheel's contents
make -C <pkg> test                   # one package (core, workhorse, workflows, ostler, farrier, groom)
```

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

Each package is independently versioned and published (`make -C <pkg> publish`).
See each package's README for details.

## Releasing

Each package is released independently, with its next version inferred from the
[Conventional-Commit](https://www.conventionalcommits.org) history since its last
release tag (`<dist-name>-v<version>`, e.g. `farrier-v1.3.0`). Only commits that
touch the package's own directory count, so each package bumps on its own clock.

The root release targets cover the three published distributions — `core`, `workhorse`
and `farrier` — in that order, because the other two declare `stablemate-core` and
releasing them against an unpublished core produces installs that cannot resolve.
`workflows` builds but is not published yet (see
[workflows/README.md](workflows/README.md)); `groom` and `saddlebag` are released by hand.

| Commit since last tag | Bump |
| --- | --- |
| `feat!:` / `fix(x)!:` / `BREAKING CHANGE:` in body | major |
| `feat:` | minor |
| anything else (`fix:`, `perf:`, `docs:`, …, or none) | patch |

```bash
make version                         # print each published package's current version
make next-version                    # show what each package WOULD bump to
make release DRY_RUN=1               # preview the full release, change nothing
make release                         # bump, build, publish, commit, tag, push — all three
make -C farrier release              # release just one package
```

`make release` stamps the new version into `pyproject.toml`, builds, publishes to
PyPI, then commits, creates the annotated tag, and pushes. The PyPI upload happens
before anything is committed or pushed: if publish fails, nothing is committed,
tagged, or pushed — just revert the local version stamp with
`git checkout -- <pkg>/pyproject.toml` and retry.

Knobs (set as `make` variables or environment variables):

| Knob | Effect |
| --- | --- |
| `DRY_RUN=1` | Print every step; change nothing. |
| `LEVEL=major\|minor\|patch` | Force the bump level instead of inferring it. |
| `RELEASE_VERSION=x.y.z` | Use an exact version (skips inference). |
| `PUBLISH=testpypi` | Publish to TestPyPI (or use `make release-test`). |
| `ALLOW_DIRTY=1` | Skip the clean-working-tree guard. |
| `NO_PUSH=1` | Commit + tag locally, but do not push. |
| `ZEROVER=1` | Pre-1.0 demotion (breaking → minor, feat → patch) while on 0.x. |

To review before committing, use `make bump` (or `make -C <pkg> bump`), which only
stamps the inferred version into `pyproject.toml` — you then commit, tag, and
publish by hand.

## License

MIT — see [LICENSE](LICENSE).
