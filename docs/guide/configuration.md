# Configuration

Stablemate reads two files. One command prints every option of both.

## The two files

| File | Holds | Lives at |
|---|---|---|
| `config.toml` | Settings for your machine: library paths, agent CLIs, model profiles, workspaces. | `~/.config/stablemate/config.toml` on Linux. `~/Library/Application Support/stablemate/config.toml` on macOS. `%APPDATA%\stablemate\config.toml` on Windows. |
| `agents.yml` | Settings for one repository: which skills to render, its services, the workflows' keys. | The repository root. |

Every stablemate tool reads the same `config.toml`. Set `$STABLEMATE_CONFIG` to point the tools at another file.

## Create them

Run `farrier init` in a repository to write a starter `agents.yml`. It reads nothing, so it works on a fresh machine.

Run `farrier config set-library <path>` to write the first `library_dir` into `config.toml`. The file does not need to exist before that.

## Find every option

```bash
farrier config reference              # both files
farrier config reference --file home  # config.toml
farrier config reference --file manifest  # agents.yml
```

Each key shows its type, default, meaning, example, the environment variable that stands in for it, and the older names it still accepts. The output comes from the same model the tools load the files with, so it lists exactly what they read.

## When a file is wrong

A value of the wrong type stops the command and names the key path, such as `groom.dispatch.runner.concurrency`. A key no tool declares loads anyway. The tool logs one warning that names the key and the closest declared key, which usually catches a typo. A run that is already going keeps the last good config when a later edit fails to load.
