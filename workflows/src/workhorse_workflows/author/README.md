# author

The `author` workflow: one approved milestone in, a validated planning graph of epics and stories out. Each subpackage is one machine that the `workhorse-author` command can run on its own.

## Map

- `epic_author/`: the machine that writes one named epic's prose and seeds.
- `epic_edit/`: the machine that reconciles one epic's scope, journeys, seeds and stories after a change.
- `epic_split/`: the machine that splits one approved milestone into ordered epic skeletons.
- `finalize/`: the machine that validates an authored milestone and commits it.
- `main/`: the default `author` flow that drains epics, story splits and stories from the work list.
- `pm/`: the PM: the angled review every authoring stage passes, the answers it gives the writers' gaps, its ledger and its receipt.
- `parity_surveyor/`: the machine that compares a legacy baseline against the current OKF book, one surface at a time.
- `shared/`: what more than one author machine needs: paths, schemas, the shared nodes and the survey kit.
- `story_author/`: the machine that writes one named story and sends it to the PM.
- `story_edit/`: the machine that turns a story add or remove request into an epic-edit handoff.
- `story_split/`: the machine that splits one epic into a story graph and accepts its coverage.
- `surveyor/`: the machine that surveys a repo against one rubric, one unit at a time.
- `workflow.py`: the composition root: which flows, blueprints and dry-run agent stubs the `author` command registers.
