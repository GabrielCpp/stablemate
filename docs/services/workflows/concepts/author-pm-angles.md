---
type: concept
slug: author-pm-angles
title: Author PM review angles
---
# Author PM review angles

An angle is one question the product manager asks of a stage's output. Each angle lives in its own prompt file under `author/pm/prompts/angles/<stage>/`, and the catalog in `angles.py` lists them in review order. A review returns one verdict per angle, so a stage passes only when every angle passes.

The angles carry the criteria that the per-stage reviewers used to hold. Every old criterion has one home:

| Stage | Angle | What it judges |
| --- | --- | --- |
| epic-split | coverage | every milestone journey, decision, constraint and release boundary reaches an epic |
| epic-split | boundaries | each epic is a vertical, observable slice, with no layer epic |
| epic-split | order | one non-empty list in coding order |
| epic-split | scope | no non-goal delivered, each epic a bare skeleton, no invented decision |
| story-split | coverage | completeness, granularity, the no-deliverable story, assessability and deferral ownership |
| story-split | vertical | the walking-skeleton root and no horizontal slice |
| story-split | order | each dependency is a real prerequisite |
| story-split | services | each story names the books it changes |
| story | journey | observable, verifiable criteria and a complete journey segment |
| story | chrome | presence and absence criteria for conditional components the story changes |
| story | transient-feedback | appear-then-disappear criteria for documented transient outcomes and for the loading, busy and failure states the story introduces |
| story | grounding | grounded and in scope, no hidden decision, correct classification, honest technical notes |
| story | mockup | the story mockup agrees with the milestone journey mockups |
| epic-edit-plan | plan | the edit satisfies the operator intent and stays buildable |

- code: `workflows/src/workhorse_workflows/author/pm/angles.py::ANGLES` @70b78cc0aae0
- code: `workflows/src/workhorse_workflows/author/pm/angles.py::Angle` @70b78cc0aae0
- code: `workflows/src/workhorse_workflows/author/pm/angles.py::stage_prompt` @70b78cc0aae0
- tests: `workflows/tests/author/pm/test_pm.py::test_every_angle_has_a_prompt_and_the_stage_a_brief`
- tests: `workflows/tests/author/test_prompt_authority.py::test_grounding_angle_does_not_demand_prior_citations_for_new_behavior`
- detail: [Author PM review](author-pm-review.md)

## Methods

### stage_prompt
- sig: `stage_prompt(stage: str) -> str`
- does: returns the path of the prompt that briefs the reviewer on what the stage produced
- verify: json_path(path="$.prompt", matches="^pm/prompts/stages/")
- code: `workflows/src/workhorse_workflows/author/pm/angles.py::stage_prompt` @70b78cc0aae0
