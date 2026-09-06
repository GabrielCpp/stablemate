---
type: concept
slug: frontmatter-parsing
title: Front-matter parsing
---
# Front-matter parsing

`farrier.frontmatter` is the parser boundary for library documents, generated-file provenance,
and `agents.yml` mappings. It parses markdown front matter with a markdown parser and YAML, then
returns deliberately lenient empty values for absent or malformed front matter. It does not resolve
library sources or write files. The public `LOCAL_INSTRUCTION_FILES` tuple names the generated
instruction files (`AGENTS.md` and `CLAUDE.md`) that source lookup recognizes.

- code: `farrier/farrier/frontmatter.py::frontmatter_mapping`

## Fields

### LOCAL_INSTRUCTION_FILES
- type: `tuple[str, str]`
- default: `("AGENTS.md", "CLAUDE.md")`
- required: true
- semantics: the generated instruction filenames accepted by source lookup
- verify: count(subject="local instruction filenames", equals=2)
- code: `farrier/farrier/frontmatter.py::LOCAL_INSTRUCTION_FILES`

## Methods

### frontmatter_mapping
- sig: `frontmatter_mapping(text: str) -> dict[str, Any]`
- does: parse the first markdown front-matter block as a YAML mapping
- verify: json_path(path="$.name", equals="n")
- returns: the complete mapping, or an empty mapping when there is no block, malformed YAML, or a non-mapping YAML value
- verify: json_path(path="$.metadata", absent=true)
- code: `farrier/farrier/frontmatter.py::frontmatter_mapping`
- tests: `farrier/tests/test_frontmatter_parsing.py::test_tags_and_metadata_read_the_same_block_as_split`

### read_yaml
- sig: `read_yaml(path: Path) -> dict[str, Any]`
- does: read UTF-8 YAML from the named filesystem path
- verify: exit_status(code=0)
- raises: `SystemExit("Missing config: <path>")` when the path does not exist
- verify: exit_status(code=1)
- raises: `SystemExit("Config must be a YAML mapping: <path>")` when the parsed value is not a mapping
- verify: exit_status(code=1)
- returns: the parsed YAML mapping, using an empty mapping for an empty file
- verify: json_path(path="$.agents", absent=true)
- code: `farrier/farrier/frontmatter.py::read_yaml`

### banner_sources
- sig: `banner_sources(text: str) -> list[str]`
- does: inspect only the first parsed HTML block for a farrier generated-file banner
- verify: count(subject="HTML blocks inspected for generated provenance", equals=1)
- returns: indented `library/` source paths from the banner in listed order
- verify: count(subject="source paths parsed from the generated banner", equals=2)
- returns: an empty list when the first block is not a farrier banner
- verify: count(subject="source paths parsed from the generated banner", equals=2)
- code: `farrier/farrier/frontmatter.py::banner_sources`
- tests: `farrier/tests/test_frontmatter_parsing.py::test_banner_sources_stop_at_the_end_of_the_banner`

### mapping_skill_names
- sig: `mapping_skill_names(mapping: dict[str, Any]) -> list[str]`
- does: choose the `skills` list from a localInstructions mapping when present
- verify: count(subject="skills selected by a localInstructions mapping", equals=1)
- does: otherwise choose the single `skill` value
- verify: count(subject="skills selected by a localInstructions mapping", equals=1)
- returns: stringified selected skill names, or an empty list when neither key selects a skill
- verify: count(subject="skills selected by a localInstructions mapping", equals=1)
- code: `farrier/farrier/frontmatter.py::mapping_skill_names`
- tests: `farrier/tests/test_local_instruction_mapping.py::test_claude_only_repo_still_writes_agents_md_plus_a_pointer`

### mapping_policy_names
- sig: `mapping_policy_names(mapping: dict[str, Any]) -> list[str]`
- does: choose the `policies` list before the single `policy` value
- verify: count(subject="policies selected by a localInstructions mapping", equals=2)
- returns: stringified selected policy names, or an empty list when neither key selects a policy
- verify: count(subject="policies selected by a localInstructions mapping", equals=2)
- code: `farrier/farrier/frontmatter.py::mapping_policy_names`
- tests: `farrier/tests/test_policies.py::test_mapping_policy_names_reads_both_spellings`

### mapping_prompt_names
- sig: `mapping_prompt_names(mapping: dict[str, Any]) -> list[str]`
- does: choose the `prompts` list before the single `prompt` value
- verify: count(subject="prompts selected by a localInstructions mapping", equals=1)
- returns: stringified selected prompt names, or an empty list when neither key selects a prompt
- verify: count(subject="prompts selected by a localInstructions mapping", equals=1)
- code: `farrier/farrier/frontmatter.py::mapping_prompt_names`
- tests: `farrier/tests/test_local_instruction_mapping.py::test_prompt_only_mapping_needs_no_skill`

