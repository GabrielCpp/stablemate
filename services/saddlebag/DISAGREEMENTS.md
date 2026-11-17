# Where the pages and saddlebag disagree

Found while writing this book from the README. Each entry names the page, the claim, and what the tool does.

1. `saddlebag/README.md`, "What each verb guarantees": an `--env VAR=NAME.totp` binding gives "the current TOTP code", and
   "a TOTP seed leaves the store only as a computed six-digit code, and only by being typed". `exec` calls `verb_env`
   (`saddlebag/saddlebag/verbs.py`), which reads the stored value of the field as it is, and `exec` puts it in the
   child's environment. Only `fill` and `type` compute the code (`_typable`). The seed itself reaches the command, and
   `exec` masks it in the output when it is eight characters or more. Classification: app wrong. The book never binds a
   stored seed, because the code it should hand changes every thirty seconds and no claim can name it. It plays a totp
   binding on a secret that holds no seed, and the refusal is the same either way.

2. `saddlebag serve --vault-addr URL` with a token on stdin, when nothing answers at the address:
   `cmd_serve` (`saddlebag/saddlebag/cli.py`) catches `VaultError` around `VaultStore(...)`, and the constructor calls
   `is_authenticated()` (`saddlebag/saddlebag/vault.py`), which lets the connection error of the HTTP client through.
   The command ends in a traceback and exit 1 where a one-line "saddlebag: ..." refusal is meant, as for a rejected
   token. Classification: app wrong. The book plays serve only to the checks before the Vault is reached.
