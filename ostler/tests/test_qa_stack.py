"""Tests for the durable stack supervisor (:mod:`ostler.qa.stack`).

The boot/teardown cases were ported from okf-builder's boot-app white-box tests when
the logic moved here; they now drive the library functions directly (which return
dicts) rather than the CLI wrapper. The ensure_stack/teardown_stack cases are new.
"""
from __future__ import annotations

import json
import logging

import pytest

from _fakes import FakeClock
from ostler.qa import stack

LOG = logging.getLogger("test-stack")

# Captured at import time, before the autouse fixture below stubs the module attribute:
# the port-diagnosis unit tests exercise the real function through this name.
_REAL_PORT_HINT = stack._port_hint


@pytest.fixture(autouse=True)
def _isolated_ownership_records(tmp_path, monkeypatch) -> None:
    """Point the stack's ownership records at a per-test cache dir.

    ensure_stack/teardown_stack read and write ``<cache>/qa-stacks/`` as a side effect;
    without this every test would share the developer's real ``~/.cache/stablemate``.
    """
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "stablemate-cache"))
    # And stub the port diagnosis: it shells out to `ss` on every boot failure, which
    # both races the machine's real listeners and trips over tests' fake Popen objects.
    monkeypatch.setattr(stack, "_port_hint", lambda _url: "")


def test_health_requires_documented_identity(monkeypatch) -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return b"<title>groom</title>"

    monkeypatch.setattr(stack.urllib.request, "urlopen", lambda *_a, **_kw: Response())

    assert stack.health_probe("http://127.0.0.1:8787", "<title>groom</title>") == ""

    # And the miss says the stack is serving and the *marker* is wrong — the distinction
    # the caller needs, because these two failures are repaired in different files.
    why = stack.health_probe("http://127.0.0.1:8787", "<title>Acme</title>")
    assert why
    assert "<title>Acme</title>" in why       # names the marker that did not match
    assert "answered HTTP 200" in why         # ...and says the stack answered anyway
    assert "<title>groom</title>" in why      # quotes what the body really said


def test_boot_timeout_falls_back_when_undocumented_or_junk() -> None:
    assert stack.boot_timeout("1800") == 1800.0
    assert stack.boot_timeout("") == stack.BOOT_TIMEOUT_S
    assert stack.boot_timeout("soon") == stack.BOOT_TIMEOUT_S
    assert stack.boot_timeout("0") == stack.BOOT_TIMEOUT_S
    # a step ceiling can override the default
    assert stack.boot_timeout("", default=stack.STEP_TIMEOUT_S) == stack.STEP_TIMEOUT_S


