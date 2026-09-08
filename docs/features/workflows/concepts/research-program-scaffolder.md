---
type: concept
slug: research-program-scaffolder
title: Research program scaffolder
---
# Research program scaffolder

The scaffolder is a one-shot operator tool that creates the directory consumed by the research
workflow. It resolves the repository and program paths, writes the [program manifest](../research-program-manifest.md),
renders the README, progress log, and first gate from the bundled templates, creates `findings/`,
and optionally writes `.agents/program` as the active-program pointer. It refuses to overwrite
existing generated files unless `--force` is supplied. The package initializer has no public API;
the executable surface is `new_program.py`.

- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest](../research-program-manifest.md)
- detail: [research program scaffolder concerns](research-program-scaffolder-concerns.md)
- detail: [research program scaffolder documentation scope](research-program-scaffolder-documentation-scope.md)

## Methods

### slug

- sig: `slug(program_dir: str) -> str`
- does: removes empty, `.` and `specs` path segments from the supplied program directory
- verify: removed(subject="empty, `.` and `specs` path segments from the derived program slug")
- verify: json_path(path="$.slug", matches="^[^/]+(-[^/]+)*$")
- does: joins the remaining segments with hyphens, or replaces `/` with `-` when no segments remain
- returns: the derived program slug
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::slug`

### render

- sig: `render(name: str, repl: dict[str, str]) -> str`
- does: reads the named template from the package-local `templates` directory
- does: replaces every exact replacement key with its replacement value in template order
- returns: the rendered template text
- verify: json_path(path="$.rendered", matches=".+")
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::render`

### write

- sig: `write(path: Path, content: str, force: bool) -> None`
- does: exits with a refusal message when the destination exists and `force` is false
- verify: exit_status(code=1)
- does: creates missing parent directories before writing a destination
- verify: created(subject="the scaffold output file")
- does: writes the supplied content to the destination and reports the path
- verify: persists(subject="the scaffold output file contents")
- raises: `SystemExit` with a refusal message when overwrite is disallowed
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::write`

### main

- sig: `main(logger: logging.Logger) -> None`
- does: accepts a required `--dir` program directory and required `--code-root` source directory
- does: resolves `--repo` to an absolute repository path, defaulting to the current directory
- does: derives the program name, progress path, result branch, and replacement values from the arguments
- does: always writes `program.yml`, `README.md`, the first gate document, and `findings/` below the program directory
- verify: created(subject="the research program scaffold")
- does: writes `PROGRESS.md` at the requested `--progress` path or at `<dir>/PROGRESS.md`
- verify: created(subject="the research progress log")
- does: includes machine envelope and containment settings in `program.yml`, using zero or `none` for unbounded defaults
- verify: persists(subject="the research program manifest")
- does: refuses each existing output unless `--force` is supplied
- verify: exit_status(code=1)
- does: writes `.agents/program` with the program directory when `--set-default` is supplied
- verify: persists(subject="the active research program pointer")
- does: logs the scaffold destination and the next workflow command without invoking the workflow
- returns: `None` after all requested writes succeed
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
