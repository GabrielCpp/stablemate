# scripts

Repo-level checks that no package ships. Each guard is a module with a `main()`, run by a
`make` target or a git hook from the repo root.

## Map

- `bench_ostler_doctor.py`: the reproducible timing baseline for `ostler doctor`, behind `make bench-doctor`.
- `check_file_length.py`: the ceiling on how long a Python file in the strict scope may grow.
- `check_fixtures.py`: the declared-fixture rule across the benchmark corpus.
- `check_no_giveup.py`: the rule that a workflow escalates instead of giving up.
- `check_no_shell.py`: the rule against ad-hoc shell scripts, and the `ALLOWED` set of files another program execs.
- `check_parsers.py`: the rule that code parses structured text instead of matching it.
- `check_portability.py`: the portability tiers each package is held to.
- `check_prompt_agnostic.py`: the rule that the coder workflow assumes nothing about where it is deployed.
- `check_public.py`: the public/private split: no private project name in the tree or its history.
- `claude_reviewer.py`: one read-only review turn on the claude CLI.
- `private_names.py`: where the private-name denylist is read from.
- `review_backlog.py`: walking a committed backlog too large to review at once, one reviewable commit range at a time.
- `review_diff.py`: cutting a diff into reviewer-sized batches.
- `review_gate.py`: the Stop hook that holds an agent until a fresh reviewer passes its diff.
- `review_git.py`: the git reads the review gate makes, none of which touch the live index.
- `review_outcome.py`: what the stop hook answers with.
- `review_run.py`: one review of a change: the batches its diff is cut into and the model that reads them.
- `review_state.py`: what the review gate remembers between stops.
- `review_verdict.py`: the reviewer's verdict and how the gate reads it.
- `strict_scope.py`: which paths the strict gate covers, from `[tool.stablemate.strict]`.
- `sync_pins.py`: widening a pin on a workspace member once that member's new version falls outside it, and committing it under the holder's scope.
- `vendor_core.py`: copying `core/stablemate_core` into each tool, and checking the copies.
