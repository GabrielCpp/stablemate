"""Own the lifecycle of a QA/dev stack that must outlive a single agent turn.

The agent runner reaps per-turn grandchildren (a browser, an MCP server), but it
does **not** own the app or stack under test — that must be started *outside* any
agent turn, or it dies when the turn tears down. This module is the durable owner:
a workflow ``script`` node calls :func:`ensure_stack` before QA and
:func:`teardown_stack` after, so the stack is brought up, health-gated, and reaped
(or deliberately left up) by the workflow rather than backgrounded in an agent's
shell where node teardown kills it mid-build.

The logic here was proven in okf-builder's ``boot-app.py`` walkthrough launcher and
is generalized so both that workflow and the coder QA flow share one implementation.
Every function **returns** a plain dict and never calls ``sys.exit``/``print`` — the
thin CLI wrappers (e.g. ``boot-app.py``) own the JSON-to-stdout contract.

Two shapes of launch command are supported, told apart by what the process does
rather than by a mode flag:

  * a FOREGROUND server (``npm run dev``, uvicorn) stays alive; exiting during
    startup means it died, and teardown reaps its process group.
  * a BRING-UP command (``make dev-stack-test-db``, ``docker compose up -d``) exits 0
    once the stack it started is serving *elsewhere* — in containers this process
    does not own. A clean exit is therefore not death: keep polling health to the
    deadline. Nothing is in our process group to reap, so teardown runs the
    documented ``stop`` recipe if there is one, and otherwise leaves the stack up.

Every command in a manifest — ``launch``, ``stop``, and the ``prepare``/``seed``/``health``
steps — is a **shell** recipe, run through ``bash -c``. Pipes, ``&&``/``||`` guards,
redirection and ``&`` all mean what they say; see :data:`_SHELL`.

Boot is idempotent: if the documented ``identity`` marker is already serving the
entry URL (a leftover from a prior turn or a shared expensive stack), it is adopted
rather than double-bound, and no process group is reported so teardown won't kill a
process this run didn't start.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import urllib.request
from typing import Any

from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock

#: Manifest commands are **shell** recipes, not argv lists. The contract already asks for
#: something only a shell can express — an *idempotent* bring-up command is written
#: `guard || start`, and a bring-up command that hands the stack off backgrounds it with
#: `nohup … & disown`. Splitting those with `shlex` hands `||`, `|` and `&` to the first
#: binary as literal arguments: a coder-QA manifest whose launch read
#: `ss -ltn | grep -q ':8081 ' || (nohup firebase emulators:start … &)` ran as `ss -ltn '|'
#: grep …` and died with exit 255, so the run failed to boot a stack that was already up
#: and escalated to a human for a recipe that was correct all along.
#:
#: bash rather than `/bin/sh`, because `sh` is dash on Debian/Ubuntu and dash has no
#: `disown` — the same manifest would then fail at 127 instead of 255. `/bin/sh` only if
#: there is no bash at all.
_SHELL = shutil.which("bash") or "/bin/sh"


def _shell_argv(cmd: str) -> list[str]:
    """The argv that runs *cmd* as a shell recipe. See :data:`_SHELL`."""
    return [_SHELL, "-c", cmd]


BOOT_TIMEOUT_S = 30.0     # a foreground dev server; overridable via a manifest `boot_timeout`
POLL_INTERVAL_S = 0.5
TERM_GRACE_S = 5.0
STOP_TIMEOUT_S = 300.0    # ceiling on a documented `stop` recipe
STEP_TIMEOUT_S = 600.0    # ceiling on one `prepare`/`seed`/`health` step
HEALTH_WINDOW_S = 120.0   # window for the `health` gates to converge; via `health_timeout`
HEALTH_RETRY_S = 5.0      # pause between re-attempts of a gate that is not satisfied yet


def boot_timeout(raw: str, default: float = BOOT_TIMEOUT_S) -> float:
    """The documented boot timeout in seconds, else the foreground-server default.

    A bring-up command that builds images is minutes, not seconds; a manifest that
    says so gets its ceiling. Junk falls back rather than crashing the run.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def health_probe(url: str, identity: str = "") -> str:
    """``""`` when *url* is healthy; otherwise one clause saying why it is not.

    The two ways this fails need opposite repairs, and reporting them as one sends the
    repairer to the wrong file. *Nothing is answering* means fix the bring-up. *It
    answered, but the body does not carry the manifest's ``identity`` marker* means the
    stack is up and the **marker** is wrong — and the manifest author cannot see that,
    because a marker is checked against the body while every hand-check of a URL
    (``curl -sf -o /dev/null``) throws the body away.

    That is not hypothetical. A coder-QA manifest declared ``identity: "127.0.0.1:8081"``
    for a Firestore emulator whose root serves the body ``Ok`` — a host:port where a body
    substring was wanted, so the probe could never pass. The failure reached the operator
    as "the launch command did not serve http://localhost:8081/", the emulator answered
    200 to every hand-check, and the block was escalated to a human as a harness fault
    against a stack that was serving the whole time.

    There is deliberately no ``health_ok`` boolean wrapper beside this. Two names for one
    check are two seams, and a caller (or a test) that reaches for the boolean one silently
    misses whichever paths went through the other. ``if not health_probe(...)`` reads the
    same and there is only one thing to patch.
    """
    try:
        with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310 (loopback)
            if not 200 <= r.status < 400:
                return f"{url} answered HTTP {r.status}"
            if not identity:
                return ""
            body = r.read(1_000_000).decode("utf-8", errors="replace")
            if identity in body:
                return ""
            return (
                f"{url} answered HTTP {r.status}, but its body does not contain the "
                f"manifest's identity marker {identity!r} — the stack is serving and the "
                f"marker is what is wrong. `identity` is a substring of the *response "
                f"body*, not a host:port or a URL; drop it, or set it to something the "
                f"body really says (body began {body[:80]!r})."
            )
    except Exception as exc:  # noqa: BLE001 — any failure to reach it is "not healthy"
        return f"{url} is not answering ({type(exc).__name__}: {exc})"


