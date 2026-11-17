# Where paddock disagrees with itself

Found while writing this book from the source and the README it replaced. Each entry names the call, what the
source says and what the app did.

1. `paddock run <benchmark> <task>` on a benchmark whose tasks.py raises when it is imported.
   - Step: found by hand in a sandbox with a second benchmark whose tasks.py is `raise RuntimeError("bad")`.
   - Source: `loader.load_all` (`paddock/paddock/loader.py`) catches the error and `cmd_list` prints `<name>  cannot
     load: RuntimeError: bad` and exits 1. `loader.load_task`, which `cmd_run` and `cmd_resume` call, does not catch
     it, and `main` handles only ConfigError, HomeConfigError, TaskError, RunError and SandboxError.
   - App did: a Python traceback ending in the RuntimeError, exit 1.
   - Classification: app inconsistent. The book keeps what `list` says and does not play the run, since a traceback
     has no stable text.
