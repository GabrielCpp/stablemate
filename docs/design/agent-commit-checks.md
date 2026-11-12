# Agent commit checks

Status: settled by a grill with the operator, 2026-11-11. Not built.

## 1. Problem

A commit in this repository waits about seventeen seconds on its git hooks. A human pays
that wait on every commit, although only an agent's commit needs most of those checks.
The private-name sweep takes about eleven seconds. The skill-declared checks take about
four. `farrier --check` takes about two and a half, all of it rendering. The commit-message
format check takes less than a tenth of a second.

Done, for the operator: a human commit waits only on the commit-message format check. An
agent commit inside a harness session still runs every check, before git starts. A commit
that workhorse makes from Python runs none of the agent checks.

## 2. Settled tree

### Git hooks

1. The commit-message format check is the only check that stays a git hook. It runs at the
   `commit-msg` stage.
2. That check moves into the `commit-and-push` policy, as a script beside its text.

### Policies become folders

3. A policy is a folder, `library/policies/<group>/<name>/POLICY.md`, with an optional
   `scripts/` folder beside it. This matches the skill layout.
4. A policy carries front matter. The renderer strips it before the policy text reaches
   `AGENTS.md`.
5. Farrier installs a policy's scripts to `.agents/policies/<name>/scripts/`.
6. The policies README drops its rule that a policy bundles no assets.

### Agent-only checks

7. Every other check becomes an agent commit check:
   - the private-name sweep over the tree
   - the private-name check on the commit message
   - `farrier --check`
   - the clone check
   - the ostler staged-files check
8. The private-name check leaves stablemate. It becomes a new policy in the agent-library,
   and its script changes to fit the check contract below.
9. The message check scans the raw command string, plus the file that `-F` names.
10. When `farrier --check` finds drift, the check runs the install and stages the files
    farrier owns, so they land in the same commit. The agent never stops to ask what to
    do about drift.

### Declaring and listing checks

11. A skill or policy declares a check under a front-matter key `commit_checks:`. Each entry
    is `{run, budget}`. `budget` is the check's average run time in seconds. The `hooks:`
    key stays for git-hook stages only.
12. `farrier checks --repo <root>` prints one line per check: its command and its budget.

### The global guard

13. One global guard lives at `agent-library/library/hooks/<name>/hook.yml` and watches shell
    calls. Farrier renders it into every harness home, like the other home guards. No
    repository carries its own copy.
14. The guard rewrites the agent's command. It does not run the checks itself. A check
    that runs inside the hook could hit the hook timeout, and every harness lets the call
    through when its hook times out.
15. The guard inserts the checks right before each `git commit` in the command:
    `git add x && <checks> && git commit`.
16. For `git -C <dir> commit`, the guard runs the checks against that folder.
17. For `git commit -a` and `git commit --only -- <paths>`, the guard passes the paths to
    each check as arguments. A plain commit makes each check read the index.
18. The guard raises the call's timeout by the sum of the check budgets, capped at the
    harness's 600 second shell maximum.
19. A command with no `git commit`, or a repository where `farrier checks` lists nothing,
    passes through unchanged.

### Per harness

20. Claude Code: the guard returns `updatedInput` without a permission decision, so the
    user's permission rules still judge the rewritten command. The guard copies every
    input field back, because `updatedInput` replaces the whole input.
21. Codex: the guard can rewrite only by approving the call. It rewrites and approves only
    a command that already matches an approved commit pattern. Otherwise it denies the
    call and hands the agent the rewritten command to run. The timeout stays as the agent
    set it, because Codex documents no way to change it.
22. OpenCode: the plugin rewrites `args.command`. One bridge test sets the timeout. If
    OpenCode ignores it, the guard denies the call and tells the agent which timeout to
    use, as on Codex.

## 3. Book changes when built

The rules above land on these concepts in the same change as the code:

- `docs/services/farrier/concepts/hook-manager-wiring.md`: only `commit-msg` runs as a git
  hook. The pre-commit fence no longer calls `farrier --check`.
- `docs/services/farrier/concepts/skill-hook-declarations.md`: `commit_checks:` and its
  `{run, budget}` entries. The `farrier checks` listing.
- `docs/services/farrier/concepts/home-guard.md`: the rewrite guard and its per-harness
  behaviour.
- A new concept for the policy folder layout, its stripped front matter and its installed
  scripts.
