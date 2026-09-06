---
type: concept
slug: skill-hook-declarations
title: Skill hook declarations
---
# Skill hook declarations

Selected skills may declare scripts that Farrier runs at supported git-hook stages. The declaration
is data in the skill front matter; merely shipping a script under `scripts/` does not install it as
a hook. The hook-manager wiring consumes the valid declarations and renders one adapter path for
each selected hook.

- code: `farrier/farrier/skill_hooks.py`
- detail: [hook manager wiring](hook-manager-wiring.md)

## Fields

### STAGES
- type: `tuple[str, ...]`
- default: `pre-commit`
- required: true
- semantics: the complete set of hook stages Farrier can wire
- verify: count(subject="wireable hook stages", equals=1)
- code: `farrier/farrier/skill_hooks.py::STAGES`

### SkillHook.skill
- type: `str`
- default: none; supplied when the record is constructed
- required: true
- semantics: the installed skill name whose declaration owns the hook
- verify: count(subject="skill hook owner field", equals=1)
- code: `farrier/farrier/skill_hooks.py::SkillHook`

### SkillHook.stage
- type: `str`
- default: none; supplied when the record is constructed
- required: true
- semantics: the supported git-hook stage at which the script runs
- verify: count(subject="skill hook stage field", equals=1)
- code: `farrier/farrier/skill_hooks.py::SkillHook`

### SkillHook.run
- type: `str`
- default: none; supplied when the record is constructed
- required: true
- semantics: a path relative to the declaring skill directory for the script to execute
- verify: count(subject="skill hook script path field", equals=1)
- code: `farrier/farrier/skill_hooks.py::SkillHook`

## Methods

### declared
- sig: `declared(data: dict[str, Any]) -> list[dict[str, Any]]`
- does: returns an empty list when `hooks` is absent or is not a list
- does: keeps only mapping entries from a list-valued `hooks` block
- returns: raw mapping declarations without validating their stage or script path
- verify: count(subject="mapping-only hook declaration filtering", equals=1)
- code: `farrier/farrier/skill_hooks.py::declared`

### hooks_for
- sig: `hooks_for(skill: str, data: dict[str, Any]) -> list[SkillHook]`
- does: trims each declaration's stage and run values
- does: keeps only declarations whose stage is in `STAGES`
- does: keeps only declarations whose normalized run path is non-empty
- returns: immutable `SkillHook` records
- returns: each record retains the supplied skill name
- returns: each record contains the normalized stage
- returns: each record contains the normalized run path
- verify: count(subject="valid skill hooks selected for wiring", equals=1)
- code: `farrier/farrier/skill_hooks.py::hooks_for`

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
- returns: `(level, code, message)` findings
- returns: one finding for each invalid declaration condition
- verify: count(subject="skill hook declaration validation findings", equals=1)
- code: `farrier/farrier/skill_hooks.py::findings`
