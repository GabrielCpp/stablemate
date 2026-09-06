---
type: concept
slug: okf-builder-shared-paths
title: OKF-builder shared paths
---
# OKF-builder shared paths

These functions are the only OKF-builder derivations for documentation roots, feature books,
build state, coverage artifacts, operator context, and walkthrough scratch. They return absolute
paths except where a helper explicitly returns the repository-relative book prefix. Document paths
are resolved through Ostler; run artifacts stay in the ignored `.agents/okf-build` directory.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py`

## Methods

### docs_root
- sig: `docs_root(docs_path: str = "", repo_dir: str = "") -> Path`
- does: resolves an explicit documentation path or discovers the documentation repository from the supplied repository directory
- verify: count(subject="OKF-builder documentation root resolutions", equals=1)
- returns: an absolute documentation-root path
- verify: count(subject="absolute OKF-builder documentation roots", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::docs_root`

### features_root
- sig: `features_root(root: Path, service: str) -> Path`
- does: resolves one service book, or the complete feature tree when service is empty, using Ostler's configured layout
- verify: count(subject="OKF-builder feature root resolutions", equals=1)
- returns: the resolved feature-root path
- verify: count(subject="resolved OKF-builder feature roots", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::features_root`

### book_scope
- sig: `book_scope(root: Path, service: str) -> str`
- does: converts the service feature root into the documentation-root-relative prefix used to scope graph findings
- verify: count(subject="OKF-builder book scopes", equals=1)
- returns: a slash-terminated relative scope prefix
- verify: count(subject="relative OKF-builder book scope results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::book_scope`

### build_dir
- sig: `build_dir(root: Path) -> Path`
- does: names the `.agents/okf-build` run-state directory beneath the documentation root without creating it
- verify: count(subject="OKF-builder build directory derivations", equals=1)
- returns: the run-state directory path
- verify: count(subject="OKF-builder build directory results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::build_dir`

### ensure_build_dir
- sig: `ensure_build_dir(root: Path) -> Path`
- does: creates the build directory when absent
- verify: created(subject="OKF-builder build directory")
- does: writes a wildcard ignore marker when the build directory has no marker
- verify: created(subject="OKF-builder build directory ignore marker")
- returns: the build-state directory
- verify: count(subject="ensured OKF-builder build directories", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::ensure_build_dir`

### worklist_path
- sig: `worklist_path(root: Path, service: str, scope_id: str = "") -> Path`
- does: names the service worklist under the build directory, using `all` for an empty service and appending a scope suffix when supplied
- verify: count(subject="OKF-builder worklist path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::worklist_path`

### diff_scope_path
- sig: `diff_scope_path(root: Path, service: str) -> Path`
- does: names the changed-paths artifact used by a since-scoped build
- verify: count(subject="OKF-builder diff scope path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::diff_scope_path`

### operator_context_path
- sig: `operator_context_path(root: Path, service: str, scope_id: str = "") -> Path`
- does: names the checkpointed operator context file for a budget or blocked-row gate
- verify: count(subject="OKF-builder operator context path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::operator_context_path`

### walk_worklist_path
- sig: `walk_worklist_path(root: Path, service: str) -> Path`
- does: names the walkthrough's separate worklist so walking does not reuse build-drain state
- verify: count(subject="OKF-builder walkthrough worklist path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::walk_worklist_path`

### walkthrough_scratch
- sig: `walkthrough_scratch(root: Path) -> Path`
- does: selects scratch storage outside the repository for the shared browser profile and log
- verify: count(subject="OKF-builder walkthrough scratch path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::walkthrough_scratch`

### source_inventory_path
- sig: `source_inventory_path(worklist: str | Path) -> Path`
- does: names the source inventory beside its worklist
- verify: count(subject="OKF-builder source inventory path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::source_inventory_path`

### waivers_path
- sig: `waivers_path(features: str | Path) -> Path`
- does: resolves the committed coverage-waivers path beneath the feature root through Ostler
- verify: count(subject="OKF-builder waiver path derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::waivers_path`

### screenshots_dir
- sig: `screenshots_dir(features: str | Path) -> Path`
- does: resolves the walkthrough screenshot directory beneath the feature root through Ostler
- verify: count(subject="OKF-builder screenshot directory derivations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::screenshots_dir`