def boot_app(
    launch_cmd: str,
    entry_url: str,
    health_path: str,
    app_cwd: str,
    repo_root: str,
    app_identity: str,
    timeout_s: float,
    *,
    adopt: bool = True,
    logger: logging.Logger,
    clock: Clock = SYSTEM_CLOCK,
) -> dict[str, str]:
    """Launch one app/stack and prove it healthy, or fail soft.

    Returns ``{boot_ok, entry_url, app_pid, app_pgid, reason}`` — ``app_pgid`` is empty
    when this run owns no process to reap (an adopted stack, or a bring-up command whose
    stack lives in containers), so teardown knows not to ``killpg`` a foreign group.

    ``reason`` is empty on success and otherwise says *why* bring-up did not end healthy,
    in this function's own words. The caller is expected to pass it on rather than
    substitute a summary of its own: the ways this fails (no launch command, a spawn that
    errored, a nonzero exit, a deadline with nothing answering, a deadline with the wrong
    ``identity`` marker) call for repairs in different files, and a caller that flattens
    them to "the launch command did not serve <url>" names the wrong one four times out of
    five. See :func:`health_probe`.

    *adopt*: when True (the default, and how a read-only walkthrough uses it), an app
    already serving the identity is reused as-is. A caller that mutates the code the app
    is built from — where a stack left serving from a prior run is *stale* — passes
    ``adopt=False`` to force the (idempotent, self-freshening) launch to run instead.

    *clock*: the boot window is measured and waited on through this, so a test that
    asserts how many polls a 30-second window buys states the window instead of racing
    the machine it runs on. Defaulted rather than required — a workflow node calls this
    with a manifest and a logger, and the real clock is what it means.
    """
    health_path = health_path or "/"
    app_cwd = app_cwd or "."
    repo_root = repo_root or app_cwd
    health_url = entry_url.rstrip("/") + "/" + health_path.lstrip("/")

    if not launch_cmd:
        logger.warning("no launch command supplied — cannot boot the app under test")
        return {"boot_ok": "no", "entry_url": entry_url, "app_pid": "", "app_pgid": "",
                "reason": "the manifest declares no launch command, so there is nothing to "
                          "bring the app up with"}

    # Idempotent reuse: something already serving here → adopt it, own nothing. Safe
    # only with an identity marker; without one, start the documented command and prove
    # that owned process became healthy instead of adopting an arbitrary listener.
    if adopt and app_identity and not health_probe(health_url, app_identity):
        logger.info("adopting the app already serving %s (identity %r matched); "
                    "teardown will not reap it", health_url, app_identity)
        return {"boot_ok": "yes", "entry_url": entry_url, "app_pid": "", "app_pgid": "",
                "reason": ""}

    logger.info("booting app: %s (cwd %s), waiting up to %.0fs for %s",
                launch_cmd, app_cwd, timeout_s, health_url)
    try:
        proc = subprocess.Popen(  # noqa: S603 (documented recipe, loopback stack)
            _shell_argv(launch_cmd), cwd=app_cwd,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        logger.warning("launch command %r could not be spawned: %s", launch_cmd, exc)
        return {"boot_ok": "no", "entry_url": entry_url, "app_pid": "", "app_pgid": "",
                "reason": f"the launch command could not be spawned at all "
                          f"({type(exc).__name__}: {exc})"}

    pgid = os.getpgid(proc.pid)
    detached = False  # the command returned; whatever it started serves outside our pgid
    # Why the last probe said no. Kept so the give-up below reports the reason and not
    # merely the symptom — see :func:`health_probe`.
    why = ""
    deadline = clock.monotonic() + timeout_s
    while clock.monotonic() < deadline:
        # Health first: a bring-up command can exit the instant the stack is serving, so
        # checking liveness first would race a successful boot into a spurious failure.
        why = health_probe(health_url, app_identity)
        if not why:
            if detached:
                logger.info("app is healthy at %s (brought up by a command that has "
                            "since exited — this run owns no process to reap)", health_url)
                return {"boot_ok": "yes", "entry_url": entry_url, "app_pid": "",
                        "app_pgid": "", "reason": ""}
            logger.info("app is healthy at %s (pid %d, pgid %d)", health_url, proc.pid, pgid)
            return {"boot_ok": "yes", "entry_url": entry_url, "reason": "",
                    "app_pid": str(proc.pid), "app_pgid": str(pgid)}
        if not detached and proc.poll() is not None:
            if proc.returncode != 0:
                logger.warning("app exited with code %s during startup", proc.returncode)
                return {"boot_ok": "no", "entry_url": entry_url, "app_pid": "",
                        "app_pgid": "",
                        "reason": f"the launch command exited with code {proc.returncode} "
                                  f"during startup"}
            # Exit 0 with nothing serving yet: a bring-up command that handed the app off
            # to something it doesn't own (containers, a supervisor). Not death — keep
            # polling health to the deadline.
            logger.info("launch command exited cleanly without serving yet — treating it "
                        "as a bring-up command and waiting for %s", health_url)
            detached = True
        clock.sleep(POLL_INTERVAL_S)

    if detached:
        logger.warning("app was not healthy within %.0fs after the bring-up command "
                       "exited — failing soft; anything it started is still up. %s",
                       timeout_s, why)
        return {"boot_ok": "no", "entry_url": entry_url, "app_pid": "", "app_pgid": "",
                "reason": why}

    logger.warning("app was not healthy within %.0fs — killing pgid %d and failing soft. %s",
                   timeout_s, pgid, why)
    _killpg(pgid, signal.SIGKILL)
    return {"boot_ok": "no", "entry_url": entry_url, "app_pid": "", "app_pgid": "",
            "reason": why}


def teardown_app(
    pgid_arg: str, stop_cmd: str, app_cwd: str, *,
    logger: logging.Logger, clock: Clock = SYSTEM_CLOCK,
) -> dict[str, str]:
    """Reap a booted app, run its documented stop recipe, or deliberately leave it up.

    Returns ``{torn_down}`` — ``"yes"`` when reaped, ``"skipped"`` when left up on
    purpose (no owned process group and no stop recipe: an adopted or self-standing
    stack an expensive shared run is cheaper to leave running), ``"no"`` on a stop
    recipe that failed.
    """
    try:
        pgid = int(pgid_arg)
    except (TypeError, ValueError):
        # No pgid: boot adopted a process it didn't start, or the launch was a bring-up
        # command whose stack lives outside our group. A documented stop recipe is the
        # only way to reap the latter.
        if stop_cmd:
            logger.info("no app_pgid — running the documented stop recipe: %s", stop_cmd)
            try:
                done = subprocess.run(  # noqa: S603 (documented recipe, loopback stack)
                    _shell_argv(stop_cmd), cwd=app_cwd or ".",
                    capture_output=True, text=True, timeout=STOP_TIMEOUT_S,
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                logger.warning("stop recipe %r failed: %s — the app may still be running",
                               stop_cmd, exc)
                return {"torn_down": "no"}
            if done.returncode != 0:
                logger.warning("stop recipe exited %d — the app may still be running: %s",
                               done.returncode, (done.stderr or "").strip()[:500])
                return {"torn_down": "no"}
            return {"torn_down": "yes"}
        logger.info("teardown skipped — no app_pgid and no stop recipe "
                    "(nothing this run owns; an adopted or self-standing app is left up)")
        return {"torn_down": "skipped"}
    logger.info("tearing down app process group %d", pgid)
    if not _killpg(pgid, signal.SIGTERM):
        return {"torn_down": "yes"}  # already gone
    deadline = clock.monotonic() + TERM_GRACE_S
    while clock.monotonic() < deadline:
        if not _killpg(pgid, 0):  # still alive?
            return {"torn_down": "yes"}
        clock.sleep(POLL_INTERVAL_S)
    _killpg(pgid, signal.SIGKILL)
    return {"torn_down": "yes"}


def ensure_stack(
    manifest: dict[str, Any], *, repo_root: str | None = None,
    logger: logging.Logger, clock: Clock = SYSTEM_CLOCK,
) -> dict[str, str]:
    """Bring a whole QA stack to ready from a declarative manifest, or fail soft.

    Manifest keys (all optional except a way to prove readiness):

      * ``entry_url`` / ``health_path`` — the HTTP readiness probe (default ``/``).
      * ``identity`` — a marker string in the served body; the readiness signal, and a
        precondition for reuse.
      * ``reuse`` — when it is safe to adopt a stack already serving, rather than bring it
        up again: ``if-fresh`` (default), ``always``, or ``never`` (see below).
      * ``fresh`` — a probe command (exit 0 ⇔ the running stack reflects the current code)
        that gates adoption under ``reuse: if-fresh``.
      * ``app_cwd`` / ``repo_root`` / ``boot_timeout`` — launch context and ceiling.
      * ``launch`` — an **idempotent, self-freshening** bring-up command (e.g.
        ``docker compose up -d --build``) owned by :func:`boot_app`. Safe to re-run: on
        no change it is a cache-hit no-op; on changed code it rebuilds and recreates.
      * ``stop`` — the teardown recipe; absent means leave an expensive stack up.
      * ``prepare`` — ordered blocking steps run *before* launch (deps/build/stack-up).
      * ``seed`` — ordered **idempotent** steps run *after* the stack serves (fixtures).
      * ``health`` — ordered command gates run last (e.g. a ``stack-health`` target). A
        gate that fails is re-attempted until the phase's window expires, because boot
        proves only the entry URL answers and a gate may assert on a slower sibling.
      * ``health_timeout`` — that window in seconds (default 120), shared by all gates.

    **Staleness — why adoption is earned, not automatic.** A stack left serving from a
    prior story was built from *older* code; adopting it blindly runs QA against a stale
    build and reports a false result. So a serving stack is adopted only when the reuse
    policy proves it is safe:

      * ``if-fresh`` (default) — adopt only if a ``fresh`` probe is declared and passes;
        otherwise re-run ``launch`` (which rebuilds). With no ``fresh`` probe, the default
        never adopts — it always re-launches, so staleness is impossible unless the author
        opts out. A code-embedding service that must be live is better run from source in
        the QA plan's ``background:`` block, where it always reflects the working tree.
      * ``always`` — adopt whenever the identity is serving. Reserve this for a
        **code-independent** stack (a stock DB/emulator holding fixtures) whose build does
        not depend on the code under test; it is the only case where skipping bring-up and
        re-seed is safe.
      * ``never`` — never adopt; always re-run ``launch``.

    ``prepare``/``seed``/``health``/``fresh`` entries are a bare command string or a mapping
    with ``run`` (+ optional ``working-directory``/``timeout``). Returns
    ``{ready, adopted, entry_url, app_pid, app_pgid[, failed_step, error]}`` — ``error``
    being the failing step's own message, so a caller routing the failure to a repairer
    can say what broke and not merely which step did.
    """
    app_cwd = manifest.get("app_cwd") or "."
    repo_root = repo_root or manifest.get("repo_root") or app_cwd
    entry_url = manifest.get("entry_url", "")
    health_path = manifest.get("health_path") or "/"
    identity = manifest.get("identity", "")
    reuse = str(manifest.get("reuse", "if-fresh"))
    timeout_s = boot_timeout(str(manifest.get("boot_timeout", "")))
    launch_cmd = manifest.get("launch", "")
    health_url = entry_url.rstrip("/") + "/" + health_path.lstrip("/") if entry_url else ""

    def _fail(step: str, error: str = "", pid: str = "", pgid: str = "") -> dict[str, str]:
        # `error` carries the step's own message out with the verdict: the caller's job is
        # usually to route the failure to whoever repairs it, and a step name alone ("the
        # health gate") does not say what to repair. Logging it is not enough — the log is
        # not what crosses the node boundary.
        return {"ready": "no", "adopted": "no", "entry_url": entry_url,
                "app_pid": pid, "app_pgid": pgid, "failed_step": step, "error": error}

    # Adopt-if-serving — but only when the reuse policy proves the running stack is not
    # stale (built from older code). Otherwise fall through and re-run the (idempotent,
    # self-freshening) launch so QA never runs against a stale build.
    if identity and health_url and not health_probe(health_url, identity):
        if _may_adopt(reuse, manifest, app_cwd, timeout_s, logger):
            logger.info("adopting the stack already serving %s (reuse=%s)", health_url, reuse)
            return {"ready": "yes", "adopted": "yes", "entry_url": entry_url,
                    "app_pid": "", "app_pgid": ""}
        logger.info("stack serving %s but not adopted (reuse=%s) — re-running launch to "
                    "refresh it against current code", health_url, reuse)

    for i, step in enumerate(manifest.get("prepare") or []):
        ok, err = _run_step(step, app_cwd, timeout_s, logger, label=f"prepare[{i}]")
        if not ok:
            logger.warning("prepare[%d] failed: %s", i, err)
            return _fail(f"prepare[{i}]", err)

    app_pid = app_pgid = ""
    if launch_cmd:
        # adopt=False: ensure_stack owns the reuse decision above; the launch itself must
        # always run (and be self-freshening) once we have decided not to adopt.
        res = boot_app(launch_cmd, entry_url, health_path, app_cwd, repo_root,
                       identity, timeout_s, adopt=False, logger=logger, clock=clock)
        if res["boot_ok"] != "yes":
            # Report boot's *own* reason, not the step name. "the launch command did not
            # serve <url>" was this branch's message for every way bring-up can fail, and it
            # names the one repair — fix the launch recipe — that is wrong for half of them.
            # A manifest whose `identity` marker never appears in the served body reached the
            # repairer as a launch fault against a stack that was answering 200 the whole
            # time; two resolve passes hand-verified the URL, found it healthy, and escalated
            # it to a human as a harness bug. See :func:`health_probe`.
            return _fail("launch",
                         res.get("reason") or f"the launch command did not serve "
                                              f"{health_url or entry_url}",
                         res["app_pid"], res["app_pgid"])
        app_pid, app_pgid = res["app_pid"], res["app_pgid"]

    for i, step in enumerate(manifest.get("seed") or []):
        ok, err = _run_step(step, app_cwd, timeout_s, logger, label=f"seed[{i}]")
        if not ok:
            logger.warning("seed[%d] failed: %s", i, err)
            return _fail(f"seed[{i}]", err, app_pid, app_pgid)

    # One window for the whole `health` phase, retried rather than single-shot: boot only
    # proved the *entry URL* answers, and in a multi-service stack that is the fastest
    # service, not the last one. A gate asserting on its siblings therefore runs into a
    # stack that is still coming up — a spurious failure that routes an otherwise healthy
    # run into repair. Gates are documented as read-only assertions (`seed` owns the side
    # effects), so re-running one is safe.
    health_deadline = clock.monotonic() + boot_timeout(
        str(manifest.get("health_timeout", "")), default=HEALTH_WINDOW_S
    )
    for i, step in enumerate(manifest.get("health") or []):
        ok, err = _gate_until(
            step, app_cwd, timeout_s, logger,
            label=f"health[{i}]", deadline=health_deadline, clock=clock,
        )
        if not ok:
            logger.warning("health[%d] failed: %s", i, err)
            return _fail(f"health[{i}]", err, app_pid, app_pgid)

    logger.info("stack is ready at %s", health_url or entry_url or "(no entry url)")
    return {"ready": "yes", "adopted": "no", "entry_url": entry_url,
            "app_pid": app_pid, "app_pgid": app_pgid}


def teardown_stack(
    handles: dict[str, str], manifest: dict[str, Any], *,
    logger: logging.Logger, clock: Clock = SYSTEM_CLOCK,
) -> dict[str, str]:
    """Reap a stack :func:`ensure_stack` brought up, honouring the leave-up policy."""
    return teardown_app(
        handles.get("app_pgid", ""), manifest.get("stop", ""),
        manifest.get("app_cwd") or ".", logger=logger, clock=clock,
    )


# -- helpers ----------------------------------------------------------------------


def _may_adopt(
    reuse: str, manifest: dict[str, Any], app_cwd: str, timeout: float,
    logger: logging.Logger,
) -> bool:
    """Decide whether a stack already serving may be adopted, or must be re-launched.

    ``always`` trusts the operator's declaration that the stack is code-independent.
    ``never`` always rebuilds. ``if-fresh`` (the default) adopts only when a ``fresh``
    probe is declared *and* exits 0 — with no probe it refuses, so the default can never
    silently adopt a stale build.
    """
    if reuse == "always":
        return True
    if reuse == "never":
        return False
    # if-fresh (and any unknown value → the safe default)
    fresh = manifest.get("fresh")
    if not fresh:
        logger.info("reuse=if-fresh with no `fresh` probe — refusing to adopt "
                    "(cannot prove the running stack matches current code)")
        return False
    ok, err = _run_step(fresh, app_cwd, timeout, logger, label="fresh")
    if not ok:
        logger.info("`fresh` probe reports the running stack is stale (%s) — will re-launch", err)
    return ok


def _gate_until(
    step: Any, default_cwd: str, default_timeout: float, logger: logging.Logger,
    *, label: str, deadline: float, clock: Clock,
) -> tuple[bool, str]:
    """Run one gate, re-attempting a failure until *deadline*; report the last error.

    A gate that fails is not yet a verdict — a stack whose entry URL answers can still
    have siblings mid-start, so the first attempt reads "not up **yet**" as often as "not
    up". Waiting is what tells the two apart, and the deadline is what keeps waiting from
    becoming a stall. The window is shared by every gate in the phase, so a manifest with
    five gates waits as long in total as one with a single gate.
    """
    attempt = 0
    while True:
        attempt += 1
        ok, err = _run_step(step, default_cwd, default_timeout, logger, label=label)
        remaining = deadline - clock.monotonic()
        if ok or remaining <= 0:
            return ok, err
        logger.info("%s not satisfied on attempt %d (%s) — retrying for up to %.0fs more",
                    label, attempt, err, remaining)
        clock.sleep(HEALTH_RETRY_S)


def _run_step(
    step: Any, default_cwd: str, default_timeout: float,
    logger: logging.Logger, *, label: str,
) -> tuple[bool, str]:
    """Run one blocking manifest step (a command string or ``{run, ...}`` mapping)."""
    if isinstance(step, str):
        cmd, cwd, timeout = step, default_cwd, default_timeout
    else:
        cmd = step.get("run", "")
        cwd = step.get("working-directory") or step.get("cwd") or default_cwd
        timeout = boot_timeout(str(step.get("timeout", "")), default=STEP_TIMEOUT_S)
    if not cmd:
        return False, f"{label}: no command"
    logger.info("running %s: %s (cwd %s)", label, cmd, cwd)
    try:
        done = subprocess.run(  # noqa: S603 (documented recipe, loopback stack)
            _shell_argv(cmd), cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if done.returncode != 0:
        return False, (done.stderr or "").strip()[:500]
    return True, ""


def _killpg(pgid: int, sig: int) -> bool:
    """Signal a process group; return False when it is already gone."""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True
