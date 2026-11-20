story: none
date: 2026-11-18
elements: CreateEpic, CreateStory, DeleteEpic, DeleteStory

The seed and story commands name the sandbox's three epics and three stories, and a refusal prints the id
folder an epic has in the sandbox. A rule's message is a template over the request, so the model cannot print a folder it
learned from the state. A world where an epic or a story is gone is therefore played only by the `plan` matrix, which
holds no seed or story command that depends on the missing folder.

The seed-only walk composes the examples of every command. `CreateEpic`, `CreateStory`, `DeleteEpic` and `DeleteStory`
give it only the calls that change nothing, so the walk never deletes an epic under the matrices of the other
commands, and it reports the four `plan` scenes that create or delete as never reached. The `plan` matrix and the
journey `ReshapeThePlan` play them against the app.

`delete epic` drops the epic from every milestone that lists it and prints `deleted epic '<id>'`. An epic whose
folder is already gone is reported as absent, and the milestones still drop it.