def test_boot_treats_a_clean_exit_as_a_bring_up_command(monkeypatch) -> None:
    """`make dev-stack-test-db` exits 0 once the stack serves — that is not death."""
    # Healthy only from the third poll: the stack comes up strictly after make returns,
    # so a run that failed on the clean exit would never see it.
    polls = {"n": 0}

    def health(*_args, **_kwargs) -> str:
        polls["n"] += 1
        return "" if polls["n"] >= 3 else "not answering yet"

    class Exited:
        pid = 4242
        returncode = 0

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(stack, "health_probe", health)
    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Exited())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)

    out = stack.boot_app(
        "make dev-stack-test-db", "http://localhost:3000", "/", ".", ".", "", 60,
        logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "yes"
    # Owns nothing: the stack lives in containers, so teardown must not killpg 4242.
    assert out["app_pgid"] == ""
    assert out["app_pid"] == ""


def test_boot_still_fails_when_the_launch_command_errors(monkeypatch) -> None:
    """A nonzero exit is a real death — the detached path must not swallow it."""
    class Died:
        pid = 4242
        returncode = 2

        def poll(self) -> int:
            return 2

    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Died())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)

    out = stack.boot_app(
        "make dev-stack-test-db", "http://localhost:3000", "/", ".", ".", "", 60,
        logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "no"


def test_boot_adopts_a_stack_already_serving(monkeypatch) -> None:
    """An identity already serving the entry URL is reused, not double-bound."""
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    monkeypatch.setattr(
        stack.subprocess, "Popen",
        lambda *_a, **_kw: pytest.fail("must not launch when adopting"),
    )
    out = stack.boot_app(
        "make dev-stack-test-db", "http://localhost:3000", "/", ".", ".",
        "<title>Acme</title>", 60, logger=LOG,
    )
    assert out == {"boot_ok": "yes", "entry_url": "http://localhost:3000",
                   "app_pid": "", "app_pgid": "", "reason": ""}


def test_boot_app_adopt_false_launches_even_when_serving(monkeypatch) -> None:
    """adopt=False forces the (self-freshening) launch even if a stale stack is serving."""
    launched = {"n": 0}

    class Exited:
        pid = 4242
        returncode = 0

        def poll(self) -> int:
            return 0

    def popen(*_a, **_kw):
        launched["n"] += 1
        return Exited()

    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    monkeypatch.setattr(stack.subprocess, "Popen", popen)
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)

    out = stack.boot_app(
        "docker compose up -d --build", "http://localhost:3000", "/", ".", ".",
        "<title>Acme</title>", 60, adopt=False, logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "yes"
    assert launched["n"] == 1  # did NOT adopt; ran the launch


def test_teardown_without_a_pgid_runs_the_documented_stop_recipe(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stderr = ""

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return Done()

    monkeypatch.setattr(stack.subprocess, "run", fake_run)

    out = stack.teardown_app("", "make dev-stack-test-db-down", ".", logger=LOG)

    assert calls == [[stack._SHELL, "-c", "make dev-stack-test-db-down"]]
    assert out["torn_down"] == "yes"


def test_teardown_leaves_the_stack_up_when_no_stop_recipe_is_documented(monkeypatch) -> None:
    """The chosen policy: an expensive shared stack is cheaper to leave running."""
    monkeypatch.setattr(
        stack.subprocess, "run", lambda *_a, **_kw: pytest.fail("ran a command"),
    )
    out = stack.teardown_app("", "", ".", logger=LOG)
    assert out["torn_down"] == "skipped"


# -- ensure_stack / teardown_stack ------------------------------------------------


def test_ensure_stack_reuse_always_adopts_without_running_prepare(monkeypatch) -> None:
    """reuse=always (code-independent stack) short-circuits before prepare/launch.

    This manifest declares no seed or health steps, so adoption runs nothing at all.
    """
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    monkeypatch.setattr(
        stack, "_run_step", lambda *_a, **_kw: pytest.fail("ran a step while adopting"),
    )
    monkeypatch.setattr(
        stack, "boot_app", lambda *_a, **_kw: pytest.fail("booted while adopting"),
    )
    out = stack.ensure_stack(
        {"entry_url": "http://localhost:8080", "identity": "acme", "reuse": "always",
         "prepare": ["make deps"], "launch": "make dev-stack-test-db"},
        logger=LOG,
    )
    assert out["ready"] == "yes"
    assert out["adopted"] == "yes"
    assert out["app_pgid"] == ""


def test_ensure_stack_default_refuses_to_adopt_a_stale_serving_stack(monkeypatch) -> None:
    """The default (if-fresh, no `fresh` probe) never adopts — it re-launches to refresh.

    This is the staleness guard: a stack serving from a prior story was built from older
    code, so adopting it blindly would run QA against a stale build.
    """
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")  # something IS serving
    launched = {"n": 0}

    def boot(*_a, **kw):
        launched["n"] += 1
        assert kw["adopt"] is False  # ensure_stack owns the decision; launch must run
        return {"boot_ok": "yes", "entry_url": "u", "app_pid": "", "app_pgid": ""}

    monkeypatch.setattr(stack, "boot_app", boot)
    out = stack.ensure_stack(
        {"entry_url": "http://localhost:8080", "identity": "acme",
         "launch": "docker compose up -d --build"},
        logger=LOG,
    )
    assert out["ready"] == "yes"
    assert out["adopted"] == "no"
    assert launched["n"] == 1  # re-launched instead of adopting the stale stack


def test_ensure_stack_if_fresh_adopts_when_probe_passes(monkeypatch) -> None:
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    monkeypatch.setattr(stack, "_run_step", lambda *_a, **_kw: (True, ""))  # fresh passes
    monkeypatch.setattr(stack, "boot_app", lambda *_a, **_kw: pytest.fail("re-launched a fresh stack"))
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "reuse": "if-fresh",
         "fresh": "make stack-matches-head", "launch": "docker compose up -d --build"},
        logger=LOG,
    )
    assert out["adopted"] == "yes"


