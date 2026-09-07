---
type: concept
slug: packaged-workflow
title: Packaged workflow directory
---
# Packaged workflow directory

`package_dir` is the package-to-filesystem boundary for workflow prompts. It accepts an
importable package name and returns a real directory; zip-backed resources, namespace packages,
missing packages, and non-directory resources are rejected before the first prompt render.

- code: `workhorse/workhorse/packaged.py::package_dir`
- tests: `workhorse/tests/test_console_script.py::test_a_registry_resolves_to_its_own_package_directory`

## Methods

### method: package_dir
- sig: `package_dir(package: str, *, workflow: str | None = None) -> Path`
- does: resolve the importable package's resource root
- does: return the root when it is a real directory
- raises: `PackagedWorkflowError` when the package cannot be located
- raises: `PackagedWorkflowError` when the resource is not a real directory
- verify: visible(locator="package directory", text="prompts")
- code: `workhorse/workhorse/packaged.py::package_dir`

### method: PackagedWorkflowError

QA invokes `package_dir` with a missing package and captures the raised exception type. It also
constructs `PackagedWorkflowError("installation layout error")` and captures its message.

- sig: `PackagedWorkflowError(message: str)`
- does: identify an installation or package-layout error that prevents filesystem prompt loading
- verify: json_path(path="exception.type", equals="PackagedWorkflowError")
- returns: a `RuntimeError` carrying the operator-facing explanation
- verify: json_path(path="error.message", equals="installation layout error")
- code: `workhorse/workhorse/packaged.py::PackagedWorkflowError`
