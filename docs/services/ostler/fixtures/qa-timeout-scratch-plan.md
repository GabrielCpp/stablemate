---
type: fixture
slug: qa-timeout-scratch-plan
title: qa timeout scratch plan
---
# qa timeout scratch plan

Adds a plan beside the one [the qa scratch repo](qa-scratch-repo.md) seeds under `art/specs/s1/`,
so a run against the same scratch book can also carry a scenario whose own `timeout=` elapses.
The scenario's body goes silent (no check, no fixture, no artifact — nothing that resets the
timeout) for longer than its declared timeout, so the runner kills it before it ever records a
check, and the `covers` stays empty, since the point is the kill and the session cleanup it
triggers, not a claim this plan proves about the demo book.

## Steps

### write-timeout-plan

- kind: seed
- run: printf -- 'import time\n\nfrom ostler_qa import Qa, plan, scenario, target\n\nplan(run_id="qa-s1-timeout", story="s1")\n\nslow = target("slow", driver="python")\n\n\n@scenario(target=slow, mechanism="live", timeout=0.2)\ndef scenario_times_out(qa: Qa) -> None:\n    """A scenario silent past its timeout is killed before it ever records a check."""\n    time.sleep(5)\n' > qa-scratch/art/specs/s1/qa_plan_timeout.py