def test_ensure_stack_adoption_still_runs_seed_and_health(monkeypatch) -> None:
    """Adoption skips prepare and launch, never seed or health.

    Serving the identity proves the *process* survived, not its *state*: an emulator
    restarted between runs answers its identity from an empty store, and adopting it on
    the identity alone hands QA a stack with no fixtures.
    """
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    ran: list[str] = []
    monkeypatch.setattr(
        stack, "_run_step",
        lambda step, *_a, label="", **_kw: (ran.append(label) or (True, "")),
    )
    monkeypatch.setattr(
        stack, "_gate_until",
        lambda step, *_a, label="", **_kw: (ran.append(label) or (True, "")),
    )
    monkeypatch.setattr(
        stack, "boot_app", lambda *_a, **_kw: pytest.fail("re-launched an adoptable stack"),
    )
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "reuse": "always",
         "prepare": ["make deps"], "launch": "docker compose up -d --build",
         "seed": ["make seed"], "health": ["make stack-health"]},
        logger=LOG,
    )
    assert out["adopted"] == "yes"
    assert out["ready"] == "yes"
    assert ran == ["seed[0]", "health[0]"]  # prepare never ran; seed and health did


def test_ensure_stack_adopted_stack_failing_a_gate_falls_back_to_bring_up(monkeypatch) -> None:
    """An adopted stack that fails a health gate is not returned broken.

    The run falls back to a full bring-up — the launch recipe is idempotent and
    self-freshening, so re-running it is the repair, not a risk — and the second pass
    through the gates is what proves readiness.
    """
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    attempts = {"gate": 0}

    def gate(step, *_a, **_kw):
        attempts["gate"] += 1
        # first pass (adoption re-proof) finds the wiped store; after relaunch it holds
        return (attempts["gate"] > 1), ("empty store" if attempts["gate"] == 1 else "")

    monkeypatch.setattr(stack, "_gate_until", gate)
    monkeypatch.setattr(stack, "_run_step", lambda *_a, **_kw: (True, ""))
    launched = {"n": 0}
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: (launched.__setitem__("n", launched["n"] + 1)
                            or {"boot_ok": "yes", "entry_url": "u", "app_pid": "", "app_pgid": ""}),
    )
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "reuse": "always",
         "launch": "docker compose up -d --build", "health": ["make stack-health"]},
        logger=LOG,
    )
    assert launched["n"] == 1  # fell through to the real bring-up
    assert attempts["gate"] == 2
    assert out["adopted"] == "no"
    assert out["ready"] == "yes"


def test_ensure_stack_if_fresh_relaunches_when_probe_fails(monkeypatch) -> None:
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    # the fresh probe reports stale; every other step passes
    monkeypatch.setattr(
        stack, "_run_step",
        lambda step, *_a, label="", **_kw: ((label != "fresh"), "stale" if label == "fresh" else ""),
    )
    launched = {"n": 0}
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: (launched.__setitem__("n", launched["n"] + 1)
                            or {"boot_ok": "yes", "entry_url": "u", "app_pid": "", "app_pgid": ""}),
    )
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "reuse": "if-fresh",
         "fresh": "make stack-matches-head", "launch": "docker compose up -d --build"},
        logger=LOG,
    )
    assert out["adopted"] == "no"
    assert launched["n"] == 1


def test_ensure_stack_reuse_never_relaunches_even_when_serving(monkeypatch) -> None:
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    monkeypatch.setattr(
        stack, "_run_step", lambda *_a, **_kw: pytest.fail("ran a `fresh` probe under reuse=never"),
    )
    launched = {"n": 0}
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: (launched.__setitem__("n", launched["n"] + 1)
                            or {"boot_ok": "yes", "entry_url": "u", "app_pid": "", "app_pgid": ""}),
    )
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "reuse": "never",
         "fresh": "make stack-matches-head", "launch": "docker compose up -d --build"},
        logger=LOG,
    )
    assert out["adopted"] == "no"
    assert launched["n"] == 1


