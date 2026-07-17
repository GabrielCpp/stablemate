# stablemate

A [uv](https://docs.astral.sh/uv/) workspace housing the publishable Python
packages that work alongside an agent prompt library:

| Package | PyPI | Role |
| --- | --- | --- |
| [`workhorse/`](workhorse/) | [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) | Fail-soft runner that drives the Claude CLI through a YAML workflow graph, unattended for days. |
| [`farrier/`](farrier/) | [`farrier`](https://pypi.org/project/farrier/) | Renders an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters and launcher. |
| [`ostler/`](ostler/) | [`ostler`](https://pypi.org/project/ostler/) | Tends a repo's `docs/` knowledge graph — the CLI several base workflows shell out to. |
| [`core/`](core/) | [`stablemate-core`](https://pypi.org/project/stablemate-core/) | Shared plumbing the tools must agree on: the home config, base-library discovery, the base-library cache. Not installed directly. |

And one directory that is **not** a package:

| Directory | Role |
| --- | --- |
| [`base-library/`](base-library/) | The **base library**: the skills, workflows and scaffolds that farrier renders and workhorse runs. Plain data — `library/`, `scaffolds/`, `workflows/` — with nothing to import and no dependencies. Tools find it on disk or fetch it from git. |

Library content resolves across two layers: the **base** (`base-library/`, above) and an
optional private **overlay** that shadows it name-for-name. Point a repo at an overlay
with:

```bash
farrier config set-library /path/to/the/overlay
```

You never install the base — see [Installing](#installing). Because it is data rather
than a distribution, nothing depends on it in either direction, so content versions on
its own clock; each `workflow.yaml` declares the tools it needs in a `requires:` block
instead.

## Installing

Install the engines. **The base library is not something you install** — it is content,
and the tools fetch it themselves:

```bash
pipx install workhorse-agent
pipx install farrier
pipx install ostler
```

`groom` and `saddlebag` are optional add-ons (`pipx install groom` /
`pipx install saddlebag`); no base workflow requires them.

### The base library fetches itself

The first time workhorse resolves a workflow by name and finds no library, it clones
one into your cache and uses it from there:

```
[stablemate] fetching base library: https://github.com/GabrielCpp/stablemate.git (main)
[stablemate] base library cached at ~/.cache/stablemate/library (420e421…)
```

**It is fetched once and then frozen.** Nothing refreshes it in the background — to
move to a newer library, delete the cache and let the next run re-fetch:

```bash
rm -rf ~/.cache/stablemate          # the upgrade path
```

That is deliberate. A run is meant to survive a week unattended and to resume into a
checkpointed graph after a crash; a cache that tracked `main` live could resume a run
into a different workflow than it started. The trade is that two machines can hold
different commits of `main` — `git -C ~/.cache/stablemate/library rev-parse HEAD` says
which. Set `STABLEMATE_FETCH_BASE=0` to forbid the fetch (air-gapped hosts), or
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
having the library, so each `workflow.yaml` declares its own and workhorse checks them
before the first node runs:

```
[workhorse] ERROR: workflow 'okf-builder' cannot run; unmet requirements:
  - ostler is not installed in the interpreter that runs script nodes. Install it there:
    ~/.local/share/pipx/venvs/workhorse-agent/bin/python -m pip install ostler>=0.1.0
```

Script nodes run under workhorse's own interpreter and import their tools in-process, so
`ostler` being on your `PATH` is not enough — it must be importable *there*:

```bash
pipx inject workhorse-agent ostler
```

See [workhorse/docs/WORKFLOW.md](workhorse/docs/WORKFLOW.md) for the `requires:` schema.

### Config

Both tools read and write one file, `~/.config/stablemate/config.toml` (override with
`$STABLEMATE_CONFIG`), so `library_dir` / `stablemate_dir` / `base_dir` mean the same
thing to each. Per-tool files (`~/.config/workhorse`, `~/.config/farrier`) are still read
when it is absent, and the first write folds them in.

The file carries a `config_version`, and **that** is what keeps the tools honest with each
other. They install separately and version independently — `pipx install workhorse-agent`
and `pipx install farrier` are two venvs, each with its own copy of the config code —
while the config path is per *user*, not per venv. So no packaging arrangement can make
them agree; the guard has to live on the file:

- a tool **refuses to write** a config newer than it understands, rather than serializing
  back a schema it cannot represent and dropping the keys it does not know;
- a newer tool **migrates** an older config forward on its first write (keeping a
  `config.toml.v<n>.bak`), which closes the door behind it;
- **reads never fail** on a newer config — they warn. `resolve_power` re-reads per node,
  and a week-long unattended run must not die because another tool was upgraded.

If a tool refuses, upgrade it — that is the mechanism working, not a bug.

An overlay library shadows the base name-for-name via `farrier config set-library` (or
`$FARRIER_LIBRARY_DIR` / `$WORKHORSE_LIBRARY_DIR`).

## Development

```bash
make sync                            # create the workspace venv (all members)
make build                           # build wheels + sdists for both packages
make test                            # run both test suites
make -C farrier check                # inspect a built wheel's contents
```

`make sync` runs `uv sync --all-packages` so both members are installed. (Plain
`uv sync` targets the workspace root, which is an intentionally non-packaged
anchor — it has a `[project]` table but no `[build-system]`, so uv never builds
or installs the root itself.) Use `uv run --package <name>` to run within a
specific member.

Each package is independently versioned and published (`make -C <pkg> publish`).
See each package's README for details.

## Releasing

Each package is released independently, with its next version inferred from the
[Conventional-Commit](https://www.conventionalcommits.org) history since its last
release tag (`<dist-name>-v<version>`, e.g. `farrier-v1.3.0`). Only commits that
touch the package's own directory count, so the two packages bump separately.

| Commit since last tag | Bump |
| --- | --- |
| `feat!:` / `fix(x)!:` / `BREAKING CHANGE:` in body | major |
| `feat:` | minor |
| anything else (`fix:`, `perf:`, `docs:`, …, or none) | patch |

```bash
make next-version                    # show what each package WOULD bump to
make release DRY_RUN=1               # preview the full release for both packages
make release                         # release both: bump, build, publish, commit, tag, push
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
