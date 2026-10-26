---
type: fixture
slug: qa-grpc-scratch-plan
title: qa grpc scratch plan
---
# qa grpc scratch plan

Adds a plan beside the one [the qa scratch repo](qa-scratch-repo.md) seeds under `art/specs/s1/`,
so a run against the same scratch book can also call `qa.grpc` from a scenario body. The target
declares no `base_url`, so the gRPC client has no address before the scenario's one call, and the
`covers` stays empty, since the point is the client's own refusal, not a claim this plan proves
about the demo book.

## Steps

### write-grpc-plan

- kind: seed
- run: printf -- 'from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id="qa-s1-grpc", story="s1")\n\nrpc = target("rpc", driver="python")\n\n\n@scenario(target=rpc, mechanism="live")\ndef grpc_needs_address(qa: Qa) -> None:\n    """A gRPC call on a target with no base_url is refused before it ever reaches a server."""\n    qa.grpc.call("Demo/Method", {})\n' > qa-scratch/art/specs/s1/qa_plan_grpc.py
