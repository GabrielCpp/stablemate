---
type: concept
slug: skill-hook-record-fields
title: Skill hook record fields
---
# Skill hook record fields

`SkillHook` is one immutable hook declaration, not three competing implementations. Its
constructor receives `skill`, `stage`, and `run` together, and `hooks_for` creates every record
with all three values after it has normalized the declared stage and script path.

There is no ranking between these fields. Read `skill` to identify the installed skill that owns
the declaration, `stage` to learn when Farrier wires its script, and `run` to locate that script
relative to the skill directory. A valid hook record needs every field; callers constructing or
consuming a record use the complete tuple rather than selecting one field as an alternative.

- code: `farrier/farrier/skill_hooks.py::SkillHook`
- rule: treat `skill`, `stage`, and `run` as complementary required attributes of one hook record; none replaces or ranks above another
