story: workflows-book
date: 2026-11-12
elements: New, DryRunLoopRunner, DryRunResearch, DryRunAuthor, DryRunCoder, DryRunOkfBook, DryRunReviewDebt

Every workhorse-<name> binary is the engine's own command line with one workflow loaded, and its run, dot,
control, inbox, replay and version subcommands start an agent, read a run's recorded state or print the engine's
version. A real run needs an agent CLI and spends money, and the engine's subcommands are the engine's, so the
book plays the two things the workflows package decides by itself: workhorse-new, which writes files, and the
run --dry-run of each workflow, which loads the workflow, stubs every agent turn and node, and writes a run
directory. Sub-flows run standalone (a flow name after run), params, resume and worktree flags are the engine's
and are not played. A dry run ignores --run-id, so every dry run is named <workflow>-dry-run.

Every dry run starts the workflow's whole package and the shared kit it imports, so each dry run names the workflow's
files and the kit's in its source. The sub-flows and the agent prompts of a workflow are read when its run loads, and
a run of one is the engine's.
