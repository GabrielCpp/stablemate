---
type: concept
slug: skill-hook-declarations
title: Skill hook declarations
---
# Skill hook declarations

Selected skills and policies may declare scripts that Farrier runs at supported git-hook stages.
The declaration is data in the front matter of `SKILL.md` or `POLICY.md`. Shipping a script under
`scripts/` does not install it as a hook. The hook-manager wiring consumes the valid declarations
and renders one runner per stage.

The same front matter may declare `commit_checks`, the scripts an agent's commit runs before it
lands. Each entry names a `run` path and a `budget` in seconds. The
[agent commit checks](agent-commit-checks.md) guard runs them.

- code: `farrier/farrier/skill_hooks.py` @723fc6fd14e0
- rule: a hook belongs to a git stage only when it is fast and must hold for every committer, and any other check is a `commit_checks` entry
- rule: a policy's hooks run from `.agents/policies/<name>/` and a skill's from the first of `.claude/skills`, `.agents/skills` and `.github/skills` that holds it
- detail: [hook manager wiring](hook-manager-wiring.md)

## Fields

### STAGES
- type: `tuple[str, ...]`
- default: `pre-commit`, `commit-msg`
- required: true
- semantics: the complete set of hook stages Farrier can wire
- verify: count(subject="wireable hook stages", equals=2)
- code: `farrier/farrier/skill_hooks.py::STAGES` @723fc6fd14e0

### SkillHook.skill
- type: `str`
- default: none
- verify: count(subject="skill hook owner field has no default", equals=1)
- default: supplied when the record is constructed
- verify: count(subject="skill hook owner field supplied at construction", equals=1)
- required: true
- semantics: the installed skill name whose declaration owns the hook
- verify: count(subject="skill hook owner field", equals=1)
- code: `farrier/farrier/skill_hooks.py::SkillHook` @28b31dc51ede
- detail: [skill hook record fields](skill-hook-record-fields.md)

### SkillHook.stage
- type: `str`
- default: none
- verify: count(subject="skill hook stage field has no default", equals=1)
- default: supplied when the record is constructed
- verify: count(subject="skill hook stage field supplied at construction", equals=1)
- required: true
- semantics: the supported git-hook stage at which the script runs
- verify: count(subject="skill hook stage field", equals=1)
- code: `farrier/farrier/skill_hooks.py::SkillHook` @28b31dc51ede
- detail: [skill hook record fields](skill-hook-record-fields.md)

### SkillHook.run
- type: `str`
- default: none
- verify: count(subject="skill hook script path field has no default", equals=1)
- default: supplied when the record is constructed
- verify: count(subject="skill hook script path field supplied at construction", equals=1)
- required: true
- semantics: a path relative to the declaring skill directory for the script to execute
- verify: count(subject="skill hook script path field", equals=1)
- code: `farrier/farrier/skill_hooks.py::SkillHook` @28b31dc51ede
- detail: [skill hook record fields](skill-hook-record-fields.md)

### SkillHook.roots
- type: `tuple[str, ...]`
- default: `.claude/skills`, `.agents/skills`, `.github/skills`
- required: false
- semantics: the folders the runner searches, in order, for the owner's installed copy of the script
- verify: count(subject="skill hook search roots", equals=3)
- code: `farrier/farrier/skill_hooks.py::SkillHook` @28b31dc51ede

### CommitCheck.owner
- type: `str`
- default: none
- required: true
- semantics: the skill or policy whose front matter declares the check
- verify: count(subject="commit check owner field", equals=1)
- code: `farrier/farrier/skill_hooks.py::CommitCheck` @d770fa01e3f6

### CommitCheck.run
- type: `str`
- default: none
- required: true
- semantics: the script's path relative to the owner's folder
- verify: count(subject="commit check script path field", equals=1)
- code: `farrier/farrier/skill_hooks.py::CommitCheck` @d770fa01e3f6

