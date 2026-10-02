# The method skills

The skills in this folder are ways of working that hold in any repository. They hold
for any language, any domain and any toolchain. A repo receives them whole through a
pack, and none of them knows which repo loaded it.

## Keep them generic

- **State the rule, not the case.** A skill here carries a rule, a procedure or a test
  that holds whatever the project is. A finding from one project enters only as the
  general rule it taught, worded so that it holds in a repo that never saw the case.
- **Name nothing from a project.** No incident, file, path, command, tool or product
  from a project that used the skill. An example uses a neutral placeholder, and only
  when the rule cannot be read without one.
- **Send the specific rule to its owner.** A rule that holds for one stack, one tool or
  one repo goes in that stack's, tool's or repo's own skill. That skill may point at a
  method skill. A method skill points only at skills its own pack ships.

Before adding a lesson here, ask one question: would it change what an agent does in a
repo unrelated to the one that taught it? If the answer is no, the lesson belongs to that repo.
