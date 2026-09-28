# saddlebag

The package behind the `saddlebag` command. It holds the credential pool and the environments a run needs, and delivers each secret to its consumer without returning it to the caller.

## Map

- `browser.py`: the `fill` delivery path. It finds a page over the Chrome DevTools Protocol on loopback and types a value into it.
- `cli.py`: the argparse entry point and every subcommand, including `env`, `totp` and `link`.
- `context.py`: which project saddlebag works in by default, inferred from the enclosing git repository.
- `db.py`: the SQLite pool: its schema, credential and environment metadata, and leases.
- `envfile.py`: reading and writing `.env` text, without python-dotenv.
- `keychain.py`: reading a secret saddlebag did not write, addressed by OS keychain attributes. It backs `link` and `unlink`.
- `manifest.py`: the checkable-in YAML form an environment travels as.
- `models.py`: the credential, lease, requirement, environment and entry records. None of them carries a secret.
- `render.py`: resolving an environment to values, and the `render --check` diff against its target file.
- `selector.py`: AI credential selection: the prompt, the agent CLI call and the parsing of its pick.
- `store.py`: the secret stores, OS keyring first and Vault as fallback. It is the only place a password is kept.
- `totp.py`: RFC 6238 codes computed in-process, so a seed never leaves.
- `workhorse.py`: the `0600`-before-content file write the workhorse integration uses.
