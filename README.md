# stablemate

A [uv](https://docs.astral.sh/uv/) workspace housing the publishable Python
packages that work alongside an agent prompt library:

| Package | PyPI | Role |
| --- | --- | --- |
| [`workhorse/`](workhorse/) | [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) | Fail-soft runner that drives the Claude CLI through a YAML workflow graph, unattended for days. |
| [`farrier/`](farrier/) | [`farrier`](https://pypi.org/project/farrier/) | Renders an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters and launcher. |
| [`ostler/`](ostler/) | [`ostler`](https://pypi.org/project/ostler/) | Tends a repo's `docs/` knowledge graph — the CLI several base workflows shell out to. |
| [`base-library/`](base-library/) | [`stablemate-library`](https://pypi.org/project/stablemate-library/) | The **base library**: the skills, workflows and scaffolds that farrier renders and workhorse runs, shipped as a wheel. |

Library content resolves across two layers: the **base** (`stablemate-library`, above)
and an optional private **overlay** that shadows it name-for-name. Point a repo at an
overlay with:

```bash
farrier config set-library /path/to/the/overlay
```

The base is always present once the tools can find it — see
[Installing](#installing) for how that discovery works, which matters because
`pipx` installs each tool in its own isolated environment.

## Installing

The engines and the base library are separate PyPI packages, and **how you install
them decides whether they can find each other at runtime.** The base library
(`stablemate-library`) is pure content — no logic the tools import beyond the path to
that content. farrier and workhorse locate it in this order (highest precedence first):

1. `$STABLEMATE_BASE_DIR` — an explicit path to the content on disk.
2. `<tool> config set-base <path>` — the persisted form of that path.
3. an import of the `stablemate-library` wheel **from the tool's own environment**.
4. a configured `stablemate_dir` checkout (`<checkout>/base-library/stablemate_library`).

Two setups are supported as equals — pick by whether you want one environment or
independently upgradable tools.

### One environment (simplest)

Install the base library and let it pull the engines into the *same* place, so the
import in step 3 resolves with nothing to configure:

```bash
pipx install stablemate-library --include-deps   # base + farrier/workhorse/ostler, one venv
# …or into a plain virtualenv:
pip install stablemate-library
```

`--include-deps` also exposes the `farrier`, `workhorse` and `ostler` commands on your
PATH. If you already installed those standalone with pipx, remove them first so the
commands don't collide:

```bash
pipx uninstall farrier workhorse-agent ostler
```

### Isolated tools (independent upgrades)

Keep each engine in its own `pipx` venv and point them at one shared copy of the base
content. This is the setup where step 3 **cannot** work — pipx isolates every app in
its own environment, so `pipx install farrier` can never import a separately-installed
wheel — and steps 1–2 carry it:

```bash
pipx install farrier
pipx install workhorse-agent
pipx install ostler

# place the content once (‑‑no-deps: just the payload, not the engines)
pip install --no-deps --target ~/.local/share/stablemate/base stablemate-library
BASE=~/.local/share/stablemate/base/stablemate_library

export STABLEMATE_BASE_DIR="$BASE"        # one env var both tools read…
# …or persist it per tool instead of exporting:
farrier   config set-base "$BASE"
workhorse config set-base "$BASE"
```

`groom` and `saddlebag` are optional add-ons (`pipx install groom` /
`pipx install saddlebag`); no base workflow requires them.

Either way, an overlay library still shadows the base name-for-name via
`farrier config set-library` (or `$FARRIER_LIBRARY_DIR` / `$WORKHORSE_LIBRARY_DIR`).

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
