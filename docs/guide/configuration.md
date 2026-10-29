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
farrier config reference                         # one line per key, both files
farrier config reference workflow                # full entries for workflow and its keys
farrier config reference profiles.claude.powers  # a name you picked matches <name>
farrier config reference --full                  # every full entry
```

Start with the index. It lists every key of `config.toml` and `agents.yml` on one line, with its type, default and the first sentence of its meaning. Then name a key, or a table such as `groom` or `workflow`, to read the full entries under it. A full entry shows the key's type, default, meaning, example, the environment variable that stands in for it, and the older names it still accepts. `--file home` or `--file manifest` keeps the output to one file. The output comes from the same model the tools load the files with, so it lists exactly what they read.

## Read or change one key

```bash
farrier config get profiles.claude.powers.high.model
farrier config set profiles.claude.powers.high.model=opus
farrier config set profiles.claude.powers.high.timeout_scale=1.5
```

`get` prints the value the tools will use, which is the default when the file does not set the key. `set` writes one key of `config.toml` and keeps the file's comments. A string key takes the text after `=` as it is. Any other key takes a TOML value, such as `true`, `1.5`, `["a", "b"]` or `{ cli = "codex" }`. `set` checks the whole file against the schema before it saves, so a misspelt key or a value of the wrong type leaves the file unchanged and names the problem. `agents.yml` has no setter. Edit it in the repository.

## When a file is wrong

A value of the wrong type stops the command and names the key path, such as `groom.dispatch.runner.concurrency`. A key no tool declares loads anyway. The tool logs one warning that names the key and the closest declared key, which usually catches a typo. A run that is already going keeps the last good config when a later edit fails to load.
