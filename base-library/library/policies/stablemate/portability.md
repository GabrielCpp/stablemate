---
name: portability
description: "The standing platform obligation every piece of Python here carries, in three tiers: a published package runs on Linux, macOS and Windows; process supervision is POSIX and branches explicitly; the container harness is Linux by construction and says so. Carries the portable replacement for each non-portable API and the rule that a platform branch owes a test on both sides. Resident every turn because nothing in the loop runs the other platforms — the code that breaks them is written without any reason to go looking."
---

## Portability, in three tiers

> "Works on my machine" and "works on Linux" are the same sentence here, because the
> container and CI are both Linux. That is exactly why the *other* platforms break
> silently: nothing in the loop runs them.

A blanket "everything must run everywhere" would be false the day it was written — the
container harness calls `os.getuid()` and registers `SIGUSR1`, and it is correct to.
So the rule is per-tier, and the tier is a property of **where the code lives**.

| Tier | What | Must run on |
|---|---|---|
| 1 | The published packages — `core`, `farrier`, `ostler`, `groom`, `saddlebag`, `workhorse` the library, `workhorse_workflows` | **Linux, macOS, Windows** |
| 2 | Process supervision — anything that spawns something it must later signal or reap | **Linux and macOS**, branching explicitly |
| 3 | The container harness — `workhorse/supervisor.py`, `workhorse/livesource.py`, `Dockerfile`, `compose.yaml` | **Linux only**, said out loud |

Tier 1 is the obligation that actually bites: someone `pip install`s `ostler` on a Mac or
a Windows box and it has to work. Nothing in this repo's CI proves that, so it is a
discipline, backed by `make check-portability` for the mechanical half.

### Tier 1 — write it portably

| Don't | Do | Why |
|---|---|---|
| `"/tmp/foo"` | `tempfile.mkdtemp()` / `TemporaryDirectory()` | Windows has no `/tmp`; `$TMPDIR` differs on macOS |
| `Path("~/.config/x")` | `platformdirs.user_config_dir()` | macOS uses `~/Library/…`, Windows `%APPDATA%` |
| `"a" + "/" + "b"` | `Path("a") / "b"` | `pathlib` already knows the separator |
| `os.getuid()`, `os.umask()` | don't — or move it to tier 2/3 | absent on Windows |
| `signal.SIGKILL`, `SIGUSR1` | `SIGTERM` / `SIGINT`, or tier 2 | only `SIGTERM`, `SIGINT`, `SIGBREAK` exist on Windows |
| `subprocess.run("ls | wc -l", shell=True)` | a list argv, or do it in Python | no POSIX shell on Windows |
| `shutil.which("bash")` | check, and have a fallback | not guaranteed anywhere but Linux |
| an executable named `foo` | `foo.exe` on Windows | `shutil.which` handles this — use it |

Two that look portable and are not:

- **`os.rename` onto an existing file** raises on Windows. `os.replace` is the atomic
  one everywhere, and it is what a checkpoint or a generated-file write wants.
- **An open file cannot be deleted or replaced on Windows.** Close it first. A
  `TemporaryDirectory()` holding a file some subprocess still has open fails to clean
  up — which surfaces as a teardown error, not as the bug it is.

### Tier 2 — POSIX, and the branch owes a test on both sides

Process supervision cannot be written portably; it is `killpg`, process groups and
`start_new_session`, and Windows has none of those. That is fine — declare the site and
branch on the real difference.

**The failure mode is not the branch. It is the assertion.** The code below is correct on
both platforms:

```python
def _signal_group(pid: int, sig: int) -> bool:
    """False once the group has nothing left to signal."""
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):   # ESRCH on Linux, EPERM on macOS
        return False
    return True
```

…and the test written beside it was not:

```python
assert _kill_pid(pid) == 0   # "gone already, no signal landed"
```

That holds on macOS, where an all-zombie group answers EPERM and the kill path stops.
On Linux a zombie is still a process: `killpg` **succeeds**, the escalation runs its full
SIGINT → SIGTERM → SIGKILL window, and the call returns `-9` three seconds later. The
production code handled the difference; the test asserted one platform's observable
outcome, and failed on the *other* Unix — before Windows was ever in the picture.

So: **when you branch on platform, the test accepts both branches** — assert the
invariant the docstring claims (here: teardown survives, and does not raise), not the
one platform's number. `sys.platform` in a test is a smell unless it guards a `skipif`.

### Tier 3 — Linux only, stated

`workhorse/supervisor.py` runs as PID 1's child inside an Ubuntu image. `os.getuid()`,
`os.umask(0o002)`, `faulthandler.register(signal.SIGUSR1)` and setgid semantics are all
load-bearing there and none of them exist on Windows. Say so in the module docstring so
nobody portably "fixes" it, and keep it out of the import path of anything in tier 1.

### Declaring a site

`{{ template.check_portability_script | default("scripts/check_portability.py") }}` flags the
non-portable APIs above inside tier-1 source.

Which import roots are tier 1, and which sites earned their POSIX call, are the repo's to
state in `[check-portability]` of its `.agent-checks.toml`; a repo that declares no tier 1
publishes nothing and the check passes. A genuine tier-2/3 site goes in `allow` with its
reason, and the reason is printed on any failure — same shape as the parse-don't-match guard. The
entry is checked for staleness too: once a module stops making the call, the exemption that
excuses it is a finding. If you are adding a POSIX call to a package a user pip-installs, the
declaration is the moment to ask whether the code belongs there at all.

### The boundary

This is a guard against known silent failures, not a proof of portability. It reads
import and call shapes; it cannot tell you that a subprocess you spawn behaves
differently, that a path you build from config is absolute on one OS, or that a file
handle you left open blocks a delete. The only proof is running the suite on the platform
— and nothing here does that yet, which is why the tiers are written down instead.

The sibling rule — a format with a grammar is read with its parser, never a regex — is the
parse-don't-match standard, and it is enforced the same way.