def test_ensure_stack_runs_prepare_launch_seed_health_in_order(monkeypatch) -> None:
    order: list[str] = []

    def run_step(step, _cwd, _to, _logger, *, label):
        order.append(label)
        return True, ""

    def boot(*_a, **_kw):
        order.append("launch")
        return {"boot_ok": "yes", "entry_url": "http://localhost:8080",
                "app_pid": "10", "app_pgid": "10"}

    # identity absent → no adopt; go through the full ordered path.
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(stack, "_run_step", run_step)
    monkeypatch.setattr(stack, "boot_app", boot)

    out = stack.ensure_stack(
        {
            "entry_url": "http://localhost:8080",
            "launch": "make dev-stack-test-db",
            "prepare": ["make deps"],
            "seed": ["make seed", "make seed-users"],
            "health": ["make stack-health"],
        },
        logger=LOG,
    )
    assert out == {"ready": "yes", "adopted": "no", "entry_url": "http://localhost:8080",
                   "app_pid": "10", "app_pgid": "10"}
    assert order == ["prepare[0]", "launch", "seed[0]", "seed[1]", "health[0]"]


def test_ensure_stack_fails_the_step_that_failed_and_stops(monkeypatch) -> None:
    ran: list[str] = []

    def run_step(step, _cwd, _to, _logger, *, label):
        ran.append(label)
        return (label != "seed[0]"), "boom"

    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(stack, "_run_step", run_step)
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "yes", "entry_url": "u", "app_pid": "9", "app_pgid": "9"},
    )
    out = stack.ensure_stack(
        {"entry_url": "u", "launch": "go", "seed": ["make seed", "make seed-more"]},
        logger=LOG,
    )
    assert out["ready"] == "no"
    assert out["failed_step"] == "seed[0]"
    # names *what* broke, not only where: the caller routes this to whoever repairs the
    # stack, and a step label alone does not say what to repair.
    assert out["error"] == "boom"
    # carries the booted handles so teardown can still act, and stops at the failure.
    assert out["app_pgid"] == "9"
    assert ran == ["seed[0]"]


def test_ensure_stack_retries_a_health_gate_that_is_not_up_yet(monkeypatch) -> None:
    """A gate failing while a sibling service is still starting is not a verdict.

    Boot proves only that the *entry URL* answers, and in a multi-service stack that is
    the fastest service. A gate asserting on the slower ones therefore fails on its first
    attempt against a stack that is coming up fine, and a single-shot gate would route a
    healthy run into repair.
    """
    attempts: list[str] = []

    def run_step(_step, _cwd, _to, _logger, *, label):
        attempts.append(label)
        return len(attempts) >= 3, "container is not running"

    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(stack, "_run_step", run_step)
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "yes", "entry_url": "u", "app_pid": "9", "app_pgid": "9"},
    )

    # The window is measured against the injected clock, which advances only by the
    # retry's own waits — so "how many attempts does a window buy" is a statement about
    # the window, not a race with the machine the suite runs on.
    out = stack.ensure_stack(
        {"entry_url": "u", "launch": "go", "health": ["make stack-health"]},
        logger=LOG, clock=FakeClock(),
    )
    assert out["ready"] == "yes"
    assert attempts == ["health[0]", "health[0]", "health[0]"]


def test_ensure_stack_stops_retrying_a_health_gate_at_the_documented_window(monkeypatch) -> None:
    """The retry is bounded: a gate that never passes fails the stack, it does not stall."""
    attempts: list[str] = []

    def run_step(_step, _cwd, _to, _logger, *, label):
        attempts.append(label)
        return False, "still down"

    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(stack, "_run_step", run_step)
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "yes", "entry_url": "u", "app_pid": "9", "app_pgid": "9"},
    )

    out = stack.ensure_stack(
        {"entry_url": "u", "launch": "go", "health_timeout": "12",
         "health": ["make stack-health", "make other-health"]},
        logger=LOG, clock=FakeClock(),
    )
    assert out["ready"] == "no"
    assert out["failed_step"] == "health[0]"
    assert out["error"] == "still down"
    assert out["app_pgid"] == "9"   # the booted handles survive, so teardown can act
    # A 12s window at 5s between attempts: t=0, 5, 10, and the one that finds it expired.
    assert attempts == ["health[0]"] * 4   # bounded, and the second gate never ran


