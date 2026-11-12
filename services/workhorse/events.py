"""What happens to the working directory outside the loop runner: a run that was started elsewhere."""

from __future__ import annotations

import json

from ostler.book import Outside, Sandbox

from .model.actions import FinishByHand, ParkByHand

STARTED = "2026-11-01T00:00:00+00:00"


def checkpoint(run_id: str, waiting_on: str | None, params: dict[str, int]) -> str:
    return json.dumps(
        {
            "engine": "pyflow",
            "workflow": "loop-runner",
            "run_id": run_id,
            "flow": "LoopRunner",
            "state": "start",
            "params": params,
            "waiting_on": waiting_on,
            "inputs": {"plan": "ship it"},
            "ctx": None,
            "seq": 3,
            "updated_at": STARTED,
        },
        indent=2,
        sort_keys=True,
    )


def started(run_id: str, **extra: str) -> str:
    return json.dumps({"workflow": "loop-runner", "run_id": run_id, "started_at": STARTED, **extra})


def message(ident: str, body: str, at: str, reply: str, replied_at: str) -> str:
    return json.dumps(
        {"id": ident, "body": body, "at": at, "reply": reply, "replied_at": replied_at}, separators=(",", ":")
    )


class ParkARun(Outside):
    does = "A run of the loop runner stops at a gate with two messages for its operator, one of them already answered."
    carries = ParkByHand

    def happen(self, sandbox: Sandbox) -> None:
        base = ".agents/runs/loop-runner-parked"
        sandbox.write(f"{base}/run.json", started("parked"))
        sandbox.write(f"{base}/checkpoint.json", checkpoint("parked", "gate", {"stale": 1}))
        sandbox.write(
            f"{base}/inbox.jsonl",
            message("m1", "Which branch should I use?", "2026-11-01T10:00:00+00:00", "", "")
            + "\n"
            + message("m2", "Is the plan approved?", "2026-11-01T11:00:00+00:00", "yes", "2026-11-01T12:00:00+00:00")
            + "\n",
        )


class FinishARun(Outside):
    does = "A run of the loop runner ends, so its run record says it is terminal."
    carries = FinishByHand

    def happen(self, sandbox: Sandbox) -> None:
        base = ".agents/runs/loop-runner-finished"
        sandbox.write(f"{base}/run.json", started("finished", terminal="terminal"))
        sandbox.write(f"{base}/checkpoint.json", checkpoint("finished", None, {}))
