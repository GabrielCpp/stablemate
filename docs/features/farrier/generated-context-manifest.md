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
- semantics: merged `template:` and `vars:` values from `agents.yml`, with the top-level `template:` value winning on duplicate keys; exposed to run-time prompts as `template.<key>`
- verify: json_path(path="$.template", absent=false)
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`

### repo
- type: `map<string, any>`
- default: `{}`
- required: false
- semantics: repository context including derived `name` and `prefix`, user-defined passthrough keys, and `root` set to the literal `.` rather than the install machine's absolute path
- verify: json_path(path="$.repo.root", equals=".")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`

### vars
- type: `map<string, any>`
- default: `{}`
- required: false
- semantics: the same merged mapping as `template`, exposed under the legacy `vars.<key>` prompt namespace
- verify: json_path(path="$.vars", absent=false)
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`

### instructions
- type: `map<string, string>`
- default: `{}`
- required: false
- semantics: every selected skill lookup alias mapped to its rendered, repo-root-relative skill file for the manifest's assistant backend
- verify: `json_path(path="$.instructions", matches="skills/.+/SKILL\\.md")`
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_copilot_open_skills.py::test_context_manifest_copilot_uses_open_skills_paths`

### instruction_tags
- type: `map<string, list<string>>`
- default: `{}`
- required: false
- semantics: each tagged selected-skill alias mapped to its normalized declared tags; untagged skills are omitted, and aliases match the keys in `instructions`
- verify: json_path(path="$.instruction_tags", absent=false)
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_skill_tags.py::test_context_manifest_publishes_tags_for_every_alias`

### prompts
- type: `map<string, string>`
- default: `{}`
- required: false
- semantics: every selected prompt lookup alias mapped to its rendered, repo-root-relative prompt file for the manifest's assistant backend
- verify: `json_path(path="$.prompts", matches="(\\.github/prompts|\\.agents/prompts)/.+\\.prompt\\.md|\\.claude/commands/.+\\.md")`
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`

### used_skills
- type: `list<string>`
- default: `[]`
- required: false
- semantics: sorted skill lookup keys used by run-time `isUsingInstruction` checks; the list includes every alias exposed by the skill lookup, not only canonical source ids
- verify: json_path(path="$.used_skills", absent=false)
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`

### skill_dir
- type: `string`
- default: `""`
- required: false
- semantics: repo-root-relative directory containing the manifest backend's installed skills, such as `.claude/skills`, `.agents/skills`, or `.github/skills`
- verify: json_path(path="$.skill_dir", matches="^\\.(claude|agents|github)/skills$")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_copilot_open_skills.py::test_context_manifest_copilot_uses_open_skills_paths`