def test_ensure_stack_reports_a_failed_launch(monkeypatch) -> None:
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "no", "entry_url": "u", "app_pid": "", "app_pgid": ""},
    )
    out = stack.ensure_stack({"entry_url": "u", "launch": "make up"}, logger=LOG)
    assert out["ready"] == "no"
    assert out["failed_step"] == "launch"
    # No reason from boot → the generic sentence, so `error` is never blank.
    assert "did not serve" in out["error"]


def test_ensure_stack_reports_boots_own_reason_not_a_launch_verdict(monkeypatch) -> None:
    """A wrong `identity` must not reach the repairer as "the launch command did not serve".

    The live failure: a QA manifest declared `identity: "127.0.0.1:8081"` for an emulator
    whose root serves the body `Ok`. The stack was up and answering 200 the whole time, but
    ensure_stack flattened every bring-up failure to one sentence blaming the launch recipe.
    Two resolve passes hand-verified the URL with `curl -sf -o /dev/null` (which throws the
    body away, so the marker mismatch is invisible), found it healthy, and escalated it to a
    human as a harness fault — burning the story's whole QA-rework budget on a one-line
    manifest typo the message had pointed away from.
    """
    marker_miss = ("http://localhost:8081/ answered HTTP 200, but its body does not contain "
                   "the manifest's identity marker '127.0.0.1:8081'")
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: marker_miss)
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "no", "entry_url": "u", "app_pid": "", "app_pgid": "",
                            "reason": marker_miss},
    )
    out = stack.ensure_stack(
        {"entry_url": "http://localhost:8081", "identity": "127.0.0.1:8081",
         "launch": "make up"},
        logger=LOG,
    )
    assert out["ready"] == "no"
    assert out["failed_step"] == "launch"
    assert out["error"] == marker_miss
    # The sentence that sent two repair passes to the wrong file must not be what crosses
    # the node boundary when boot knows better.
    assert "did not serve" not in out["error"]


