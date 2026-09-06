---
type: concept
slug: drift-report
title: Drift report
---
# Drift report

The `--check` report explains missing, changed, extra, and edited hook-manager output without
trusting provenance copied into the worktree. It attributes changes from the expected render.

### method: Drifted
- sig: `Drifted(rel: str, content: str, expected: str, actual: str)`
- does: carry the relative output path, rendered record, expected text, and worktree text for one drift finding
- code: `farrier/farrier/drift.py::Drifted`
- verify: count(subject="drifted output records", equals=1)

## Methods

### method: sources_for
- sig: `sources_for(content: str, expected: str) -> list[str]`
- does: return recorded aggregate sources when present, otherwise front-matter source metadata, otherwise banner sources
- returns: an empty list when no provenance carrier is present
- verify: count(subject="provenance sources selected from expected output", equals=1)
- code: `farrier/farrier/drift.py::sources_for`

### method: attribute
- sig: `attribute(content: str, actual: str) -> set[str]`
- does: identify aggregate source parts missing from the actual text
- returns: an empty set when every recorded part was altered or no parts were recorded
- verify: count(subject="aggregate source parts attributed to drift", equals=1)
- code: `farrier/farrier/drift.py::attribute`

### method: changed_report
- sig: `changed_report(rel: str, sources: list[str], drifted: set[str]) -> str`
- does: describe the changed output, its editable source files, and the regeneration command
- verify: visible(locator="changed output remediation", text="re-render")
- code: `farrier/farrier/drift.py::changed_report`

### method: missing_report
- sig: `missing_report(rel: str) -> str`
- does: identify a missing generated file and tell the operator to regenerate it
- verify: visible(locator="missing output remediation", text="Run")
- code: `farrier/farrier/drift.py::missing_report`

### method: extra_report
- sig: `extra_report(rel: str) -> str`
- does: explain that an output is no longer generated and must be deleted or selected again
- verify: visible(locator="extra output remediation", text="Delete")
- code: `farrier/farrier/drift.py::extra_report`

### method: fence_report
- sig: `fence_report(rel: str) -> str`
- does: explain restoration or disabling of a Farrier hook fence while preserving surrounding user content
- verify: visible(locator="hook fence remediation", text="Everything outside the fence")
- code: `farrier/farrier/drift.py::fence_report`

### method: footer
- sig: `footer() -> str`
- does: explain that comparison uses the working tree and identify `farrier source` as the reverse lookup
- verify: visible(locator="drift report footer", text="working tree")
- code: `farrier/farrier/drift.py::footer`

### method: report
- sig: `report(missing: list[str], changed: list[Drifted], extra: list[str], fences: list[str] | None = None) -> str`
- does: emit missing, changed, extra, and hook-fence blocks in category order followed by the footer
- verify: count(subject="drift report category blocks", equals=4)
- code: `farrier/farrier/drift.py::report`
