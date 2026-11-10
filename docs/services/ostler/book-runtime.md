---
type: cli
slug: book-runtime
title: ostler book
---
# ostler book

`ostler book <verb> ...` runs a [service book](concepts/service-book.md): the executable Python model of one HTTP or gRPC service that lives under `services/<name>/` in a repo. The verbs build what the book declares, play it against the running service, search it and keep it current with the service's source. A run judges the service against the book, so a green run means the service does what the book says. The page [What a run judges](concepts/what-a-run-judges.md) lists what the verdict covers and what it leaves out.

`ostler book` hands every argument after `book` to the runtime's own command line and leaves with its exit code. The directory that holds `services/` is the working directory, or the one `-C DIR` names before `book`. The command puts that directory first on the import path itself, so no `PYTHONPATH` is set. A service is named by its module, as in `services.api`. `python -m ostler.book <verb>` runs the same command line.

A verb that takes a service exits through one rule: 0 when the verdict is good, 1 when the service or the book is wrong, 2 when the command cannot do what was asked, 3 when the place cannot be judged.

- binary: ostler
- code: ostler/ostler/cli.py::_cmd_book@7a2f3e9833fd
- code: ostler/ostler/book/cli.py::main@325a304f7f89
- code: ostler/ostler/book/cli.py::build_parser@423018a4f9c8
- detail: [A service book](concepts/service-book.md)
- detail: [What a run judges](concepts/what-a-run-judges.md)

## Commands

### ostler-book-run

Reads each health journey the service declares on a fresh model before anything else and stops without a verdict when one fails or a host does not answer. Plays the journeys in the chosen order on one long-lived account, and prints one line per journey with its verdict PASS, KNOWN, FAIL or SKIP, its step count and its time. After the journeys, plays every declared cell of the lifecycle matrices, then every input class of every endpoint, when no `--journey` is given. Prints the witness report, the answers and fields the run saw the service produce against those the book declares. Writes `<out>/<service>.md`, the journeys step by step with the model and the app side by side, the state table played and the input classes sent, and `<out>/<service>-witness.md`, the witness report. Writes the stack's process output to `<out>/logs/<process>.log`.