def test_boot_reports_why_it_gave_up_rather_than_only_that_it_did(monkeypatch) -> None:
    """The deadline path carries the last probe's reason out, not just `boot_ok: no`."""
    class Serving:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Serving())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(stack, "_killpg", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        stack, "health_probe",
        lambda *_a, **_kw: "http://localhost:8081/ answered HTTP 200, but its body does not "
                           "contain the manifest's identity marker '127.0.0.1:8081'",
    )

    out = stack.boot_app(
        "make up", "http://localhost:8081", "/", ".", ".", "127.0.0.1:8081", 30.0,
        adopt=False, logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "no"
    assert "identity marker" in out["reason"]


def test_boot_reports_a_nonzero_exit_as_the_reason(monkeypatch) -> None:
    """Each way bring-up fails needs its own repair, so each states itself."""
    class Died:
        pid = 4242
        returncode = 2

        def poll(self) -> int:
            return 2

    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Died())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")

    out = stack.boot_app(
        "make up", "http://localhost:3000", "/", ".", ".", "", 60, logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "no"
    assert "exited with code 2" in out["reason"]


def test_teardown_stack_delegates_with_the_leave_up_policy(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_teardown(pgid, stop, cwd, *, logger, clock):
        seen.update(pgid=pgid, stop=stop, cwd=cwd)
        return {"torn_down": "skipped"}

    monkeypatch.setattr(stack, "teardown_app", fake_teardown)
    out = stack.teardown_stack({"app_pgid": ""}, {"stop": "", "app_cwd": "api"}, logger=LOG)
    assert out["torn_down"] == "skipped"
    assert seen == {"pgid": "", "stop": "", "cwd": "api"}


def test_run_step_accepts_string_and_mapping(monkeypatch) -> None:
    seen: list[tuple[list[str], str, float]] = []

    class Done:
        returncode = 0
        stderr = ""

    def fake_run(argv, *, cwd, capture_output, text, timeout):
        seen.append((argv, cwd, timeout))
        return Done()

    monkeypatch.setattr(stack.subprocess, "run", fake_run)

    ok, _ = stack._run_step("make seed", "root", 42, LOG, label="seed[0]")
    assert ok
    ok, _ = stack._run_step(
        {"run": "make seed-users", "working-directory": "api", "timeout": "7"},
        "root", 42, LOG, label="seed[1]",
    )
    assert ok
    assert seen == [
        ([stack._SHELL, "-c", "make seed"], "root", 42),
        ([stack._SHELL, "-c", "make seed-users"], "api", 7.0),
    ]


def test_run_step_reports_a_nonzero_exit(monkeypatch) -> None:
    class Failed:
        returncode = 1
        stdout = ""
        stderr = "seed blew up"

    monkeypatch.setattr(stack.subprocess, "run", lambda *_a, **_kw: Failed())
    ok, err = stack._run_step("make seed", "root", 42, LOG, label="seed[0]")
    assert not ok
    assert "seed blew up" in err
    assert "exit 1" in err  # the exit code is part of the brief, not only the stream


def test_run_step_briefs_from_stdout_when_stderr_is_silent(monkeypatch) -> None:
    """make and docker put real failures on stdout; an empty brief points at nothing.

    The observed shape: a coder-QA seed step failed with exit 2, its Makefile printed the
    error to stdout, and the setup fixer was briefed with a blank reason — so it had to
    re-run the step by hand to learn what the run already knew.
    """
    class Failed:
        returncode = 2
        stdout = "progress...\nError: emulator port 8081 is taken"
        stderr = "  \n"

    monkeypatch.setattr(stack.subprocess, "run", lambda *_a, **_kw: Failed())
    ok, err = stack._run_step("make seed", "root", 42, LOG, label="seed[0]")
    assert not ok
    assert "port 8081 is taken" in err


def test_step_error_keeps_the_tail_of_a_long_stream() -> None:
    """The error is the last thing a scrolling build prints — head-truncation cuts it."""
    noise = "progress line\n" * 200
    err = stack._step_error(2, None, noise + "FATAL: the actual reason")
    assert "FATAL: the actual reason" in err
    err = stack._step_error(2, "", "")
    assert "exit 2" in err  # never a blank brief, even with silent streams


def test_a_manifest_step_is_a_shell_recipe_not_an_argv_list() -> None:
    """Manifest commands run through a shell — really, not via a mock.

    Run as argv this exits 255: `ss` gets `|` and `||` as literal arguments. That is the
    live failure this pins — a coder-QA manifest whose launch guard was `ss -ltn | grep -q
    ':8081 ' || (nohup firebase emulators:start … &)` failed to boot a stack that was
    already serving, and the workflow escalated to a human over a correct recipe."""
    ok, err = stack._run_step(
        "echo ':8081 listening' | grep -q ':8081 ' || exit 3", ".", 30, LOG, label="probe",
    )
    assert ok, err

    # The other half of the guard: when it does *not* match, the right-hand side runs.
    ok, _ = stack._run_step("echo nothing | grep -q ':8081 ' || exit 3", ".", 30, LOG, label="p")
    assert not ok


def test_boot_launches_the_recipe_through_a_shell(monkeypatch) -> None:
    """`<probe> || <start>` is how the coder QA flow writes "start it unless it is already
    listening", and it only means that in a shell. Split as argv the probe takes `||` and
    the start command as its own operands and exits nonzero, which boot reads as the app
    dying during startup — so the run reports a failed launch for a recipe that is correct.
    That is what the live coder-QA run did, against a stack that was already serving."""
    recipe = "ss -ltn | grep -q ':8081 ' || (nohup firebase emulators:start & disown)"
    seen: list[list[str]] = []

    class Serving:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    def popen(argv, **_kwargs):
        seen.append(argv)
        return Serving()

    monkeypatch.setattr(stack.subprocess, "Popen", popen)
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")

    out = stack.boot_app(
        recipe, "http://127.0.0.1:18099", "/", ".", ".", "", 30.0,
        logger=LOG, clock=FakeClock(), adopt=False,
    )

    assert out["boot_ok"] == "yes"
    assert seen == [[stack._SHELL, "-c", recipe]]


if __name__ == "__main__":
    import subprocess
    import sys

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))


