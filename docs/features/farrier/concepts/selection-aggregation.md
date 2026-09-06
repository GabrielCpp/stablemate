---
type: concept
slug: selection-aggregation
title: Selection aggregation
---
# Selection aggregation

The installer and scaffold command use this aggregation before they select library sources or
gate a scaffold id. It expands each configured [pack](../packs-yml.md), then adds the repository's
own [`agents.yml` selections](../agents-yml-config.md#packs). The four resulting sets keep skills,
prompts, roots, and scaffold ids separate so their later consumers can apply their distinct
matching, rendering, and availability rules.

`collect_selection` moved from the `farrier.install` compatibility facade to
`farrier.sources.collect_selection`; `farrier.install.collect_selection` remains a public
compatibility import.

- code: `farrier/farrier/sources.py::collect_selection`
- tests: `farrier/tests/test_scaffold_command.py::test_pack_scaffolds_contribute_available_ids`

## Methods

### method: collect_selection
- sig: `collect_selection(config: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str]]`
- does: expand every id in `config.packs`, treating an omitted or empty list as no pack selections
- verify: count(subject="configured packs expanded", equals=1)
- does: union each expanded pack's skills, prompts, roots, and scaffold ids into its matching selection set
- verify: count(subject="selection sets after one pack expansion", equals=4)
- does: add `agents.yml` scaffolds after validating that every local entry is a plain string id
- verify: count(subject="available scaffold ids from a pack and agents.yml", equals=2)
- does: add local skills, prompts, and roots to their matching selection sets
- verify: count(subject="locally selected source categories", equals=3)
- does: collapse duplicate selections because every category is represented as a set
- verify: count(subject="duplicate scaffold ids in the available catalog", equals=1)
- raises: exits when a configured or indirectly included pack id cannot be resolved from the library layers
- verify: exit_status(code=1)
- raises: exits when recursive pack inclusion revisits a pack id
- verify: exit_status(code=1)
- raises: exits when a local `scaffolds:` entry is not a plain string id
- verify: exit_status(code=1)
- returns: the unioned skill selection patterns
- verify: count(subject="returned skill selection patterns", equals=1)
- returns: the unioned prompt selection patterns
- verify: count(subject="returned prompt selection patterns", equals=1)
- returns: the unioned literal root instruction names
- verify: count(subject="returned root instruction names", equals=1)
- returns: the unioned scaffold definition ids
- verify: count(subject="returned scaffold definition ids", equals=1)
- code: `farrier/farrier/sources.py::collect_selection`
- tests: `farrier/tests/test_scaffold_command.py::test_pack_scaffolds_contribute_available_ids`
