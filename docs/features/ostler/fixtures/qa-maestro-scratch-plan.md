---
type: fixture
slug: qa-maestro-scratch-plan
title: qa maestro scratch plan
---
# qa maestro scratch plan

Adds a third plan beside [the qa scratch repo](qa-scratch-repo.md)'s own, under
`art/specs/s1/`, so a run against the same scratch book can also target a `driver="maestro"`
target. The one scenario settles a screen on that target, which reads the device through
`maestro hierarchy` — a CLI this sandbox does not install, so the read raises before any state
it names is ever checked. The scenario's `claim` covers nothing, since the point is the device
read the driver buys, not a claim this plan proves about the demo book.

## Steps

### write-maestro-plan

- kind: seed
- run: printf -- 'from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id="qa-s1-device", story="s1")\n\ndevice = target("device", driver="maestro")\n\n\n@scenario(target=device, mechanism="live")\ndef device_settles(qa: Qa) -> None:\n    """A maestro target hands settle a device screen, read through the maestro CLI."""\n    with qa.claim(covers=[]):\n        qa.settle("home", busy=None, states={}, expect="shown")\n' > qa-scratch/art/specs/s1/qa_plan_device.py
