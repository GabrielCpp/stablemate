---
type: concept
slug: scaffold-definition-loader
title: Scaffold definition loader
---
# Scaffold definition loader

Loads the library's parameterized scaffold catalog for the `farrier scaffold` command. Definitions
are keyed by their public scaffold id; the higher-precedence layer wins when an overlay and base
library provide the same id. A definition is usable only when its YAML value is a mapping with a
mapping-valued `tree:` entry.

- code: `farrier/farrier/scaffolds.py::load_scaffold_defs`

## Methods

### method: load_scaffold_defs
- sig: `load_scaffold_defs() -> dict[str, dict[str, Any]]`
- does: visit every `.yml` and `.yaml` file under each available layer's `scaffolds/` directory in sorted path order
- verify: count(subject="scaffold definition files visited", equals=1)
- does: parse each definition file with the YAML mapping reader
- does: reject a scaffold id duplicated by two files in the same layer
- verify: count(subject="duplicate scaffold ids rejected within one layer", equals=1)
- does: reject a definition whose value is not a mapping containing a mapping-valued `tree` entry
- does: retain the first definition for an id encountered in layer-precedence order, so a higher layer shadows lower layers
- returns: a mapping from each retained scaffold id, converted to `str`, to its validated definition mapping
- verify: count(subject="retained scaffold definitions returned", equals=1)
- code: `farrier/farrier/scaffolds.py::load_scaffold_defs`
- tests: `farrier/tests/test_scaffold_command.py::test_scaffold_writes_tree_with_defaults`
- tests: `farrier/tests/test_scaffold_command.py::test_duplicate_scaffold_id_across_files_errors`
