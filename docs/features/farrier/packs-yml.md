---
type: format
slug: packs-yml
title: library pack file
---
# library pack file

The mapping loaded for each `packs: [<id>]` entry in
[`agents.yml`](agents-yml-config.md#packs). Farrier resolves the file as
`packs/<id>.yml` through the configured library layers, with the higher layer
shadowing a lower layer for the same filename. The loader recognizes the
fields below; a pack contributes selections to the repository configuration,
but it does not itself render files.

- file: `packs/<id>.yml`
- code: `farrier/farrier/sources.py::load_pack`
- detail: [agents.yml pack selection](agents-yml-config.md#packs)
- detail: [selection aggregation](concepts/selection-aggregation.md)

## Fields

### description
- type: `string`
- default: absent — no description is required for selection
- verify: json_path(path="$.description", absent=true)
- required: false
- verify: json_path(path="$.description", absent=true)
- semantics: optional human-readable pack metadata
- verify: json_path(path="$.description", absent=true)
- semantics: the installer reads the YAML mapping but does not use this value when collecting selections
- verify: unchanged(subject="merged selection when pack description changes")
- code: `farrier/farrier/sources.py::load_pack`
- detail: [pack field selection](concepts/pack-field-selection.md)

### includes
- type: `list[string]`
- default: `[]`
- verify: count(subject="merged selections when a pack omits includes", equals=0)
- required: false
- verify: json_path(path="$.includes", absent=true)
- semantics: pack ids are recursively merged into this pack
- verify: count(subject="merged skill selection from one included pack", equals=1)
- semantics: an include cycle terminates loading with `Pack include cycle detected at <id>`
- verify: exit_status(code=1)
- code: `farrier/farrier/sources.py::load_pack`
- detail: [pack field selection](concepts/pack-field-selection.md)

### skills
- type: `list[string]`
- default: `[]`
- verify: count(subject="merged skill selection when a pack omits skills", equals=0)
- required: false
- verify: json_path(path="$.skills", absent=true)
- semantics: skill ids or glob patterns are added to the merged selection
- verify: count(subject="merged skill selection from one pack", equals=1)
- semantics: duplicate skill entries collapse when packs and the repository config are unioned
- verify: count(subject="merged skill selection when pack and repository select one skill", equals=1)
- code: `farrier/farrier/sources.py::load_pack`
- detail: [pack field selection](concepts/pack-field-selection.md)

### prompts
- type: `list[string]`
- default: `[]`
- verify: count(subject="merged prompt selection when a pack omits prompts", equals=0)
- required: false
- verify: json_path(path="$.prompts", absent=true)
- semantics: prompt ids or glob patterns are added to the merged selection
- verify: count(subject="merged prompt selection from one pack", equals=1)
- semantics: duplicate prompt entries collapse when packs and the repository config are unioned
- verify: count(subject="merged prompt selection when pack and repository select one prompt", equals=1)
- code: `farrier/farrier/sources.py::load_pack`
- detail: [pack field selection](concepts/pack-field-selection.md)

### roots
- type: `list[string]`
- default: `[]`
- required: false
- semantics: literal root instruction names added to the merged selection
- verify: count(subject="merged root selection from one pack", equals=1)
- semantics: roots are validated even when the Copilot adapter is disabled
- verify: exit_status(code=1)
- semantics: roots render only for the Copilot adapter
- verify: absent(subject="non-Copilot root instruction output")
- code: `farrier/farrier/sources.py::load_pack`
- tests: `farrier/tests/test_selection_misses.py::test_unknown_root_fails_even_with_copilot_disabled`
- detail: [pack field selection](concepts/pack-field-selection.md)

### scaffolds
- type: `list[string]`
- default: `[]`
- required: false
- semantics: scaffold definition ids are made available to `farrier scaffold`
- verify: count(subject="scaffold definitions available to farrier scaffold", equals=1)
- semantics: each entry must be a plain string
- verify: exit_status(code=1)
- semantics: ids from nested packs are unioned with this list
- verify: count(subject="merged scaffold selection from one pack and one nested pack", equals=2)
- code: `farrier/farrier/sources.py::parse_scaffold_ids`
- tests: `farrier/tests/test_scaffold_command.py::test_pack_scaffolds_contribute_available_ids`

Pack loading reads the file with the same YAML mapping validation as
`agents.yml`: a missing file raises `Unknown pack`, and a YAML list or scalar
raises `Config must be a YAML mapping`. `includes` is traversed depth-first;
all four selection sets are unioned from every included pack before the
repository's own selections are added. An included pack is still resolved
through the same library layer stack, so a missing indirect id is reported as
an unknown pack too.

## Methods

### method: load_pack
- sig: `load_pack(pack_id: str, seen: set[str] | None = None) -> dict[str, Any]`
- does: resolves `packs/<pack_id>.yml` from the highest-precedence library layer
- does: recursively loads each `includes:` entry
- does: unions skills, prompts, roots, and scaffolds from included packs
- raises: exits for an unknown direct or indirect pack id
- raises: exits when a recursive include revisits a pack id
- returns: four selection sets keyed by `skills`, `prompts`, `roots`, and `scaffolds`
- verify: exit_status(code=1)
- code: `farrier/farrier/sources.py::load_pack`

### method: parse_scaffold_ids
- sig: `parse_scaffold_ids(entries: Any, origin: str) -> set[str]`
- does: accepts each scaffold entry only when it is a plain string id
- raises: exits with a migration hint when an entry is a mapping or another non-string value
- returns: unique scaffold ids as a set, treating an omitted or empty value as empty
- verify: exit_status(code=1)
- code: `farrier/farrier/sources.py::parse_scaffold_ids`
- tests: `farrier/tests/test_scaffold_command.py::test_legacy_mapping_scaffold_entry_rejected`
