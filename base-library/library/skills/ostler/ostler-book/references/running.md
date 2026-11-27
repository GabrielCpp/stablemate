# The commands

Reached from [../SKILL.md](../SKILL.md) before you check, explore, run or land a book.

Run from the code repository, or from the book root with `--app`, one at a time.
`ostler book branch` opens the book branch of the current code branch and prints its root. `ostler book land` lands it on the artifacts base by rebase and fast-forward, then removes its worktree and branch. Never start a second `run` or `explore` while
one is live.

| Command | Takes | Tells you |
| --- | --- | --- |
| `ostler book check services.<name>` | seconds, no app | the format: unregistered endpoints, journeys or rules, unplaced endpoints, modules nothing imports, missing source pointers, a journey with no docstring |
| `ostler book explore services.<name> --seed-only` | seconds to minutes as matrices grow, no app | the model's walk to depth 4; run it after every change to a fixture, a scene or an endpoint; "the book contradicts itself" means a fixture arranges a record that cannot exist |
| `ostler book explore services.<name> --no-stack --only <A>,<B>` | about 2 s a cell | every cell of the named endpoints, or interactions in a screen book, on every state the walk reaches, against the app |
| `ostler book run services.<name> --no-stack --only <A>,<B>` | a few minutes | the journeys that call the named endpoints or interactions, their declared cells and their input classes, including divergences declared for them and never met |
| `ostler book run services.<name> --no-stack` | tens of minutes | every journey, every declared cell and every input class; the book's gate, run when a backfill ends and nightly, never per batch |

A run prints the section `Stated and never played` before its verdict: each outside happening, action, rule and scene
that no play exercised, with what closes it (a journey step or a given that arranges the happening, a cell built in the
scene, a step or input class that draws the refusal). It is a list and never turns the run red. An action carried only by
an unplayed outside happening is named on the happening's line. The run also writes `<service>-played.json` to the report
folder: each element with the journeys, cells and input classes that exercised it.
| `ostler book move [NAME ...] [--repo REPO] [--from FOLDER] [--to FOLDER] [--dry-run]` | seconds, no app | moves flat books into `services/<repo>/` of the artifacts checkout `--to` names, and rewrites every dotted module name; `--from` moves a whole `services/` folder out of a code repository; lists each `services/<name>/` path to check by hand; `--dry-run` changes nothing |
| `ostler book index services.<name>` | seconds | rebuilds the search index in the user cache. `search` keeps that index itself, so nothing is committed and nothing needs to run |
| `ostler book stale services.<name> --app <root>` | seconds, no app | the elements whose source changed since the verified commit, changed files no element names, decisions they touch |
| `ostler book missing services.<name> --app <root> [--under <folder>] [--files]` | seconds, no app; minutes the first time on a Go app, then cached per commit | every tracked file under the app's roots that no element names, every call a contract file lists that no element declares, every function under the roots of a Go app whose calls reach a bus send (shared code included) that no action emitting names in its `source`, and every emitted event no environment's delivery taps; prints the map of each named file to its elements, the unnamed files, a count per ignore pattern (`--files` lists them), the undeclared calls and the unmodelled publishes; exits 1 for any of them, and when the call graph cannot be read; the batch a backfill works through |
| `ostler book decisions services.<name> --unexplained [--kind KIND]` | seconds, no app | the class name of each endpoint, record, screen and interaction no decision names, one per line; `--kind` keeps `endpoint`, `record`, `screen` or `interaction` |
| `ostler book verified services.<name> --app <root>` | seconds | records the app's HEAD once `stale` is worked |
| `ostler book affected services.<name> --app <root> [--since <commit>] [--out <dir>]` | seconds, no app | the calls and journeys to play for the code changed since the verified commit or `--since`, uncommitted and untracked work included; plan `none`, `empty`, `partial` or `whole` (`empty`, with exit 1, means files changed and none selects a play), the changed files of the book's own folder read class by class (an edited element class selects its plays, and a changed module-level name, or a changed class that is no element, selects the elements that use it, found through the book's own files; only a changed line that is no class and no name, or a name the walk cannot trace, makes the plan whole), the files outside every root it did not judge under `diff.not_computed`, the `only` and `journeys` lists to pass to `run`, `whole` with its `reason`, the chain from each changed symbol to its element and plays, with how it was reached (`direct`, or `through` the nearest symbol that mentions the change), the changed symbols and paths no element names (exit 1), the ignored ones, the Go import-only files, the widened places (a hunk with no definition line, still a list), and the fallbacks that made the plan whole (a screen no interaction names or an action no call carries goes under `unplayed` and does not widen the plan; a record or an event still makes it whole); writes `<service>-affected.json`; ends with the `run` line to play |

`--only` takes endpoint class names, or interaction class names in a screen book, or outside happening names, never journey names. A wrong name is refused before anything starts. `explore` and `run` print their verdict when they end, and a long one may outlive the shell's
wait. Send the output to a file and read its last lines once the command has exited.
[play.md](play.md#running-a-long-play) says how to start one and what it prints. Their report goes under
`--out`. Omitted, it goes to a fresh temp folder the command names on a `reports:` line. In a story, point `--out` at the story's spec folder, and never inside a repository. `--no-stack` skips starting the
stack `service.py` declares, and changes nothing when that stack is empty.

An application the book does not start still needs its data reloaded. The stack states how, and `ostler book run <module> --fresh-data` runs that command before any call:

```python
Stack((), log_dir, fresh=Fresh(("make", "seed"), cwd="repo://api-service"))
```

`cwd` takes `repo://<member>/<path>`, an absolute path or a path under the book root, and empty is the book root. A repo that shares its stack through `services/shared/` states the `fresh` there once. A book that states none runs one of two ways. When its environment has an `ostler:` host, `--fresh-data` resets the copy the play uses with `ostler env reset` and prints `data: reloaded by resetting the copy <name> in <N>s`. The copy must be yours: another live holder refuses the reset. With neither a `fresh` nor a copy ostler manages, `--fresh-data` refuses to play and prints `data: not reloaded, the book states no way to reload it and runs on no copy ostler manages: state fresh=Fresh(...) on its Stack`.

A host written `ostler:` in an environment is a copy of the stack that `ostler env` runs. The copy is the
runner's to name: `--copy NAME`, else the lease the run holds, else the name the book wrote after `ostler:`,
else `shared`. Write no copy name the book cannot keep for every runner.

A book in the artifacts folder states no `root` on its `Environment`. The environment reads the stack copy of the code checkout the command runs in. `root` is only for a book kept inside its repository, or for pointing a play at another checkout, and a root derived from the book's own `__file__` lies in the artifacts folder and names no code checkout.

`ostler env up` takes the book's name as its `ops/stack.yml` declares it, the folder under
`services/<repo>/` in the artifacts folder, or under `services/` beside the code, such as `api`, and never the module name. A repository's stack root is the book named `<repo>`. One service of a book is
`book:service`. A wrong name is refused with the list of the books that have a stack file.

`search <term>` and `explain <Endpoint|Journey|Action|Event>` answer what the book already says
before you read any source. A search term may be a label in any of the book's languages, a source file or a part
of its path, or several words in any order. It also reaches a decision by its story id, the classes it explains or
the sources it cites, and an open question by its words with `--kind question`. An event's name finds the event, the actions that emit it and the outside events that hear it, across every book under the root; `--kind event` or `--kind outside` keeps one side. While authoring, `explore` against the app always takes `--only`: the full replay is the
gate's job. The seed-only walk needs no app and runs as often as you like.
