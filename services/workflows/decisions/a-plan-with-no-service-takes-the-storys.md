story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/shared/plan.py::record_plan

The plan's services came only from the dev review turn's result. A turn that left the field out gave a repository-root fallback, root-level gates and an answer check with no repository. The story's declared services now fill an empty list, each mapped to its repository and path through the `services` table of that repository's `agents.yml`. A declared name that maps to no path is left out with a warning. A plan that names its services is recorded unchanged.
