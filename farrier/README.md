# farrier

[![PyPI](https://img.shields.io/pypi/v/farrier.svg)](https://pypi.org/project/farrier/)

**farrier** renders an agent-neutral prompt library into a repository — generating
the skill, prompt, instruction, and workflow adapters expected by Codex, Claude,
and GitHub Copilot, plus the launcher scaffolding that runs them.

A farrier is the craftsman who fits the right gear onto each horse. This tool
fits the shared prompt library onto each repository.

## Install

```bash
pipx install farrier        # or: uv tool install farrier
```

farrier ships **no library content of its own** — the prompt library lives in a
separate repository. Point farrier at it once:

```bash
farrier config set-library /path/to/vigilant-octo/agents
farrier config show
```

`config` writes a small TOML file in your OS config directory
(`~/.config/farrier/config.toml` on Linux, `~/Library/Application Support/farrier/`
on macOS, `%APPDATA%\farrier\` on Windows).

## Use

From a repository that has a `.agents.yml`:

```bash
farrier --repo .            # render/install the selected packs
farrier --repo . --check    # verify generated files are up to date (no writes)
```

Rendering is the default action; `farrier install --repo .` is an accepted alias
of `farrier --repo .`.

## Configuring `.agents.yml`

`.agents.yml` (at your repo root) selects what farrier renders. Every option —
`repo`, `agents`, `packs`, `skills`/`prompts`/`roots`, `scaffolds`, `exclude`,
`localInstructions`, `template`/`vars`, and `workflow` — is documented with
inline comments in **[`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml)**. Copy it to
your repo as `.agents.yml` and prune to taste.

## Locating the library

farrier resolves the library directory with this precedence:

1. `--library DIR`
2. `$FARRIER_LIBRARY_DIR`
3. `library_dir` from the home config (`farrier config set-library`)

If none resolve — or the path does not contain `library/` and `packs/` — farrier
exits with a setup hint.

## Related

- [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) — the fail-soft
  runtime that executes the workflows farrier installs. Both live in the
  [stablemate](https://github.com/GabrielCpp/stablemate) workspace.
