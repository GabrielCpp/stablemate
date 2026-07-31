# farrier

[![PyPI](https://img.shields.io/pypi/v/farrier.svg)](https://pypi.org/project/farrier/)

**farrier** renders an agent-neutral prompt library into a repository — generating
the skill, prompt and instruction adapters expected by Codex, Claude, and GitHub
Copilot, plus the launcher scaffolding (`.agents/agents.mk` and friends) that runs
the workflows a repo names.

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
`~/.cache/stablemate`. The env-var and `set-base` routes are the ones that matter under
`pipx`, which isolates each tool in its own venv: the base is data with no package to
import, so it can only be found by path. The cache is deliberately last, so a fetched
copy can never shadow a checkout you are editing — though today nothing populates it on
your behalf: `stablemate_core.base_cache` implements the fetch, but no command calls it
yet, so in practice one of the first three routes is what makes a base reachable. See the
[monorepo README](https://github.com/GabrielCpp/stablemate#installing) for how the tools
are installed.

## Use

From a repository that has an `agents.yml`:

```bash
farrier --repo .            # render/install the selected packs
farrier --repo . --check    # verify generated files are up to date (no writes)
```

Rendering is the default action; `farrier install --repo .` is an accepted alias
of `farrier --repo .`.

Four more verbs round it out:

```bash
farrier config show                        # every config key as key=value
farrier source .claude/skills/x/SKILL.md   # the library file that generated an adapter
farrier scaffold --list                    # the scaffolds this repo may apply, and their params
farrier scaffold <id> [--param KEY=VALUE]  # seed repo files from one
farrier version
```

`source` takes the path of a *generated* file and prints the library file behind it. It
is the one to reach for before editing anything under `.claude/`, `.codex/` or
`.github/`: those are outputs, and an edit there is discarded by the next install.

## Configuring `agents.yml`

`agents.yml` (at your repo root) selects what farrier renders. Every option —
`repo`, `agents`, `packs`, `skills`/`prompts`/`roots`, `scaffolds`, `exclude`,
`localInstructions`, `template`/`vars`, and `workflow` — is documented with
inline comments in **[`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml)**. Copy it to
your repo as `agents.yml` and prune to taste.

## Library layout

The other side of the contract is the **agent library** farrier renders *from* — what
goes in `library/skills/`, `library/prompts/`, `packs/` and `scaffolds/`, the file
formats expected, and how source names map to generated adapters. That is documented in
**[`docs/LAYOUT.md`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/docs/LAYOUT.md)**.

A library no longer ships workflows. `workflows:` in a pack or `agents.yml` is a
*selection* — farrier emits the launcher scaffolding for the names it lists, and
workhorse resolves each one through its own `workhorse.workflows` entry-point group.
Nothing is copied into `.agents/workflows/`. The catch, documented at the end of
`docs/LAYOUT.md`: farrier still *validates* each selected name against a
`workflows/<name>/` directory in some library layer, and the base library no longer has
one — so today only an overlay that still ships those directories can name workflows.

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
  that executes the workflows the launcher farrier scaffolds invokes.
- [`ostler`](https://pypi.org/project/ostler/) — the doc-graph CLI those workflows
  shell out to.

All three live in the [stablemate](https://github.com/GabrielCpp/stablemate) workspace.
