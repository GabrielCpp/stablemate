"""The story, the epic and the dev flow every dev flow test builds on."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.dev.flow import Dev

EPIC = "EPIC-1"
STORY = "STORY-1"

STORY_MD = """---
id: STORY-1
type: story
services: [api, web]
---

# Story STORY-1

## Dependencies

(none)

## Fixtures

(none)

## Context

Users need links that only point inside the site.

## Acceptance Criteria

- a relative link destination is rejected

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- the check lives in the api's link validator

## Implementation Status

- **Status**: Not started
"""


def make_dev(docs: Path, operator_mode: str = "auto") -> Dev:
    return Dev(story=STORY, epic=EPIC, operator_mode=operator_mode)
