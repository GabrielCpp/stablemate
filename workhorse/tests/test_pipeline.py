"""Tests for `Workflow.pipeline`, the work-list drain (workhorse/pyflow/workflow.py)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse import worklist as wl  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import RunConfig  # noqa: E402
from workhorse.pyflow import DEFAULT_LAPS, Continue, Done, Workflow  # noqa: E402
from workhorse.pyflow.driver import drive, read_resume  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402
from workhorse.records import parse_checkpoint  # noqa: E402
from workhorse.runner.ladder import AgentRunner  # noqa: E402

Transition = Any


def _env(tmp: str, *, reopen: bool = False) -> RunEnv:
    run_dir = Path(tmp) / "runs" / "acme-t"
    writer = (
        ArtifactWriter.resume(run_dir)
        if reopen
        else ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    )
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


def _work(env: RunEnv) -> wl.WorkList:
    return wl.WorkList(wl.JsonBackend(env.run_dir / wl.WORK_FILE))


def _fill(env: RunEnv, n: int, kind: str = "epic") -> wl.WorkList:
    work = _work(env)
    work.add(
        wl.WorkItem(
            id=f"r{i}", kind=kind, order=i, payload={"name": f"r{i}"}, status="pending"
        )
        for i in range(n)
    )
    return work


def _statuses(work: wl.WorkList) -> dict[str, str]:
    return {it.id: it.status for it in work.items()}


def _resume(tmp: str, cls: type[Workflow]) -> Any:
    env = _env(tmp, reopen=True)
    text = (env.run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text()
    return drive(cls(), env, read_resume(parse_checkpoint(text)))


class Stop(RuntimeError):
    pass


def test_a_flow_target_drains_every_row_once_in_order_and_settles_after_each_handoff():
    seen: list[tuple[str, str, list[str]]] = []
    env_box: list[RunEnv] = []

    class Child(Workflow):
        name: str = ""

        def start(self) -> Transition:
            rows = {it.id: it.status for it in _work(env_box[0]).items()}
            seen.append(("child", self.name, [rows[k] for k in sorted(rows)]))
            return Done(self.name)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=Child, n=2) or Done("drained")

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env_box.append(env)
        work = _fill(env, 3)
        assert drive(Drain(), env) == "drained"
        assert [s[1] for s in seen] == ["r0", "r1", "r2"]
        assert seen[0][2] == ["active", "active", "pending"]
        assert seen[1][2] == ["done", "active", "pending"]
        assert seen[2][2] == ["done", "done", "active"]
        assert set(_statuses(work).values()) == {"done"}


def test_a_state_target_receives_the_rows_and_they_settle_only_on_re_entry():
    seen: list[list[str]] = []
    at_entry: list[dict[str, str]] = []

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            at_entry.append(_statuses(_work_of(self)))
            return self.pipeline("epic", to=self.work_on, n=2, tag="x") or Done("drained")

        def work_on(self, items: list[wl.WorkItem], tag: str = "") -> Transition:
            seen.append([it.id for it in items])
            assert tag == "x"
            return Continue(None, self.polish, items=items)

        def polish(self, items: list[wl.WorkItem]) -> Transition:
            return Continue(None, self.drain)

    def _work_of(flow: Workflow) -> wl.WorkList:
        return flow.work_list

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 3)
        assert drive(Drain(), env) == "drained"
        assert seen == [["r0", "r1"], ["r2"]]
        assert at_entry[0] == {"r0": "pending", "r1": "pending", "r2": "pending"}
        assert at_entry[1] == {"r0": "active", "r1": "active", "r2": "pending"}
        assert set(_statuses(work).values()) == {"done"}


def test_a_run_stopped_inside_a_state_target_finishes_with_nothing_dispatched_twice():
    dispatched: list[str] = []
    armed = [True]

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=self.work_on, n=1) or Done("drained")

        def work_on(self, items: list[wl.WorkItem]) -> Transition:
            dispatched.append(items[0].id)
            if items[0].id == "r1" and armed[0]:
                armed[0] = False
                raise Stop
            return Continue(None, self.drain)

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 3)
        try:
            drive(Drain(), env)
        except Stop:
            pass
        assert _statuses(work) == {"r0": "done", "r1": "active", "r2": "pending"}
        assert _resume(tmp, Drain) == "drained"
        assert dispatched == ["r0", "r1", "r1", "r2"]
        assert set(_statuses(work).values()) == {"done"}


def test_a_run_stopped_inside_a_flow_target_redispatches_that_row_and_its_child_resumes_in_place():
    starts: list[str] = []
    finishes: list[str] = []
    armed = [True]

    class Child(Workflow):
        name: str = ""

        def start(self) -> Transition:
            starts.append(self.name)
            return Continue(None, self.finish)

        def finish(self) -> Transition:
            finishes.append(self.name)
            if self.name == "r1" and armed[0]:
                armed[0] = False
                raise Stop
            return Done(self.name)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=Child, n=1) or Done("drained")

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 3)
        try:
            drive(Drain(), env)
        except Stop:
            pass
        assert _statuses(work) == {"r0": "done", "r1": "active", "r2": "pending"}
        assert _resume(tmp, Drain) == "drained"
        assert starts == ["r0", "r1", "r2"]
        assert finishes == ["r0", "r1", "r1", "r2"]
        assert set(_statuses(work).values()) == {"done"}


def test_the_lap_cap_blocks_a_row_that_keeps_coming_back():
    dispatched: list[str] = []

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=self.work_on, n=1) or Done("drained")

        def work_on(self, items: list[wl.WorkItem]) -> Transition:
            dispatched.append(items[0].id)
            self.work_list.settle([items[0].id], "pending")
            return Continue(None, self.drain)

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 1)
        assert drive(Drain(), env) == "drained"
        assert dispatched == ["r0"] * DEFAULT_LAPS
        row = work.items()[0]
        assert (row.status, row.laps) == ("blocked", DEFAULT_LAPS + 1)


def test_a_row_claimed_past_the_lap_cap_is_blocked_not_dispatched():
    dispatched: list[str] = []

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=self.work_on, n=2, laps=2) or Done("drained")

        def work_on(self, items: list[wl.WorkItem]) -> Transition:
            dispatched.extend(it.id for it in items)
            return Continue(None, self.drain)

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 2)
        rows = work.items()
        rows[0].laps = 2
        work.backend.save(rows)
        assert DEFAULT_LAPS == 3
        assert drive(Drain(), env) == "drained"
        assert dispatched == ["r1"]
        assert _statuses(work) == {"r0": "blocked", "r1": "done"}


def test_a_target_that_blocks_its_row_keeps_that_verdict():
    env_box: list[RunEnv] = []

    class Child(Workflow):
        name: str = ""

        def start(self) -> Transition:
            if self.name == "r1":
                _work(env_box[0]).mark("r1", "blocked")
            return Done(self.name)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=Child) or Done("drained")

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env_box.append(env)
        work = _fill(env, 3)
        assert drive(Drain(), env) == "drained"
        assert _statuses(work) == {"r0": "done", "r1": "blocked", "r2": "done"}


def test_a_state_target_that_blocks_its_row_keeps_that_verdict():
    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=self.work_on) or Done("drained")

        def work_on(self, items: list[wl.WorkItem]) -> Transition:
            if items[0].id == "r1":
                self.work_list.mark("r1", "blocked")
            return Continue(None, self.drain)

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 3)
        assert drive(Drain(), env) == "drained"
        assert _statuses(work) == {"r0": "done", "r1": "blocked", "r2": "done"}


def test_requeue_resets_status_laps_and_note_and_the_row_runs_again_with_its_note():
    notes: list[tuple[str, str]] = []

    class Child(Workflow):
        name: str = ""
        note: str = ""

        def start(self) -> Transition:
            notes.append((self.name, self.note))
            return Done(self.name)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=Child) or Done("drained")

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 2)
        assert drive(Drain(), env) == "drained"
        assert work.requeue(["r1", "missing"], "use the new tone", kind="epic") == 1
        row = {it.id: it for it in work.items()}["r1"]
        assert (row.status, row.laps, row.note) == ("", 0, "use the new tone")
        assert _work(env).requeue([], "x") == 0
        notes.clear()
        env2 = _env(tmp, reopen=True)
        assert drive(Drain(), env2) == "drained"
        assert notes == [("r1", "use the new tone")]
        assert set(_statuses(work).values()) == {"done"}


def test_a_note_never_changes_a_rows_digest():
    item = wl.WorkItem(id="a", kind="epic", payload={"x": 1})
    before = wl.payload_digest(item)
    item.note = "answer"
    assert wl.payload_digest(item) == before
    with tempfile.TemporaryDirectory() as tmp:
        work = wl.WorkList(wl.JsonBackend(Path(tmp) / "w.json"))
        work.add([item])
        work.requeue(["a"], "another answer")
        assert [it.note for it in work.items()] == ["another answer"]


def test_pipeline_only_claims_its_own_kind_and_returns_none_when_drained():
    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            return self.pipeline("epic", to=self.never) or Done("drained")

        def never(self, items: list[wl.WorkItem]) -> Transition:
            raise AssertionError("nothing of this kind is left")

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        work = _fill(env, 1, kind="story")
        assert drive(Drain(), env) == "drained"
        assert _statuses(work) == {"r0": "pending"}


def test_an_explicit_work_list_replaces_the_runs_own():
    seen: list[str] = []

    class Child(Workflow):
        name: str = ""

        def start(self) -> Transition:
            seen.append(self.name)
            return Done(None)

    with tempfile.TemporaryDirectory() as tmp:
        other = wl.WorkList(wl.JsonBackend(Path(tmp) / "other.json"))
        other.add([wl.WorkItem(id="o", kind="epic", payload={"name": "o"})])

        class Drain(Workflow):
            def start(self) -> Transition:
                return Continue(None, self.drain)

            def drain(self) -> Transition:
                return self.pipeline("epic", to=Child, work=other) or Done("drained")

        assert drive(Drain(), _env(tmp)) == "drained"
        assert seen == ["o"]


def _asks_subagents() -> Workflow:
    class Asks(Workflow):
        def start(self) -> Transition:
            return Done(self.subagents)

    return Asks()


def test_a_dry_run_has_no_subagents_unless_the_environment_sets_them():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env.dry_run = True
        assert drive(_asks_subagents(), env) is False


def test_a_dry_run_environment_can_grant_subagents():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env.dry_run = True
        env.subagents = True
        assert drive(_asks_subagents(), env) is True


def test_a_live_run_reads_subagents_from_its_backend():
    class Backend:
        supports_subagents = True

    class Runner:
        backend = Backend()

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env.agent_runner = cast(AgentRunner, Runner())
        assert drive(_asks_subagents(), env) is True


if __name__ == "__main__":
    fns = [
        v
        for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)


def _renders(prompt: str, **args: Any) -> Workflow:
    class Renders(Workflow):
        def start(self) -> Transition:
            return Done(self.render_prompt(prompt, args))

    return Renders()


def _has_delegate() -> Workflow:
    class Has(Workflow):
        def start(self) -> Transition:
            return Done(self.has_delegate("advisor"))

    return Has()


def test_a_dry_run_render_returns_the_placeholder():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env.dry_run = True
        assert drive(_renders("dev/brief.md", who="x"), env) == "(dry-run) dev/brief.md\n"


def test_a_render_returns_the_text_a_turn_would_send_and_writes_no_step():
    from _fakes import FakeBackend, FakeClock

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "brief.md").write_text("Hello {{ who }}.", encoding="utf-8")
        env = _env(tmp)
        env.agent_runner = AgentRunner(backend=FakeBackend(), clock=FakeClock())
        text = drive(_renders("brief.md", who="globex"), env)
        assert text.strip() == "Hello globex."
        assert not list(env.run_dir.rglob("prompt.md"))
        assert not list(env.run_dir.rglob("brief"))


def test_a_dry_run_has_a_delegate_only_when_the_environment_grants_subagents():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        env.dry_run = True
        assert drive(_has_delegate(), env) is False
        env.subagents = True
        assert drive(_has_delegate(), env) is True