### mapping_include_readme
- sig: `mapping_include_readme(mapping: dict[str, Any]) -> bool`
- does: use `includeReadme` when it is a boolean
- verify: json_path(path="$.includeReadme", equals=false)
- raises: `SystemExit` for an unsupported compatibility value
- verify: exit_status(code=1)
- verify: json_path(path="$.includeReadme", equals=false)
- returns: true when `includeReadme` is absent
- verify: json_path(path="$.includeReadme", equals=true)
- returns: the compatibility values `inline` and `import` as true
- verify: json_path(path="$.includeReadme", equals=true)
- returns: the compatibility value `none` as false
- verify: json_path(path="$.includeReadme", equals=false)
- code: `farrier/farrier/frontmatter.py::mapping_include_readme`
- tests: `farrier/tests/test_local_instruction_mapping.py::test_legacy_include_readme_spellings_still_map_onto_the_boolean`

### split_front_matter
- sig: `split_front_matter(content: str) -> tuple[dict[str, str], str]`
- does: parse front matter into a flat string map while keeping nested YAML values under their parent key
- verify: json_path(path="$.metadata.source", equals="library/skills/acme/a/SKILL.md")
- does: convert scalar, list, and mapping values to renderer-ready strings
- verify: json_path(path="$.allowed-tools", equals="[Bash, Read]")
- returns: the parsed flat header and the body after the fence and exactly one separator line
- verify: json_path(path="$.name", equals="n")
- returns: the original content as the body with an empty header when no usable front-matter token exists
- verify: json_path(path="$.metadata", absent=true)
- code: `farrier/farrier/frontmatter.py::split_front_matter`
- tests: `farrier/tests/test_frontmatter_parsing.py::test_nested_metadata_does_not_leak_top_level_keys`

### normalize_tags
- sig: `normalize_tags(value: Any) -> list[str]`
- does: split a string on commas or consume a list/tuple of values
- verify: count(subject="normalized unique tags", equals=2)
- does: strip whitespace and quote characters from each tag
- verify: count(subject="normalized unique tags", equals=2)
- does: lowercase each tag
- verify: count(subject="normalized unique tags", equals=2)
- does: remove later duplicates while retaining first-seen order
- verify: count(subject="normalized unique tags", equals=2)
- returns: an empty list for values other than strings, lists, or tuples
- verify: count(subject="normalized unique tags", equals=2)
- code: `farrier/farrier/frontmatter.py::normalize_tags`
- tests: `farrier/tests/test_skill_tags.py::test_normalize_tags_lowercases_dedupes_and_keeps_order`

### frontmatter_tags
- sig: `frontmatter_tags(text: str) -> list[str]`
- does: read the `tags` value from parsed front matter and normalize it
- verify: count(subject="tags extracted from front matter", equals=2)
- returns: an empty list for absent front matter, absent tags, or malformed YAML
- verify: count(subject="tags extracted from front matter", equals=2)
- code: `farrier/farrier/frontmatter.py::frontmatter_tags`
- tests: `farrier/tests/test_skill_tags.py::test_frontmatter_tags_reads_the_block_list`

### frontmatter_metadata
- sig: `frontmatter_metadata(text: str) -> dict[str, Any]`
- does: read the nested `metadata` mapping from parsed front matter
- verify: json_path(path="$.source", equals="library/skills/stablemate/ostler/SKILL.md")
- returns: the metadata mapping, or an empty mapping when the block is absent or not a mapping
- verify: json_path(path="$.source", equals="library/skills/stablemate/ostler/SKILL.md")
- code: `farrier/farrier/frontmatter.py::frontmatter_metadata`
- tests: `farrier/tests/test_source_command.py::test_frontmatter_metadata_reads_nested_block`

### first_heading
- sig: `first_heading(body: str, fallback: str) -> str`
- does: find the first level-one markdown heading in the parsed body outside fenced code
- verify: json_path(path="$.title", equals="The Title")
- returns: the heading text without surrounding whitespace, or the fallback when no level-one heading exists
- verify: json_path(path="$.title", equals="The Title")
- code: `farrier/farrier/frontmatter.py::first_heading`
- tests: `farrier/tests/test_frontmatter_parsing.py::test_first_heading_ignores_a_heading_inside_a_fence`

### front_matter_end
- sig: `front_matter_end(content: str) -> int`
- does: locate the source line index at which document content begins after front matter
- verify: count(subject="front-matter line-map boundary", equals=1)
- returns: zero when no usable front-matter token or line map exists
- verify: count(subject="front-matter line-map boundary", equals=1)
- code: `farrier/farrier/frontmatter.py::front_matter_end`
