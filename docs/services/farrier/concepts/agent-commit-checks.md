---
type: concept
slug: agent-commit-checks
title: Agent commit checks
---
# Agent commit checks

An agent commit check runs when an agent commits from its session, and never when a person
commits. A person's commit runs only the fast git hooks the [hook manager wiring](hook-manager-wiring.md)
installs. The slow checks, such as the drift check and a sweep for private names, move to the agent,
because the agent is the committer that leaks and the person should not wait for them.

A `commit-checks` [home guard](home-guard.md) in the user's agent library watches the shell tool.
When a command holds a `git commit`, the guard asks `farrier checks --repo <root>` for the checks
of the repository the commit lands in. It then rewrites the command so the checks run first and
the commit runs only when every check passes. It also raises the call's timeout by the sum of the
checks' budgets.

A skill or a policy declares its checks in its front matter, beside its `hooks:`:

```yaml
commit_checks:
  - run: scripts/check_private_names.py
    budget: 2
```

`run` is the script's path inside the skill or policy folder. `budget` is the seconds the check
takes in the average case. The first check of every repository with an `agents.yml` is
`farrier sync`, which reinstalls drifted generated files and stages them with the commit.

- code: `farrier/farrier/outputs.py::commit_checks` @4cdcc3e17a62
- code: `farrier/farrier/skill_hooks.py::checks_for` @6493910441e7
- code: `farrier/farrier/sync.py::sync` @e18ce8b0bcac
- rule: a commit check runs from the repository root, reads the index, takes the commit's paths as arguments when the commit names any, passes with exit 0 and explains a failure on stderr
- rule: a check reads the commit command from `AGENT_COMMIT_COMMAND` and the directory the agent ran it from from `AGENT_COMMIT_CWD`, so a check can read the commit message
- rule: the rewrite stages what the commit would stage before the checks run, with `git add -u` for `-a` and `git add -A --` for named paths, so each check reads the index the commit will record
- rule: the rewritten command marks itself, so the guard passes a command it already rewrote
- rule: a commit the guard cannot place in one repository, such as one behind `||` or `cd -`, runs as written
- rule: a repository whose checks farrier cannot list commits as written, because a broken setting must not block every commit on the machine
- rule: Claude and OpenCode receive the rewritten command and a timeout raised by the sum of the budgets, capped at 600000 milliseconds
- rule: Codex cannot change a timeout, so it receives the rewrite with an allow when the command holds only `cd`, `git add` and `git commit`, and a deny carrying the rewrite for any other command
- rule: `farrier sync` stages what it regenerated when the commit names no paths, and refuses with the list of paths otherwise, because staging them would widen a commit the agent limited
- rule: a policy with scripts installs under `.agents/policies/<name>/`, so its checks and hooks run from the installed copy
- rule: `farrier checks` lists the user library's skills the repository neither selects nor excludes, so a check follows the machine and a repository opts out under `exclude: skills`
- tests: `farrier/tests/test_commit_checks.py`
- tests: `farrier/tests/test_sync.py`
