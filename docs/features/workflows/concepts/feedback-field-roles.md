---
type: concept
slug: feedback-field-roles
title: Feedback field roles
---
# Feedback field roles

`Feedback` is one polling result, not a choice among alternative field implementations. The
`check_story_feedback` result uses `present` to state whether an outstanding operator message was
found, `scope` to name that message's authoring scope, and `content` to carry the operator note for
the rework prompt. Callers read `present` before treating `scope` or `content` as feedback; the
default result has `present=False`, `scope="story"`, and empty `content`.

No field is preferred or deprecated. Each answers a distinct question about the same result, so a
caller needing the feedback state, its target, or its text uses `present`, `scope`, or `content`
respectively.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback`
- rule: treat `present`, `scope`, and `content` as complementary fields of one feedback result; choose the field that answers whether feedback exists, which authoring scope it targets, or what note it carries
