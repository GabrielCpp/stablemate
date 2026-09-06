---
type: concept
slug: context-manifest-fields
title: Context manifest fields
---
# Context manifest fields

`Renderer.context_manifest` returns one object containing all eight fields. They are complementary
views of the selected repository context and installed assistant assets, rather than alternative
implementations of the same value. Read the field that corresponds to the value a consumer needs;
no field is preferred or deprecated. The method constructs `template`, `repo`, `vars`,
`instructions`, `instruction_tags`, `prompts`, `used_skills`, and `skill_dir` in the same returned
mapping.

- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- rule: select the field that supplies the required manifest value; all eight fields are current and complementary