- usage: ostler book run SERVICE [--journey TITLE ...] [--partial] [--only ENDPOINT,...] [--order declared|reversed|shuffled] [--seed N] [--out DIR] [--no-stack] [--env NAME] [--print-exec] — checks the book, starts the service's stack, reads the health journeys, plays every journey, every declared cell of the lifecycle matrices and every input class, and prints the verdict; exits 0 when all of it passes and the witness is complete, 1 when a journey, cell or input fails, a declared known defect or divergence was never met, an answer or field stays unseen undeclared, or the check of the book finds a fault that blocks a run, 2 for `--journey` without `--partial` or when saddlebag leaves a secret unset, 3 when the place cannot be judged
- flags:
  - --journey (play the journey of this title only, repeatable; the rest stay unseen, so the run needs --partial)
  - --partial (a run of some journeys only: unseen answers and unmet defects do not fail it)
  - --only (play only the journeys that call these endpoints, their declared cells and their input classes; the names are endpoint class names, repeatable or comma-separated, and a name the service does not declare stops the command; a declared divergence of a named endpoint that was never met still fails the run)
  - --order (the order the journeys are taken in on the one long-lived account: declared, reversed or shuffled; declared by default)
  - --seed (the seed of a shuffled order, 0 by default)
  - --out (the directory the reports go to, `results` by default, relative to the working directory)
  - --no-stack (leave the stack alone: the service is already running at the environment's address)
  - --env (the environment to reach, by name; omitted, the service's default)
  - --print-exec (print the saddlebag command that would supply the secrets, and stop)
- args: service — the module of the book, such as `services.api`
- exits: 0 when every journey, cell and input passes and the witness is complete
- run: invoke(argv=["-C", "book-todo", "book", "run", "services.api"])
- verify: exit_status(code=0)
- verify: stdout(matches="5 pass, 0 known defects, 0 fail")
- verify: stdout(matches="27 of 27 answers and 47 of 47 fields witnessed")
- exits: 2 when journeys are named without `--partial`
- run: invoke(argv=["-C", "book-todo", "book", "run", "services.api", "--journey", "AWeekOfChores"])
- verify: exit_status(code=2)
- verify: stdout(text="a run of some journeys leaves the rest unseen: add --partial")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_run@80afbf8ae3c7
- code: ostler/ostler/book/cli.py::report@b08de2d26283
- code: ostler/ostler/book/cli.py::unhealthy@a5cb92003bb1
- code: ostler/ostler/book/witness.py::WitnessReport@bc2d28ac2287
- detail: [What a run judges](concepts/what-a-run-judges.md)
- detail: [Known defects](concepts/known-defects.md)
- tests: ostler/tests/test_book_todo.py::test_run_plays_the_journeys_the_cells_and_the_input_classes
- tests: ostler/tests/test_book_todo.py::test_an_update_that_changes_nothing_turns_the_book_red

### ostler-book-check

Builds each endpoint, journey, rule, matrix and decision the book declares once and names every one that raises or comes out without its text. Names the endpoints, journeys, rules and states nothing registers, the endpoints no matrix places, the modules nothing imports and the source pointers that name no file. Counts an `index.tsv` that differs from what `index` would write as a finding that does not block a run.

- usage: ostler book check SERVICE [--app ROOT] [--env NAME] — builds everything the book declares with no stack running and prints `check: N findings` after one line per finding; exits 0 with no finding and 1 with any
- flags:
  - --app (the app's root; every source pointer the book names must exist under it)
  - --env (the environment whose secrets are checked; omitted, the service's default)
- args: service — the module of the book
- exits: 0 when the book has no finding
- run: invoke(argv=["-C", "book-todo", "book", "check", "services.api"])
- verify: exit_status(code=0)
- verify: stdout(text="check: 0 findings")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/check.py::cmd_check@ae79aa18df1a
- code: ostler/ostler/book/check.py::check@8056b584d6ad
- detail: [A service book](concepts/service-book.md)
- tests: ostler/tests/test_book_todo.py::test_check_finds_nothing_wrong_with_the_book

### ostler-book-explore

Prints the number of new state signatures at each depth, the cells in all as baselines, refusals and input classes, the declared scenes the walk never reached and the rules no cell refused. Writes `<out>/<service>-explore.md`, the walk, the failures with the path that reached each and the cells. Names a book that contradicts itself when a fixture or scene arranges a record the model refuses.

- usage: ostler book explore SERVICE [--depth N] [--only ENDPOINT,...] [--seed-only] [--out DIR] [--no-stack] [--env NAME] [--print-exec] — walks the model's state graph to a depth bound, then plays every state, action and input class it reached once against the service; exits 0 when every cell passes, 1 when a cell fails or the check of the book blocks, 3 when the place cannot be judged
- flags:
  - --depth (the depth bound of the walk, 4 by default)
  - --only (play the cells of these endpoints only, repeatable or comma-separated; the walk stays whole)
  - --seed-only (walk and list the cells without touching the app, so no stack starts and no secret is needed)
  - --out (the directory the report goes to, `results` by default)
  - --no-stack (leave the stack alone)
  - --env (the environment to reach)
  - --print-exec (print the saddlebag command that would supply the secrets, and stop)
- args: service — the module of the book
- exits: 0 when the seed-only walk ends
- run: invoke(argv=["-C", "book-todo", "book", "explore", "services.api", "--seed-only"])
- verify: exit_status(code=0)
- verify: stdout(matches="cells: 109 total")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_explore@bab3c85eed93
- code: ostler/ostler/book/cli.py::report_exploration@ffb1b7c42d66
- code: ostler/ostler/book/exploration.py::seed@5e45b9984c09
- detail: [Cells of a scene share an arrangement](concepts/cells-share-an-arrangement.md)
- tests: ostler/tests/test_book_exploration.py

### ostler-book-walk

Prints the scene's description, one line per step taken as ok, FAIL or SKIP, then the scene the model now reads and the model's state.

- usage: ostler book walk SERVICE --scene NAME [--action NAME] [--record RECORD] [--out DIR] [--no-stack] [--env NAME] [--print-exec] — arranges one scene of one matrix on the live service, takes one action there and prints each step with the model and the app side by side; exits 0 when every step is ok, 1 when a step fails, 2 for an action the matrix does not name, 3 when the place cannot be judged
- flags:
  - --scene (a scene named in the matrix, required)
  - --action (an action named in the matrix; omitted, only the scene is arranged)
  - --record (the record whose matrix is meant; omitted, the service's first)
  - --out (the directory for the stack's logs, `results` by default)
  - --no-stack (leave the stack alone)
  - --env (the environment to reach)
  - --print-exec (print the saddlebag command that would supply the secrets, and stop)
- args: service — the module of the book
- exits: 2 when the action is not one of the matrix's
- run: invoke(argv=["-C", "book-todo", "book", "walk", "services.api", "--scene", "overdue", "--action", "nosuch"])
- verify: exit_status(code=2)
- verify: stdout(matches="no action named 'nosuch'")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_walk@e516fae814a3
- code: ostler/ostler/book/cli.py::axes_of@502c66220188
- detail: [Cells of a scene share an arrangement](concepts/cells-share-an-arrangement.md)

### ostler-book-index

Writes one row per endpoint, action, rule, defect, state rule, journey, screen and scene, and the decisions are read from their files at search time.

- usage: ostler book index SERVICE — writes `index.tsv` in the service's package directory, which `search` reads without importing the service, and prints its path with `changed` or `unchanged`; exits 0
- args: service — the module of the book
- exits: 0 after the file is written
- run: invoke(argv=["-C", "book-todo", "book", "index", "services.api"])
- verify: exit_status(code=0)
- verify: stdout(matches="index.tsv: (changed|unchanged)")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/index.py::cmd_index@a1204a3a58cf
- code: ostler/ostler/book/index.py::write@87b10c1277f3
- detail: [A service book](concepts/service-book.md)

### ostler-book-search

Reads each service's `index.tsv` and its decision files as text, and rebuilds an index that is older than the service's files by importing the service, saying `index stale: <service>` on stderr.

- usage: ostler book search TERM [--service SERVICE] [--kind KIND] — prints every place a term appears among the endpoints, rules, defects, actions, journeys, screens, scenes and decisions, as the kind and address of each item with the matching lines; exits 0 with a match and 1 with none
- flags:
  - --service (search this service only; omitted, every service under `services/`)
  - --kind (one of rule, defect, endpoint, action, journey, screen, scene, decision)
- args: term — the text to find, matched without regard to case; the old form `search SERVICE TERM` still works
- exits: 1 when nothing says the term
- run: invoke(argv=["-C", "book-todo", "book", "search", "zzz-no-such-term"])
- verify: exit_status(code=1)
- verify: stdout(matches="nothing in the book says 'zzz-no-such-term'")
- exits: 0 when something does
- run: invoke(argv=["-C", "book-todo", "book", "search", "overdue", "--service", "services.api"])
- verify: exit_status(code=0)
- verify: stdout(matches="endpoint")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/index.py::cmd_search_book@85c075cfa6d3
- code: ostler/ostler/book/search.py::cmd_search@2a6f015e1f34
- detail: [A service book](concepts/service-book.md)

### ostler-book-explain

Prints the address of the class, its description, the journeys that call it and the decisions that name it.

- usage: ostler book explain SERVICE NAME — prints everything the book says of one endpoint, action, screen, interaction or journey, by class name; exits 0, and stops with the reason when the book has no such name
- args:
  - service — the module of the book
  - name — the class name
- exits: 0 when the name is found
- run: invoke(argv=["-C", "book-todo", "book", "explain", "services.api", "AddTodo"])
- verify: exit_status(code=0)
- verify: stdout(text="POST /todos")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/search.py::cmd_explain@59b23ff93463
- detail: [A service book](concepts/service-book.md)

### ostler-book-stale

Prints the verified commit and the app's head, the endpoints and records whose cited source changed, the changed files and functions no element names, the pointers to files that no longer exist and the decisions that touch a stale element. Needs the app root to be a git work tree, and stops with git's own error on a directory that is not one.

- usage: ostler book stale SERVICE --app ROOT — lists the elements whose source changed since the commit the book was last verified against; exits 0 with nothing stale, 1 with stale elements or open items, 2 when the book has no verified commit or declares no app
- flags:
  - --app (the app's git work tree, required)
- args: service — the module of the book
- exits: 2 when the book carries no verified commit
- run: invoke(argv=["-C", "book-todo", "book", "stale", "services.api", "--app", "."])
- verify: exit_status(code=2)
- verify: stdout(text="not verified: write the commit with 'verified'")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_stale@c8c64fa71c07
- code: ostler/ostler/book/sources.py::stale@6d1d50984121
- detail: [A service book](concepts/service-book.md)

### ostler-book-verified

Refuses to record a commit while `stale` still lists an open item, and prints what to settle first. Writes the commit to the file the service's `App` names, in the service's package directory.

- usage: ostler book verified SERVICE --app ROOT — records the app's head commit as the commit the book is verified against, by writing it to the file the service's `App` declares and printing it; exits 0 when it is written, 1 while a changed file or function is named by no element or a pointer names no file, 2 when the service declares no app
- flags:
  - --app (the app's git work tree, required)
- args: service — the module of the book
- exits: 0 when the commit is written
- run: invoke(argv=["-C", "book-todo", "book", "verified", "services.api", "--app", "."])
- verify: exit_status(code=0)
- verify: stdout(matches="^[0-9a-f]{7,}")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_verified@b2434c611334
- code: ostler/ostler/book/sources.py::head_of@5674950bf41b
- detail: [A service book](concepts/service-book.md)

### ostler-book-decisions

Reads each markdown file under `decisions/` beside the service, whose header names its story, its date and the Python elements it explains.

- usage: ostler book decisions SERVICE [--story ID] [--element NAME] — lists the decisions the service settled, one line each with the slug, the story, the date and the first sentence; exits 0
- flags:
  - --story (list the decisions of this story only)
  - --element (list the decisions that name this element only)
- args: service — the module of the book
- exits: 0 whether or not a decision is found
- run: invoke(argv=["-C", "book-todo", "book", "decisions", "services.api"])
- verify: exit_status(code=0)
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/decisions.py::cmd_decisions@c929fd01c5ad
- detail: [A service book](concepts/service-book.md)

### ostler-book-graph

Writes `<out>/<service>-<record>.dot` and prints its path, with the svg beside it when `dot` ran and a note that there is no svg when it is absent. Stops with the records the service has when the named record has no matrix.

- usage: ostler book graph SERVICE [--record RECORD] [--out DIR] — draws each record's state graph and table from its matrix as a dot file, and as an svg where `dot` is on the machine; exits 0
- flags:
  - --record (one record; omitted, every matrix)
  - --out (the directory the files go to, `results` by default)
- args: service — the module of the book
- exits: 0 after the files are written
- run: invoke(argv=["-C", "book-todo", "book", "graph", "services.api", "--record", "chore"])
- verify: exit_status(code=0)
- verify: stdout(matches="api-chore.dot")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_graph@49831af2dfee
- code: ostler/ostler/book/graph.py::dot@f2adbd03bb1d
- detail: [A service book](concepts/service-book.md)

### ostler-book-endpoints

Prints every declared answer with its status, its shape and the reason the book gives.

- usage: ostler book endpoints SERVICE — prints each body shape the service declares with its fields, then each endpoint with its route, its auth, its answers and the model action it carries; exits 0
- args: service — the module of the book
- exits: 0
- run: invoke(argv=["-C", "book-todo", "book", "endpoints", "services.api"])
- verify: exit_status(code=0)
- verify: stdout(text="POST /todos")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_endpoints@ae8575a76aa5
- detail: [A service book](concepts/service-book.md)

### ostler-book-screens

Describes each declared screen, then lists the interactions.

- usage: ostler book screens SERVICE [--lang LANG] — prints the screens and the interactions the service declares, in the language given, `en` by default; exits 0, and prints nothing for a service that declares none, which every HTTP and gRPC book is
- flags:
  - --lang (the language the screens are described in)
- args: service — the module of the book
- exits: 0
- run: invoke(argv=["-C", "book-todo", "book", "screens", "services.api"])
- verify: exit_status(code=0)
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_screens@06efe5170dd7
- detail: [What a service book cannot say yet](concepts/what-a-service-book-cannot-say-yet.md)

### ostler-book-matrix

Prints each cell as the state it reaches and the change it makes, as `refuse` with the answer when the model turns the action away, or as `impossible` when no such action can be built in that scene.

- usage: ostler book matrix SERVICE — prints each record's lifecycle matrix computed on the model, the scenes the record can be in and a table of what each action does in each scene; exits 0
- args: service — the module of the book
- exits: 0
- run: invoke(argv=["-C", "book-todo", "book", "matrix", "services.api"])
- verify: exit_status(code=0)
- verify: stdout(text="### Scenes")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_matrix@811fc7b0b2d1
- code: ostler/ostler/book/matrix.py::matrix@88dd0c4a6947
- detail: [Cells of a scene share an arrangement](concepts/cells-share-an-arrangement.md)

### ostler-book-denied

Needs no running service, because the answer comes from the model alone.

- usage: ostler book denied SERVICE [--given EXPRESSION ...] — prints the state the model reaches after the given requests, then each request the state refuses with the rule and the answer it earns; exits 0, and 2 for a service that declares no endpoint
- flags:
  - --given (a request to perform first, as a Python expression over the service's endpoints and fixtures, plus `today`, `date` and `timedelta`; repeatable, and `name = expression` binds a name for the later ones)
- args: service — the module of the book
- exits: 0 after the refusals are listed
- run: invoke(argv=["-C", "book-todo", "book", "denied", "services.api", "--given", "AddTodo(todo('Buy milk'))"])
- verify: exit_status(code=0)
- verify: stdout(text="From this state:")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_denied@d001a3a7d2b4
- code: ostler/ostler/book/denied.py::denied@da118e083e2b
- detail: [A service book](concepts/service-book.md)

### ostler-book-plan

Needs no running service, because the search runs on the model alone.

- usage: ostler book plan SERVICE --goal EXPRESSION [--given EXPRESSION ...] [--text TEXT ...] [--depth N] [--only KIND,...] — searches the model for the shortest sequence of requests from the given state to one where the goal holds, and prints it step by step; exits 0 when a sequence is found within the depth and 1 when none is
- flags:
  - --goal (an expression over `state` that holds where the user wants to be, required)
  - --given (a request to perform first, as for `denied`)
  - --text (a text the planner may put in a string field, repeatable)
  - --depth (the most moves the plan may take, 8 by default)
  - --only (comma-separated step kinds the plan may use, by the start of the class name)
- args: service — the module of the book
- exits: 0 when a plan is found
- run: invoke(argv=["-C", "book-todo", "book", "plan", "services.api", "--given", "AddTodo(todo('Buy milk'))", "--goal", "len(state.rows()) == 0"])
- verify: exit_status(code=0)
- verify: stdout(text="1 moves:")
- fixture: [book todo scratch](fixtures/book-todo-scratch.md)
- code: ostler/ostler/book/cli.py::cmd_plan@215123dc5bb0
- code: ostler/ostler/book/planner.py::plan@fbfdb915914b
- detail: [A service book](concepts/service-book.md)
