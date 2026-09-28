# kit

The helpers any workflow family's nodes reuse. A helper that only one family needs belongs in that family.

## Map

- `credentials.py`: the one place a workflow reads the environment, and only for secrets.
- `git.py`: every git operation a node needs, so no node shells out to git.
- `github.py`: GitHub access through PyGithub: the repo, its open PR, and token-authenticated push and fetch.
- `inbox.py`: the run-scoped operator inbox a workflow polls from its loop heads.
- `jsonio.py`: reading strict JSON and the relaxed JSONC dialect VSCode writes.
- `paths.py`: the repo root and the docs root, taken from the run's inputs rather than the environment.
- `qa/`: the family-neutral QA domain: bringing a stack up, running a plan and checking its evidence.
- `telemetry.py`: how a bounded retry loop reports its counters and verdicts as span labels.
- `tools.py`: the one seam a node runs an external CLI through.
- `workspace.py`: which repos a run spans, where they live, and their checkout. It also builds the dispatch list from a plan's services.
