story: none
date: 2026-11-21
elements: CheckEnvironment

`environment` starts `claude -p` and one engine turn and compares the lists their init events carry. Each is a paid model call, and the lists depend on the machine's skills, plugins and hooks, so the sandbox can neither provide nor fix them. The book plays only the refusals the command makes before it starts a session: a config file that does not exist and a profile the config does not define. The comparison is a pure function of two init events, a refused-tool list and the delegate names, and the engine's own tests play it. Its other exits are never played: 0 when the turn loads everything the plain session loads, 1 when it misses names, 2 when the profile's backend reports no load list, and 3 when a session passes its limit or sends no init event. `Service.unseen` says so for the inputs of `CheckEnvironment`, and the exit codes are listed in workhorse/README.md.
