story: none
date: 2026-11-17
elements: Doctor, ListEpicRows, ListStoryRows, SearchPlan, BuildIndex, QueryCovering, NextEpic, NextStory, ShowChecks, EvictCache, EditRename, EditRenameUnknown, CreateMilestone, MilestoneEpicsFirst, MilestoneEpicsBoth, MilestoneEpicsUnknown, MilestoneSourceItem, CreateSpec, CreateSpecOfUnknownStory, BacklogAdd, BacklogList, BacklogPrune, BacklogDropWithoutReason, BacklogAdopt, FileDecision, TemplateNew, TemplateFind, TemplateApply, TemplateDelete, ListArtifactKinds, ScaffoldArtifact, VetArtifact, EnvSchema, EnvCheck, EnvList

The commands in `graph.py` take free text in the real tool: an epic name, a story id, a title, a query. The book declares
each of them once per call it plays and writes the words into the argv, so the command has no argument to vary. A free
text field would draw the run's input classes and twins, and the tool answers `" alpha "` and `"alpha"` apart
for most of these, so every field would end as a registered underspecified pair that says nothing about the product.
The commands that do vary a field (`todo`, `seed`, `set-status`, `conflict`, `unblock`, `create epic|story`, `update
story`, `delete`, `path`) stay in `commands.py` with their classes.

A command whose output the book cannot state keeps every line opaque, so the claim is the exit code and the files the
watch reads. These are the readers of the plan (`list`, `search`, `index build`, `query`, `next-epic`, `next-story`,
`checks`, `artifact list`, `edit rename`, `doctor`, `env schema`, the `qa` reports and ledger), whose lines carry ids,
counts, times or a schema the library edits. `doctor` exits 1 on the sandbox, whose stories and epics are bare
scaffolds, so the book states the refusal with no words and the exit code.

`edit rename` is played as the dry run it is without `--write`. The apply path writes and moves files, and the book
does not play it. The Python entry point `ostler/ostler/api.py` is the in-process API workflow nodes call. The command
line never runs it, and the book reaches the tool through the command line only, so `App(ignore=...)` names it.

Three milestone commands are played with the epics `first` and `second`, which the sandbox starts with. A milestone
lists an epic by its position, so the book plays the order `first` then `second` and not the reverse.
