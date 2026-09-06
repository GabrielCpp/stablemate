---
type: concept
slug: library-frontmatter-check
title: Library front-matter check
---
# Library front-matter check

This module validates the YAML front matter that library skills and prompts expose to the
renderer, including losses that `yaml.safe_load` would otherwise hide.

### method: Finding
- sig: `Finding(path: Path, level: str, code: str, message: str)`
- does: carry one source path, severity, machine code, and explanation
- code: `farrier/farrier/library_check.py::Finding`
- verify: count(subject="library validation finding records", equals=1)

### method: render
- sig: `Finding.render(root: Path | None = None) -> str`
- does: render a finding with an optional root-relative path
- code: `farrier/farrier/library_check.py::Finding.render`
- verify: visible(locator="rendered library finding", text="error")

## Methods

### method: _fence
- sig: `_fence(text: str) -> str | None`
- does: extract the opening Markdown front-matter block after normalizing line endings
- verify: count(subject="front-matter blocks extracted from source text", equals=1)
- code: `farrier/farrier/library_check.py::_fence`

### method: _top_level_scalars
- sig: `_top_level_scalars(fence: str) -> dict[str, yaml.ScalarEvent]`
- does: retain parser events for load-bearing top-level scalar values
- verify: count(subject="load-bearing scalar parser events", equals=1)
- code: `farrier/farrier/library_check.py::_top_level_scalars`

### method: _retyped_tags
- sig: `_retyped_tags(fence: str) -> list[tuple[str, str]]`
- does: identify tag values YAML resolves to a non-string type and record written and installed forms
- verify: count(subject="retyped YAML tag findings", equals=1)
- code: `farrier/farrier/library_check.py::_retyped_tags`

### method: _trailing_text
- sig: `_trailing_text(fence: str, event: yaml.ScalarEvent) -> str`
- does: return non-value text remaining on the scalar's source line
- verify: count(subject="scalar trailing-text inspections", equals=1)
- code: `farrier/farrier/library_check.py::_trailing_text`

### method: _spec_findings
- sig: `_spec_findings(text: str, data: dict, path: Path, declared: str, description: str) -> list[Finding]`
- does: validate SKILL.md name, description, and body limits against the published skill specification
- verify: count(subject="skill specification findings", equals=1)
- code: `farrier/farrier/library_check.py::_spec_findings`

### method: check_text
- sig: `check_text(text: str, path: Path, require_tags: bool = True) -> list[Finding]`
- does: validate front matter parsing, mapping shape, scalar fidelity, tags, hooks, and skill requirements
- verify: count(subject="front-matter findings for one library source", equals=1)
- code: `farrier/farrier/library_check.py::check_text`

### method: _stutter_finding
- sig: `_stutter_finding(root: Path, sub: str, path: Path) -> Finding | None`
- does: warn when a source basename repeats its containing library group
- verify: count(subject="group-stutter findings", equals=1)
- code: `farrier/farrier/library_check.py::_stutter_finding`

### method: check_library
- sig: `check_library(roots: list[Path], require_tags: bool = True) -> tuple[list[Finding], int]`
- does: scan each distinct skills and prompts tree, skipping un-fenced bundled references
- returns: all findings and the number of checked sources
- verify: count(subject="distinct library sources checked", equals=1)
- code: `farrier/farrier/library_check.py::check_library`

### method: format_findings
- sig: `format_findings(findings: list[Finding], checked: int, root: Path | None = None) -> str`
- does: render errors before warnings and report the checked-source count
- verify: visible(locator="formatted library check report", text="source")
- code: `farrier/farrier/library_check.py::format_findings`
