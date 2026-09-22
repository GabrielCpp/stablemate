"""Tests for `Workflow.pipeline`, the chunked worklist drain (workhorse/pyflow/workflow.py)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse import worklist as wl  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import RunConfig  # noqa: E402
from workhorse.pyflow import Await, Continue, Done, Workflow  # noqa: E402
from workhorse.pyflow.driver import drive  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402

Transition = Any


class MemoryBackend:
    """A worklist held in memory, so a drain needs no disk."""

    def __init__(self, items: list[wl.WorkItem]) -> None:
        self.items = items

    def load(self) -> list[wl.WorkItem]:
        return [it.model_copy(deep=True) for it in self.items]

    def save(self, items: Any) -> None:
        self.items = [it.model_copy(deep=True) for it in items]


def _work(n: int, kind: str = "finding") -> wl.WorkList:
    return wl.WorkList(
        backend=MemoryBackend(
            [wl.WorkItem(id=f"f{i}", status="pending", kind=kind) for i in range(n)]
        )
    )


def _env(tmp: str) -> RunEnv:
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


def _drive(cls: type[Workflow]) -> Any:
    with tempfile.TemporaryDirectory() as tmp:
        return drive(cls(), _env(tmp))


def test_a_seven_row_queue_drains_in_three_chunks_of_three():
    chunks: list[list[str]] = []
    work = _work(7)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain, rnd=1)

        def drain(self, rnd: int = 0) -> Transition:
            again = self.pipeline(
                work, "finding", 3, lambda items: chunks.append([it.id for it in items])
            )
            if again:
                return again
            return Done(rnd)

    assert _drive(Drain) == 1
    assert chunks == [["f0", "f1", "f2"], ["f3", "f4", "f5"], ["f6"]]
    assert {it.status for it in work.items()} == {"done"}


def test_every_chunk_runs_under_a_checkpoint_a_resume_can_land_on():
    marks: list[dict[str, Any]] = []
    work = _work(7)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain, rnd=1)

        def drain(self, rnd: int = 0) -> Transition:
            again = self.pipeline(
                work,
                "finding",
                3,
                lambda items: marks.append(
                    json.loads(
                        (self.run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text()
                    )
                ),
            )
            if again:
                return again
            return Done(rnd)

    _drive(Drain)
    assert [(m["state"], m["params"]) for m in marks] == [("drain", {"rnd": 1})] * 3


def test_the_loop_carries_the_states_own_params_without_the_author_naming_them():
    seen: list[int] = []
    work = _work(4)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain, rnd=7, stall=2)

        def drain(self, rnd: int = 0, stall: int = 0) -> Transition:
            seen.append(rnd * 10 + stall)
            again = self.pipeline(work, "finding", 2, lambda items: None)
            if again:
                return again
            return Done(seen)

    assert _drive(Drain) == [72, 72, 72]


def test_a_handler_returning_an_await_short_circuits_the_drain():
    work = _work(6)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            again = self.pipeline(
                work,
                "finding",
                2,
                lambda items: Await.on_machine("gate.md", "wait?", self.after),
            )
            assert isinstance(again, Await)
            return Done(f"gated:{again.state}")

        def after(self) -> Transition:
            return Done("gated")

    assert _drive(Drain) == "gated:after"
    assert [it.status for it in work.items()] == ["active", "active"] + ["pending"] * 4


def test_a_row_the_handler_blocked_keeps_that_verdict():
    work = _work(3)

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            again = self.pipeline(
                work, "finding", 3, lambda items: work.mark(items[0].id, "blocked")
            )
            if again:
                return again
            return Done("drained")

    assert _drive(Drain) == "drained"
    got = {it.id: it.status for it in work.items()}
    assert got == {"f0": "blocked", "f1": "done", "f2": "done"}


def test_a_handler_that_raises_leaves_its_rows_claimable():
    work = _work(2)

    def boom(items: list[wl.WorkItem]) -> None:
        raise RuntimeError("handler fell over")

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            try:
                self.pipeline(work, "finding", 2, boom)
            except RuntimeError as exc:
                return Done(str(exc))
            return Done("drained")

    assert _drive(Drain) == "handler fell over"
    assert [it.status for it in work.items()] == ["active", "active"]
    assert [it.id for it in work.claim(2)] == ["f0", "f1"]


def test_a_drained_queue_returns_none():
    work = _work(0)
    calls: list[int] = []

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            again = self.pipeline(work, "finding", 3, lambda items: calls.append(1))
            if again:
                return again
            return Done("drained")

    assert _drive(Drain) == "drained"
    assert calls == []


def test_pipeline_only_claims_its_own_kind():
    work = wl.WorkList(
        backend=MemoryBackend(
            [
                wl.WorkItem(id="a", status="pending", kind="finding"),
                wl.WorkItem(id="b", status="pending", kind="audit"),
            ]
        )
    )

    class Drain(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.drain)

        def drain(self) -> Transition:
            again = self.pipeline(work, "finding", 5, lambda items: None)
            if again:
                return again
            return Done("drained")

    assert _drive(Drain) == "drained"
    assert {it.id: it.status for it in work.items()} == {"a": "done", "b": "pending"}


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
