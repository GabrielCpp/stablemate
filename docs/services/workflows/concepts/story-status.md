---
type: concept
slug: story-status
title: Story status persistence
---
# Story status persistence

The coder records a story outcome through this shared adapter so later selection sees the same
status in the story document. Graph-backed writes are preferred; the file rewrite only runs when
there is no story id to resolve through the graph. A story id the graph refuses to write now
raises instead of falling back to the rewrite, so the caller must handle that failure itself.
The caller owns committing the returned paths, so a successful stamp is not complete until those
paths are committed.

- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py` @43edc4a82319

## Fields

### STATUS_PREFIX

- type: string
- default: `- **Status**:`
- required: true
- semantics: literal prefix used when appending a missing body Status field
- verify: json_path(path="$.status_prefix", equals="- **Status**:")
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::STATUS_PREFIX` @43edc4a82319

## Methods

### resolve_story_path

- sig: `resolve_story_path(root: Path, epic: str, slug: str, story_path_arg: str = "") -> Path`
- does: returns the supplied story path when it names an existing file
- does: otherwise derives the story.md path from the documentation root, epic, and slug
- returns: a Path naming the fallback story.md location
- verify: json_path(path="$.story_path", matches="story\\.md$")
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::resolve_story_path` @43edc4a82319

### mark_via_ostler

- sig: `mark_via_ostler(root: Path, story_id: str, new_status: str, logger: logging.Logger | None = None) -> list[Path]`
- does: returns no paths without attempting a graph write when the story id is empty
- does: asks Ostler to set the story status when the story id is non-empty
- does: returns the paths reported by a successful Ostler status update
- does: returns an empty list and logs an informational fallback message only when constructing or calling `Ostler(...)` itself raises `OSError` or `RuntimeError`
- raises: `RuntimeError` with Ostler's message when Ostler reports the status write failed, instead of falling back
- returns: written status paths on success, otherwise an empty list
- verify: persists(subject="the story status written through the document graph")
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::mark_via_ostler` @43edc4a82319

### status_line_index

- sig: `status_line_index(text: str) -> int | None`
- does: parses the document body to locate its machine-recognized Status bullet
- returns: the absolute line index of the Status bullet, or None when no such field exists
- verify: count(subject="parsed story Status fields", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::status_line_index` @43edc4a82319

### rewrite_status

- sig: `rewrite_status(story_md: Path, new_status: str, logger: logging.Logger | None = None) -> list[Path]`
- does: replaces the parsed Status bullet while preserving the other document lines
- does: writes an updated existing Status field through a temporary file followed by replacement
- does: appends a Status bullet using STATUS_PREFIX when the document has no Status field
- does: returns no paths and logs a warning when the replacement write fails
- returns: the story.md path after a successful rewrite or append, otherwise an empty list
- verify: persists(subject="the story body Status field after fallback rewrite")
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::rewrite_status` @43edc4a82319

### current

- sig: `current(root: Path, slug: str, *, epic: str = "", story_path: str = "") -> str`
- does: resolves the story document using the explicit path when available or the epic and slug fallback
- does: returns an empty string when the story document is absent or unreadable
- does: reads the frontmatter status first and the parsed body Status bullet second
- returns: the status value selected by the same precedence as the graph status writer, or an empty string
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::current` @43edc4a82319

### mark

- sig: `mark(root: Path, story_id: str, new_status: str, *, epic: str = "", slug: str = "", story_path: str = "", logger: logging.Logger | None = None) -> list[Path]`
- does: tries the Ostler graph adapter against `story_id` before using the story.md fallback, which `slug` locates instead
- does: rewrites the resolved story.md when graph stamping returns no written paths
- does: logs a warning and returns no paths when no story.md can be resolved
- does: propagates `RuntimeError` instead of falling back when the graph refuses the status write
- returns: every path written by the graph or fallback adapter, or an empty list when stamping fails
- verify: persists(subject="the story outcome after graph-first stamping")
- code: `workflows/src/workhorse_workflows/coder/shared/story_status.py::mark` @43edc4a82319