def test_boot_without_an_entry_url_never_probes_a_bare_path(monkeypatch) -> None:
    """A runbook proving readiness with a `health:` gate declares no `entry-url:`.

    Joining an empty base onto the default health path used to yield the bare string
    `"/"`, which urlopen rejects as an unknown url type — once per poll, for the whole
    boot window, before failing every such stack. There is nothing to probe here, so
    nothing may be probed.
    """
    class Exited:
        pid = 4242
        returncode = 0

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(
        stack, "health_probe",
        lambda *_a, **_kw: pytest.fail("probed a stack that declares no entry url"),
    )
    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Exited())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)

    out = stack.boot_app(
        "docker compose up -d --wait", "", "", ".", ".", "", 60,
        logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "yes"
    assert out["reason"] == ""
    # A command that has already exited leaves this run nothing to reap.
    assert out["app_pgid"] == ""


def test_boot_without_an_entry_url_owns_a_launch_that_keeps_running(monkeypatch) -> None:
    """A foreground daemon is the service itself: hand its pgid back for teardown."""
    class Serving:
        pid = 4242
        returncode = None

        def poll(self) -> None:
            return None

    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Serving())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 77)

    out = stack.boot_app(
        "npm run dev", "", "", ".", ".", "", 60, logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "yes"
    assert (out["app_pid"], out["app_pgid"]) == ("4242", "77")


def test_boot_without_an_entry_url_still_reports_a_launch_that_died(monkeypatch) -> None:
    """Absent probe or not, a nonzero exit is a failure and must be named as one."""
    class Died:
        pid = 4242
        returncode = 2

        def poll(self) -> int:
            return 2

    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Died())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)

    out = stack.boot_app(
        "docker compose up -d --wait", "", "", ".", ".", "", 60,
        logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "no"
    assert "code 2" in out["reason"]


# -- the ownership record ----------------------------------------------------------


def _record_file(app_cwd: str):
    return stack._record_path(app_cwd)


def test_ensure_stack_records_an_owned_foreground_server(monkeypatch, tmp_path) -> None:
    """A booted foreground server is recorded so a later *process* can still reap it."""
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "down")  # nothing serving
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "yes", "entry_url": "u",
                            "app_pid": "4242", "app_pgid": "77", "reason": ""},
    )
    monkeypatch.setattr(stack, "_proc_starttime", lambda _pid: "9999")
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "launch": "npm run dev",
         "app_cwd": str(tmp_path)},
        logger=LOG,
    )
    assert out["ready"] == "yes"
    raw = json.loads(_record_file(str(tmp_path)).read_text(encoding="utf-8"))
    assert raw == {"pid": "4242", "pgid": "77", "launch": "npm run dev",
                   "starttime": "9999"}


def test_ensure_stack_reaps_a_recorded_leaked_group_before_relaunching(
    monkeypatch, tmp_path,
) -> None:
    """A run killed before its teardown leaks its server; the NEXT bring-up reaps it.

    Without this, the relaunch fails on a port held by the previous run's own orphan.
    """
    monkeypatch.setattr(stack, "_proc_starttime", lambda _pid: "9999")
    stack._write_record(str(tmp_path), "4242", "77", "npm run dev")
    reaped: list[int] = []
    monkeypatch.setattr(stack, "_reap_pgid", lambda pgid, *, clock: reaped.append(pgid))
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "down")
    monkeypatch.setattr(
        stack, "boot_app",
        lambda *_a, **_kw: {"boot_ok": "yes", "entry_url": "u",
                            "app_pid": "5000", "app_pgid": "88", "reason": ""},
    )
    out = stack.ensure_stack(
        {"entry_url": "u", "identity": "acme", "launch": "npm run dev",
         "app_cwd": str(tmp_path)},
        logger=LOG,
    )
    assert out["ready"] == "yes"
    assert reaped == [77]
    # and the record now names the NEW owner, not the reaped one
    raw = json.loads(_record_file(str(tmp_path)).read_text(encoding="utf-8"))
    assert raw["pgid"] == "88"


