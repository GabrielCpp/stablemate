"""Hand a dying run to something that will tell a human about it.

A run that fails unattended is invisible until someone thinks to look. `groom status`
lists only *live* runs, so a run that ended is simply absent from it, and the evidence
that it ended badly — `workhorse.terminal="fail"` and `error.class` on the root span —
is only found by a poller that already suspected something. That is fine when an
operator is watching. The case this exists for is the one where nobody is: the run dies
at 03:00 and the next eight hours are spent not running.

So the driver spawns an operator-configured command on its way out. What that command
*is* is deliberately not this module's business — notify, open a terminal, start a
headless repair, post to a channel — because the right answer depends on where the
operator is, and a hook that hard-codes one is a hook that is wrong for everyone else.

**It cannot hand the operator a console, and must not pretend to.** A detached run has
no controlling terminal: stdin is `/dev/null`, stdout is a log file, and the process has
usually been reparented to init. A child that inherited that stdio would read EOF and
write into a log nobody is tailing. What a child *can* do is reach a display, a message
bus, or a terminal that already exists — which is why it is spawned in its own session
with its stdio closed.

There are two ways to be told, and they answer different questions:

* **A terminal you already have** (:func:`write_to_tty`, `--on-fail-pid`). Name a PID and
  the failure is printed on that process's terminal. Nothing is spawned, nothing has to
  survive a session, and it works the same over SSH — the terminal is the operator's, not
  the run's. The limit is exact and worth stating plainly: this **writes to the screen,
  it does not type into the program**. Linux ≥ 6.2 ships `dev.tty.legacy_tiocsti=0`, so
  the ioctl that pushed characters into another terminal's *input* queue is refused;
  a shell or an agent sitting at that terminal sees the text appear and is not prompted
  by it. It wakes a human, or an agent whose loop is already reading that pane. It does
  not answer for one.
* **A command** (:func:`spawn`, `--on-fail`). Everything else: `notify-send`, a chat
  webhook, opening a window, starting a headless repair run.

Both may be set; the tty write happens first, because it is the one that cannot fail
halfway.

Three properties hold no matter what the command does, because the alternative in each
case is worse than not notifying at all:

* **It never fails the run.** A failing hook would replace the workflow's diagnosis with
  a diagnosis of the hook — the operator arrives to a message about a missing binary and
  no idea which story broke.
* **It never blocks the run's exit.** The process is finalizing telemetry and releasing
  its control socket. `Popen` and walk away; the child is reparented and lives on.
* **It never recurses.** `WORKHORSE_ON_FAIL` is stripped from the child's environment,
  so a hook that launches an agent that launches another run cannot arm the same hook
  again and fork-bomb the machine on a bad night.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The variables the driver reads its hook from, and the names stripped from the child.
#: Module-level so the strip and the read can never drift apart.
ON_FAIL_ENV = "WORKHORSE_ON_FAIL"
ON_FAIL_PID_ENV = "WORKHORSE_ON_FAIL_PID"

#: Pseudo-terminal character-device majors (`Documentation/admin-guide/devices.txt`).
#: A pts device is major 136-143, minor = the number under `/dev/pts/`.
_PTS_MAJOR_LO = 136
_PTS_MAJOR_HI = 143


@dataclass(frozen=True)
class Failure:
    """Everything a hook needs to say something specific about a run that died.

    A record rather than eight parameters because it is passed twice — once rendered for
    a human on a terminal, once flattened into a child's environment — and two argument
    lists drift.
    """

    run_id: str
    run_dir: str
    workflow: str = ""
    repo: str = ""
    node: str = ""
    error: str = ""
    error_class: str = ""
    #: What the operator types next. Carried explicitly because it is the one thing they
    #: cannot reconstruct from the rest: the run dir does not name the `workhorse-<name>`
    #: entry point that owns it.
    resume_cmd: str = ""

    def env(self) -> dict[str, str]:
        """The parent environment plus this failure, for a spawned hook.

        Passed as environment rather than as argv so the configured command stays a
        one-liner an operator can put in a config file — `notify-send "$WORKHORSE_RUN_ID
        failed"` rather than a positional contract they have to look up.
        """
        env = dict(os.environ)
        env.pop(ON_FAIL_ENV, None)
        env.pop(ON_FAIL_PID_ENV, None)
        env.update(
            WORKHORSE_RUN_ID=self.run_id,
            WORKHORSE_RUN_DIR=self.run_dir,
            WORKHORSE_WORKFLOW=self.workflow,
            WORKHORSE_REPO=self.repo,
            WORKHORSE_NODE=self.node,
            WORKHORSE_ERROR=self.error,
            WORKHORSE_ERROR_CLASS=self.error_class,
            WORKHORSE_RESUME_CMD=self.resume_cmd,
        )
        return env

    def banner(self) -> str:
        """The failure as text for a terminal that is not this run's.

        Leading and trailing blank lines on purpose: this lands in the middle of whatever
        the operator was already looking at, so it has to be findable by eye in a scroll
        buffer rather than merely present.
        """
        lines = [
            "",
            "=" * 72,
            f"WORKHORSE RUN FAILED: {self.run_id}",
            "=" * 72,
        ]
        for label, value in (
            ("workflow", self.workflow),
            ("node", self.node),
            ("repo", self.repo),
            ("run dir", self.run_dir),
            ("error", f"{self.error_class}: {self.error}" if self.error_class else self.error),
            ("resume", self.resume_cmd),
        ):
            if value:
                lines.append(f"  {label:<9}{value}")
        lines += ["=" * 72, ""]
        return "\n".join(lines) + "\n"


def tty_of(pid: int) -> str | None:
    """The terminal device `pid` is attached to, or None if it has none.

    Two sources, in that order, because each covers the other's blind spot. The process's
    own descriptors are checked first: they are the ground truth for where its output
    actually goes, and they stay right for a process whose *controlling* terminal is not
    where it writes. When all three are redirected — a program run with `>log 2>&1`, which
    is common enough to matter — nothing there names a terminal, so the controlling
    terminal recorded in `stat` is decoded from its device number instead.

    Returns a path that existed at the moment of the check. Nothing keeps it open, so a
    terminal closed between here and the write is a failed write, handled there.
    """
    proc = Path("/proc") / str(pid)
    for fd in ("0", "1", "2"):
        try:
            target = os.readlink(proc / "fd" / fd)
        except OSError:
            continue
        if target.startswith(("/dev/pts/", "/dev/tty")):
            return target
    try:
        # Field 7 of /proc/<pid>/stat is tty_nr. The comm field (2) may itself contain
        # spaces and parentheses, so the split starts after its closing one.
        stat = (proc / "stat").read_text()
        tty_nr = int(stat[stat.rindex(")") + 1 :].split()[4])
    except (OSError, ValueError):
        return None
    if tty_nr == 0:
        return None
    # Device numbers are packed 12 bits of major around 20 bits of minor.
    major = (tty_nr >> 8) & 0xFFF
    minor = (tty_nr & 0xFF) | ((tty_nr >> 12) & 0xFFF00)
    if _PTS_MAJOR_LO <= major <= _PTS_MAJOR_HI:
        return f"/dev/pts/{minor + (major - _PTS_MAJOR_LO) * 256}"
    return None


def write_to_tty(pid: int, text: str, logger: logging.Logger) -> bool:
    """Print `text` on the terminal `pid` is using. True if it landed.

    Not an injection: the text is *displayed*, not typed. See the module docstring for
    why the ioctl that would type it is refused by any current kernel.

    Fails quietly and specifically, because every way this goes wrong is a normal
    situation rather than a bug — the operator gave a PID that has since exited, or one
    that never had a terminal (a service, a browser), or one belonging to another user
    whose terminal this process may not write to.
    """
    device = tty_of(pid)
    if device is None:
        logger.warning("on-fail: pid %s has no terminal to write to", pid)
        return False
    try:
        with open(device, "w") as handle:
            handle.write(text)
    except OSError as exc:
        logger.warning("on-fail: could not write to %s (pid %s): %s", device, pid, exc)
        return False
    logger.info("on-fail: failure reported on %s (pid %s)", device, pid)
    return True


def spawn(command: str, env: dict[str, str], logger: logging.Logger) -> bool:
    """Start `command` detached from this process. True if it was started.

    Shell-interpreted on purpose: the hook comes from the operator's own config or their
    own command line, the same trust boundary as `$EDITOR`, and the recipes that make it
    useful are pipelines and `&&` chains. Nothing untrusted reaches it — the failure text
    travels in the environment, never spliced into the string.

    `start_new_session` is what makes the child outlive us. Without it the child stays in
    this run's process group and shares its session, so it dies with the group on the way
    out — a terminal window that opens and closes faster than it can be read, which is
    indistinguishable from a hook that was never configured.
    """
    # The repo is a convenience, not a requirement: a hook that opens an editor wants to
    # start there. But a run whose workspace was deleted (a scratch clone, a torn-down
    # container mount) must still be able to *report* that, so an unusable directory
    # falls back to this process's cwd rather than failing the spawn — which is how a
    # missing repo silenced the notification for the failure it caused.
    repo = env.get("WORKHORSE_REPO") or ""
    cwd = repo if repo and os.path.isdir(repo) else None
    try:
        subprocess.Popen(  # noqa: S602 - operator-supplied, see the docstring
            command,
            shell=True,
            env=env,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        # Deliberately swallowed: see the module docstring. The warning is the whole
        # report, and it lands in the run's own log where a postmortem will find it.
        logger.warning("on-fail hook could not be started (%s): %s", command, exc)
        return False
    logger.info("on-fail hook started: %s", command)
    return True


def notify_failure(
    failure: Failure,
    logger: logging.Logger,
    *,
    command: str = "",
    pid: int = 0,
) -> bool:
    """Report a failed run through whatever the operator configured. True if anything ran.

    The one call the driver makes, and the only place that knows both channels exist.
    Nothing configured is the overwhelmingly common case — most runs are launched by
    somebody who is sitting there watching them — so it is a cheap no-op that reads as
    nothing at the call site.

    Both channels are attempted independently: an operator who set a PID *and* a command
    asked for two notifications, and the terminal having gone away is not a reason to
    skip the webhook.
    """
    told = False
    if pid > 0:
        told = write_to_tty(pid, failure.banner(), logger) or told
    if command.strip():
        told = spawn(command, failure.env(), logger) or told
    return told
