story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/shared/review.py::evidence_gap

A review finding can concern a file of the story's spec folder, such as its plan or a recorded measurement. In a workspace whose spec folder sits outside the code repositories, no commit carries that fix.

A fixed answer may therefore cite the spec file by a `- path:` line. The check accepts it when the file exists inside the story's spec folder. The path may be absolute, relative to the spec folder, or end with the folder's own trailing parts. A path that escapes the folder, names a directory or names a missing file does not hold.

Commit evidence and test evidence keep their rules.