def test_teardown_stack_falls_back_to_the_recorded_group(monkeypatch, tmp_path) -> None:
    """Handed no handles (a fresh process), teardown reaps the recorded owned group."""
    monkeypatch.setattr(stack, "_proc_starttime", lambda _pid: "9999")
    stack._write_record(str(tmp_path), "4242", "77", "npm run dev")
    reaped: list[int] = []
    monkeypatch.setattr(stack, "_reap_pgid", lambda pgid, *, clock: reaped.append(pgid))
    out = stack.teardown_stack({}, {"app_cwd": str(tmp_path)}, logger=LOG)
    assert out["torn_down"] == "yes"
    assert reaped == [77]
    assert not _record_file(str(tmp_path)).exists()  # the debt is settled


def test_stale_record_is_distrusted_and_cleared(monkeypatch, tmp_path) -> None:
    """A recycled pid (start time mismatch) must never be signalled; the record dies."""
    monkeypatch.setattr(stack, "_proc_starttime", lambda _pid: "9999")
    stack._write_record(str(tmp_path), "4242", "77", "npm run dev")
    monkeypatch.setattr(stack, "_proc_starttime", lambda _pid: "1111")  # pid recycled
    monkeypatch.setattr(
        stack, "_reap_pgid",
        lambda *_a, **_kw: pytest.fail("signalled a process group on a stale record"),
    )
    out = stack.teardown_stack({}, {"app_cwd": str(tmp_path)}, logger=LOG)
    assert out["torn_down"] == "skipped"  # no live record, no stop recipe: leave-up policy
    assert not _record_file(str(tmp_path)).exists()


# -- port diagnosis ----------------------------------------------------------------


def test_port_hint_names_the_holder(monkeypatch) -> None:
    class Done:
        returncode = 0
        stdout = 'LISTEN 0 511 *:4000 *:* users:(("node",pid=8123,fd=20))\n'

    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/ss")
    monkeypatch.setattr(stack.subprocess, "run", lambda *_a, **_kw: Done())
    hint = _REAL_PORT_HINT("http://localhost:4000/")
    assert "port 4000" in hint
    assert "node (pid 8123)" in hint


def test_port_hint_is_silent_when_nothing_listens(monkeypatch) -> None:
    class Done:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/ss")
    monkeypatch.setattr(stack.subprocess, "run", lambda *_a, **_kw: Done())
    assert _REAL_PORT_HINT("http://localhost:4000/") == ""
    # and a URL with no port has nothing to diagnose
    assert _REAL_PORT_HINT("http://example.com/") == ""


def test_port_hint_degrades_when_the_holder_is_unnamed(monkeypatch) -> None:
    """An unprivileged ss sees the listener but not its owner — still say the port is taken."""
    class Done:
        returncode = 0
        stdout = "LISTEN 0 511 *:4000 *:*\n"

    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/ss")
    monkeypatch.setattr(stack.subprocess, "run", lambda *_a, **_kw: Done())
    hint = _REAL_PORT_HINT("http://localhost:4000/")
    assert "port 4000" in hint
    assert "unidentified" in hint


def test_boot_failure_reason_carries_the_port_hint(monkeypatch) -> None:
    """A launch that dies during startup names who already holds its port."""
    class Died:
        pid = 4242
        returncode = 1

        def poll(self) -> int:
            return 1

    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "nothing is serving")
    monkeypatch.setattr(stack.subprocess, "Popen", lambda *_a, **_kw: Died())
    monkeypatch.setattr(stack.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(
        stack, "_port_hint",
        lambda url: " Note: port 3000 is already held by node (pid 8123) — a leftover "
                    "or unrelated process may own it; stop it, or change the stack's port.",
    )
    out = stack.boot_app(
        "npm run dev", "http://localhost:3000", "/", ".", ".", "", 60,
        logger=LOG, clock=FakeClock(),
    )
    assert out["boot_ok"] == "no"
    assert "exited with code 1" in out["reason"]
    assert "held by node (pid 8123)" in out["reason"]
