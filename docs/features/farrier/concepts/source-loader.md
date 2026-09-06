---
type: concept
slug: source-loader
title: Source loader
---
# Source loader

Discovers installable Markdown sources below one library content root. The loader recognizes both
directory-form skills (`<name>/SKILL.md`) and legacy flat Markdown files, while leaving bundled
reference and script assets attached to their owning skill. Its result is consumed by the layer
loader before selection and rendering; the returned records are described by the
[library source record](source-record.md).

- code: `farrier/farrier/sources.py::load_sources`
- detail: [skill bundled assets](skill-assets.md)

## Methods

### method: load_sources
- sig: `load_sources(root: Path, kind: str, layer: Layer | None = None) -> list[Source]`
- does: scan `root` recursively for every `SKILL.md` and every Markdown file except `SKILL.md` and `README.md`
- verify: count(subject="sources discovered from a library root", equals=1)
- does: exclude Markdown files beneath `references/` or `scripts/` when that directory belongs directly to a skill directory containing `SKILL.md`
- does: retain a `references/` or `scripts/` directory as ordinary library content when it is not owned by a skill directory
- does: return sources sorted by path, with each record carrying the requested `kind`, root-relative POSIX path, derived source id, and supplied layer
- tests: `farrier/tests/test_skill_assets.py::test_reference_markdown_does_not_register_as_its_own_skill`
- tests: `farrier/tests/test_skill_assets.py::test_readme_does_not_register_as_a_source`
- tests: `farrier/tests/test_skill_assets.py::test_scripts_are_not_loaded_as_sources`
- tests: `farrier/tests/test_skill_assets.py::test_a_references_dir_outside_a_skill_still_holds_skills`

The loader delegates source identifiers and machine-independent library paths to the
[source naming and selection](source-naming-selection.md) contract. `SKILL.md` directories are
the owning boundaries for bundled assets; flat Markdown files have no asset directory of their own.
