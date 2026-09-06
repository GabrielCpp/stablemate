---
type: format
slug: generated-context-manifest
title: Generated context manifest
---
# Generated context manifest

The JSON adapter farrier writes for the selected assistant backends. It records the resolved
template context and the repo-root-relative locations of selected skills and prompts so workflows
can resolve library references at run time. Farrier writes one per-enabled-assistant override and
also writes this generic path as an alias of the first enabled assistant; the generic file is
machine-independent because `repo.root` is pinned to `.`.

- file: `.agents/agents-context.json`
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- detail: [renderer](concepts/renderer.md#context_manifest-the-per-repo-run-time-manifest)

The per-assistant variants use `.agents/agents-context.<assistant>.json` and differ only in the
backend-specific paths held by `instructions`, `prompts`, and `skill_dir`. The object always
contains the fields below; maps and lists are empty when no matching selections exist.

## Fields

### template
- type: `map<string, any>`
- default: `{}`
- required: false
- semantics: merged `template:` and `vars:` values from `agents.yml`, with the top-level `template:` value winning on duplicate keys
- verify: unchanged(subject="the manifest template mapping", except_fields=[])
- semantics: exposed to run-time prompts as `template.<key>`
- verify: unchanged(subject="the manifest template mapping exposed to prompts", except_fields=[])
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### repo
- type: `map<string, any>`
- default: `{}`
- required: false
- semantics: repository context includes a derived `name` based on the repository directory
- verify: json_path(path="$.repo.name", matches="^[a-z0-9]+(?:-[a-z0-9]+)*$")
- semantics: repository context includes the configured installation `prefix`
- verify: json_path(path="$.repo.prefix", matches="^[a-z0-9]+(?:-[a-z0-9]+)*$")
- semantics: repository context preserves user-defined passthrough keys
- verify: unchanged(subject="user-defined repo context keys", except_fields=["name", "prefix", "root"])
- semantics: repository context sets `root` to the literal `.` rather than the install machine's absolute path
- verify: json_path(path="$.repo.root", equals=".")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### vars
- type: `map<string, any>`
- default: `{}`
- required: false
- semantics: the same merged mapping as `template`, exposed under the legacy `vars.<key>` prompt namespace
- verify: json_path(path="$.vars", matches="\\{.+\\}")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### instructions
- type: `map<string, string>`
- default: `{}`
- required: false
- semantics: every selected skill lookup alias mapped to its rendered, repo-root-relative skill file for the manifest's assistant backend
- verify: json_path(path="$.instructions", matches="skills/.+/SKILL\\.md")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_copilot_open_skills.py::test_context_manifest_copilot_uses_open_skills_paths`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### instruction_tags
- type: `map<string, list<string>>`
- default: `{}`
- required: false
- semantics: each tagged selected-skill alias is mapped to its normalized declared tags
- verify: json_path(path="$.instruction_tags", matches="^\\{'.+': \\['[a-z0-9][a-z0-9 _-]*'")
- semantics: untagged skills are omitted from `instruction_tags`
- verify: omits(subject="instruction_tags", matches="untagged skill aliases")
- semantics: aliases in `instruction_tags` match the keys in `instructions`
- verify: json_path(path="$.instruction_tags", matches="the aliases in instructions")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_skill_tags.py::test_context_manifest_publishes_tags_for_every_alias`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### prompts
- type: `map<string, string>`
- default: `{}`
- required: false
- semantics: every selected prompt lookup alias mapped to its rendered, repo-root-relative prompt file for the manifest's assistant backend
- verify: json_path(path="$.prompts", matches="(\\.github/prompts|\\.agents/prompts)/.+\\.prompt\\.md|\\.claude/commands/.+\\.md")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### used_skills
- type: `list<string>`
- default: `[]`
- required: false
- semantics: sorted skill lookup keys used by run-time `isUsingInstruction` checks
- verify: json_path(path="$.used_skills", matches="^\\[(?:'[^']+'(?:, )?)+\\]$")
- semantics: the list includes every alias exposed by the skill lookup, not only canonical source ids
- verify: json_path(path="$.used_skills", matches="^\\[(?:'[^']+'(?:, )?)+\\]$")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- detail: [context manifest fields](concepts/context-manifest-fields.md)

### skill_dir
- type: `string`
- default: `""`
- required: false
- semantics: repo-root-relative directory containing the manifest backend's installed skills, such as `.claude/skills`, `.agents/skills`, or `.github/skills`
- verify: json_path(path="$.skill_dir", matches="^\\.(claude|agents|github)/skills$")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_copilot_open_skills.py::test_context_manifest_copilot_uses_open_skills_paths`
- detail: [context manifest fields](concepts/context-manifest-fields.md)
