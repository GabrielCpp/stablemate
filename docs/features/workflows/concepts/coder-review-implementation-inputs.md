---
type: concept
slug: coder-review-implementation-inputs
title: Coder review implementation inputs
---
# Coder review implementation inputs

The implementation reviewer receives three complementary inputs in every invocation. The story
path identifies the acceptance criteria being judged, the specification directory supplies the
implementation plan and receives review artifacts, and the affected repository paths identify
the implementations and tests to inspect. They are passed together to the reviewer; none is an
alternative to another and no ranking exists.

- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.review`
- rule: provide `story_path`, `spec_dir`, and `affected_repo_paths` together for every implementation review