### CommitCheck.budget
- type: `float`
- default: none
- required: true
- semantics: the seconds the check takes in the average case, which the guard adds to the commit's timeout
- verify: count(subject="commit check budget field", equals=1)
- code: `farrier/farrier/skill_hooks.py::CommitCheck` @d770fa01e3f6

## Methods

### declared
- sig: `declared(data: dict[str, Any]) -> list[dict[str, Any]]`
- does: returns an empty list when `hooks` is absent or is not a list
- does: keeps only mapping entries from a list-valued `hooks` block
- returns: raw mapping declarations without validating their stage or script path
- verify: count(subject="mapping-only hook declaration filtering", equals=1)
- code: `farrier/farrier/skill_hooks.py::declared` @ce2b1090632f

### hooks_for
- sig: `hooks_for(skill: str, data: dict[str, Any], roots: tuple[str, ...] = SKILL_ROOTS) -> list[SkillHook]`
- does: trims each declaration's stage and run values
- does: gives each record the `roots` it was called with, which a policy sets to `.agents/policies`
- does: keeps only declarations whose stage is in `STAGES`
- does: keeps only declarations whose normalized run path is non-empty
- returns: immutable `SkillHook` records
- returns: each record retains the supplied skill name
- returns: each record contains the normalized stage
- returns: each record contains the normalized run path
- verify: count(subject="valid skill hooks selected for wiring", equals=1)
- code: `farrier/farrier/skill_hooks.py::hooks_for` @ab63dceb271a

### checks_for
- sig: `checks_for(owner: str, data: dict[str, Any]) -> list[CommitCheck]`
- does: returns an empty list when `commit_checks` is absent or is not a list
- does: keeps only mapping entries with a non-empty `run` and a positive numeric `budget`
- returns: one `CommitCheck` per kept entry, in declaration order
- verify: count(subject="valid commit checks", equals=1)
- code: `farrier/farrier/skill_hooks.py::checks_for` @6493910441e7
- tests: `farrier/tests/test_commit_checks.py::test_checks_for_keeps_entries_with_a_run_and_a_positive_budget`

### check_findings
- sig: `check_findings(data: dict[str, Any], source_dir: Path) -> list[tuple[str, str, str]]`
- does: returns no findings when `commit_checks` is absent
- does: reports `commit-checks-not-a-list` when the block is not a list
- does: reports `commit-check-not-a-mapping` for an entry that is not a mapping
- does: reports `commit-check-no-run` for an entry with no `run`
- does: reports `commit-check-bad-budget` for a budget that is missing, not a number or not positive
- does: reports `hook-run-escapes` for an absolute or parent-traversing run path
- does: reports `hook-run-missing` for a run path that names no file in `source_dir`
- returns: `(level, code, message)` findings
- verify: count(subject="commit check validation findings", equals=1)
- code: `farrier/farrier/skill_hooks.py::check_findings` @378e93f8b7c3
- tests: `farrier/tests/test_commit_checks.py::test_check_findings_name_every_broken_entry`
- tests: `farrier/tests/test_commit_checks.py::test_findings_cover_commit_checks_beside_hooks`

### findings
- sig: `findings(data: dict[str, Any], source_dir: Path) -> list[tuple[str, str, str]]`
- does: returns no findings when `hooks` is absent
- does: reports a malformed hook block
- does: reports a hook entry that is not a mapping
- does: reports a missing stage
- does: reports an unsupported stage
- does: reports a missing run path
- does: reports an absolute run path as an error
- does: reports a parent-traversing run path as an error
- does: reports a run path that does not name a file in `source_dir` as an error
- does: appends the `check_findings` of the same front matter
- returns: `(level, code, message)` findings
- returns: one finding for each invalid declaration condition
- verify: count(subject="skill hook declaration validation findings", equals=1)
- code: `farrier/farrier/skill_hooks.py::findings` @603f72cb7721
