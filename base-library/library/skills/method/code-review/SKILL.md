---
name: code-review
description: "Review a code change against the rules the repository states: the code-structure triggers, every AGENTS.md and CLAUDE.md on the changed files' paths, and bugs. Ships a Stop hook that holds the implementing agent until a fresh reviewer passes its diff, and the same reviewer for a pull request. Load when reviewing a change or a pull request, before reporting work done, or when the review gate blocks a stop."
tags: [review, standards]
---

# Code review

The agent that wrote a change reads it as the plan it had in mind. It does not see two
implementations sharing one module, because it put them there on purpose. A reviewer
that did not write the change, and that reads the repository's rules first, does.

## What a review checks

A review reports three kinds of finding, and nothing else:

1. **A structure trigger fires.** The
   {{ skill_link("code-structure") }}
   skill opens with a table of triggers. Each links the reference that holds its fix and
   its counter-case. A trigger that fires with no counter-case is a finding, and its id
   is the row number, such as `2.1`.
2. **A written rule breaks.** Every AGENTS.md and CLAUDE.md from a changed file's
   directory up to the root binds that file. The id is `agents`, and the finding quotes
   the rule.
3. **A bug.** A wrong result, a crash, a lost write, or a broken invariant that a
   docstring or a test states. The id is `bug`.

The reviewer judges each touched module, class and function as it stands after the
change. A module that now holds two capabilities is a finding even when the second one
arrived in lines the diff did not touch. Two implementations of one capability that a
reader cannot tell apart in one glance are the common form.

[scripts/review_prompt.md](scripts/review_prompt.md) is the reviewer's full rubric.

## What is not a finding

- A problem in code the change leaves untouched.
- Anything a linter, a type checker or the test suite reports. Those gates run
  separately.
- A style preference that no rule states.
- A hypothetical problem with no line to point at.

## The Stop gate

[scripts/review_gate.py](scripts/review_gate.py) runs as a Claude Code Stop hook. When the
agent tries to stop with source changes, it asks a fresh `claude -p` reviewer to review
the diff. The reviewer gets read-only tools and no hooks. A finding blocks the stop, and
the agent reads the findings as its next instruction.

How it behaves:

- **Scope.** It reviews the working tree, staged or not, against the last approved
  tree. A stop with no source change passes without a review.
- **Memory.** A pass pins the approved tree in the git directory. A commit on top keeps
  the pin, so the next review covers only what changed since the approval.
- **Escalation.** The first two blocked rounds go to `sonnet`. Later rounds go to
  `opus`, which breaks a disagreement between the agent and the first reviewer.
- **Give up.** After ten blocked rounds the stop goes through with the open findings as
  a notice. The next stop starts again from round one.
- **Budget.** The diff is packed into batches of about 60,000 tokens, at most four. A
  larger change blocks with a `too-large` finding, because a reviewer cannot hold it.
- **Failure.** A reviewer that errors or times out blocks the stop, and the round does
  not count.

Configure it in `.agent-checks.toml` at the repository root. Every key is optional:

```toml
[code-review]
extensions = [".py"]
exclude = ["vendor/*", ".venv/*"]
rules = ["docs/architecture.md"]
```

- `extensions` replaces the default set of source file extensions.
- `exclude` lists glob patterns of paths the gate never reviews.
- `rules` lists more rule documents, relative to the root, for the reviewer to read
  beside the code-structure skill.

## Reviewing by hand or a pull request

`--base REV` runs the same reviewer against any revision and prints the verdict:

```bash
python3 .claude/skills/<prefix>-code-review/scripts/review_gate.py --base main
```

It exits 1 when it finds something. Its round count lives apart from the hook's, so a
manual review never spends the hook's rounds.

To review a pull request, check out its branch and run `--base` with its merge base.
Post the findings with `gh pr comment`. Link each one to the file at the full commit
sha with a line range, such as `blob/<sha>/path/to/file.py#L10-L15`. A branch name in
the link moves when the branch does.
