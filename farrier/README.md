# farrier

[![PyPI](https://img.shields.io/pypi/v/farrier.svg)](https://pypi.org/project/farrier/)

**farrier** renders an agent-neutral prompt library into a repository — generating
the skill, prompt and instruction adapters expected by Codex, Claude, and GitHub
Copilot, plus the launcher scaffolding (`.agents/agents.mk` and friends) that keeps
those adapters current.

A farrier is the craftsman who fits the right gear onto each horse. This tool
fits the shared prompt library onto each repository.

## Install

```bash
pipx install farrier        # or: uv tool install farrier
```

The farrier package ships **no library content of its own.** Content resolves across
two layers: the **base library** — plain data, the toolchain skills and the packs that
select them, with nothing to install or import — and an optional private **overlay**
that shadows it name-for-name. Point farrier at an overlay once:

```bash
farrier config set-library /path/to/the/overlay
farrier config show
```

`config` writes one shared TOML file, `~/.config/stablemate/config.toml`
(`~/Library/Application Support/stablemate/` on macOS, `%APPDATA%\stablemate\` on
Windows; `$STABLEMATE_CONFIG` overrides it). Every stablemate tool reads and writes that
same file, so `library_dir` and `base_dir` mean one thing across all of them — a
pre-existing `~/.config/farrier/config.toml` is still read, and folded in on the first
write.

**Finding the base library.** farrier discovers the base via, in order,
`$STABLEMATE_BASE_DIR` → the `base_dir` config key (`farrier config set-base <path>`) →
a configured `stablemate_dir` checkout (`<checkout>/base-library`) → the shared cache at
`~/.cache/stablemate`. The cache is deliberately last, so a fetched copy can never shadow
a checkout you are editing.

**`farrier install` fetches the base, and updates it.** It is the only command that
touches the cache, so under `pipx` — where each tool is its own venv and the base is data
with no package to import — you get a working base library without configuring anything.
An update asks the remote for the head of `main` first, so an already-current cache costs
one round-trip rather than a re-clone. Three qualifications:

- **A base you named is never fetched over.** If `$STABLEMATE_BASE_DIR`, `set-base` or a
  `stablemate_dir` checkout answers, install returns it without even probing the remote.
- **`--check` fetches but never updates.** It writes nothing and runs in CI, where a
  library moving underneath the comparison would make the result depend on the hour.
- **Failure keeps what works.** Offline, `STABLEMATE_FETCH_BASE=0`, or a broken clone all
  leave the existing cache in place rather than leaving you with none.

`STABLEMATE_FETCH_BASE=0` forbids the network entirely; `STABLEMATE_CACHE_DIR` relocates
the cache. See the
[monorepo README](https://github.com/GabrielCpp/stablemate#finding-the-base-library) for
the full resolution order and why everything other than install reads the cache frozen.

## Use

In a repository that has no `agents.yml` yet:

```bash
farrier init                # write a starter agents.yml (--force to replace one)
```

`init` reads nothing — no library, no config — so it works on a fresh machine before
`farrier config set-library`. It refuses to overwrite an existing `agents.yml`.

Then, from a repository that has one:

```bash
farrier --repo .            # render/install the selected packs
farrier --repo . --check    # verify generated files are up to date (no writes)
```

Rendering is the default action; `farrier install --repo .` is an accepted alias
of `farrier --repo .`. A bare `farrier` with no arguments prints the verb listing.

The rest of the verbs:

```bash
farrier config show                        # every config key as key=value
farrier config show --profile cheap        # one [profiles.<name>] table, flattened
farrier config --config ./c.toml show      # …read from that file rather than the home one
farrier source .claude/skills/x/SKILL.md   # the library file that generated an adapter
farrier scaffold --list                    # the scaffolds this repo may apply, and their params
farrier scaffold <id> [--param KEY=VALUE]  # seed repo files from one
farrier workflows                          # the workflows installed on this machine
farrier version
```

`source` takes the path of a *generated* file and prints the library file behind it. It
is the one to reach for before editing anything under `.claude/`, `.codex/` or
`.github/`: those are outputs, and an edit there is discarded by the next install.

`config show --profile <name>` prints one `[profiles.<name>]` table — the named model
set a run selects with `workhorse-<name> run --profile <name>` — flattened to one dotted
line per leaf (`power.high.claude.model=haiku`). A profile **replaces** the top-level
tables rather than layering over them, so what it prints is the whole config that run
resolves from, and two profiles diff against each other line by line. `--config PATH`
goes before the action and names the file every config verb reads and writes, so the
question can be asked of a config that is not this machine's home one. There is no
setter: a profile is a nested table, and `set-library`-style flat assignment cannot
express one — edit the file.

## Configuring `agents.yml`

`agents.yml` (at your repo root) selects what farrier renders. `farrier init` writes a
starter one with the common keys as commented examples. Every option —
`repo`, `agents`, `packs`, `skills`/`prompts`/`roots`, `scaffolds`, `exclude`,
`localInstructions`, `template`/`vars`, and `workflow` — is documented with
inline comments in **[`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml)**. Copy it to
your repo as `agents.yml` and prune to taste.

## Library layout

The other side of the contract is the **agent library** farrier renders *from* — what
goes in `library/skills/`, `library/prompts/`, `packs/` and `scaffolds/`, the file
formats expected, and how source names map to generated adapters. That is documented in
**[`docs/LAYOUT.md`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/docs/LAYOUT.md)**.

A skill or prompt is markdown with YAML frontmatter, and `farrier.frontmatter` reads it
with a markdown parser and `yaml.safe_load` — never a fence regex. (It is farrier's own
module rather than `ostler.markdown` because farrier needs frontmatter only and does not
depend on ostler; both follow the same rule, which the `stablemate-structured-parsing`
skill states in full.) A CRLF file, a closing `---` with a trailing space and a file with
no newline after it are all ordinary documents, and the regexes that preceded this read
every one of them as having no frontmatter at all.

**Farrier does not install workflows.** A library ships none, `agents.yml` has no
`workflows:` key, and nothing is written to `.agents/workflows/`. A workflow is a Python
distribution that brings its own command: install it with pip/uv and run it directly.

```bash
uv tool install workhorse-workflows
workhorse-coder run --dry-run    # static preflight, drives nothing
workhorse-coder run
```

## Locating the library

`--library DIR`, `$FARRIER_LIBRARY_DIR` and `library_dir` in the home config
(`farrier config set-library`) select the **overlay**, in that precedence. The base
library is found separately, by the order under [Install](#install) above, and the two
stack: the overlay first, then the base.

A directory counts as a library if it holds `library/` — that is the whole contract.
Point farrier at one that does not and it exits with a setup hint; configure no overlay
at all and it runs base-only, which is a supported setup rather than an error. Only with
neither an overlay nor a base does it refuse to start.

## Related

- [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) — the fail-soft runner
  that executes the workflows, against the adapters farrier renders.
- [`ostler`](https://pypi.org/project/ostler/) — the doc-graph CLI those workflows
  shell out to.

All three live in the [stablemate](https://github.com/GabrielCpp/stablemate) workspace.
