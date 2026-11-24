# A command-line tool

Reached from [../SKILL.md](../SKILL.md) when the service is a program a person types, not a server.
A command is declared like an endpoint and played with the same journeys, cells, input classes, twins,
witness and report. The worked example is stablemate's own farrier book, which lives in its author's artifacts folder.

## Declare a command

```python
class Install(Command):
    does = "Render the selected skills into the repository."
    program = "farrier"
    argv = ("install", Flag("--repo", "repo"), Flag("--library", "library"))
    args = Object("InstallArgs", repo=Field(Str(), required=False), library=Field(Str(), required=False))
    answers = (Exit(0, Lines(opaque=("Wired ",)), "files written"), Exit(1, STDERR, "no config"))
    carries = RunInstall
    source = ("farrier/farrier/cli.py::_run_install",)
```

A step is `Install(InstallArgs(repo="."))`, a fixture whose fields are the `args` names. Leave a flag out by
leaving its field None.

## The argv template

A plain string is a word sent as written. The other tokens read an argument by name.

| Token | Sends |
| --- | --- |
| `Flag("--repo", "repo")` | `--repo value` when set. A list repeats the flag once per item. `fmt="dir={}"` shapes the value. |
| `Switch("--force", "force")` | `--force` when the field is true. |
| `Positional("name")` | the value as a word of its own. |
| `stdin = "field"` | that field is sent on stdin and is not in the template. |

Every argument must be read by a token, and every token must name a declared argument, or the class is refused.
A field named `id` typed `Str` is flagged by check; name it `name`.

## Exits

`Exit(code, shape, means)` is one answer. Zero is a success and any other code a refusal.

| Shape | Reads |
| --- | --- |
| `Lines()` | stdout, one string per line. `opaque=(prefix, ...)` leaves out lines that start so. |
| `STDERR` | stderr, as the refusal message. |
| an `Object` or `List` | stdout parsed as JSON. |
| `None` | no stdout. |

A refusal's message is stderr for `STDERR`, or the stdout lines joined with a newline for `Lines`. A rule quotes
it word for word with `status=Exited(1)`. stderr of a success is not compared. An exit the declaration does not
list is `Undeclared`, and a stdout off its shape is `OffShape`.

The model answers with `Transaction(*changes, says=(line, ...))`: the changes to the files, and the lines the
command prints. A rule can read `{field}` of the fixture, so a property on the fixture can build a path.

## The sandbox and the watch

`CommandSurface(Seed(files, git=False, name=...), environment)` makes a fresh directory per world from the seed.
Text may name `<sandbox>`, which is the directory. The program runs there with only the environment the book
declares plus `PATH`. No network, no timer, no timeout. The surface writes the sandbox path back as `<sandbox>` in
everything the program printed, so a message built from a path is the same text in every world. Name the
directory (`name="acme"`) when the program reads it.

A `Files` read lists the watched paths: `marks = (Mark("agents.yml", "claude: true"), ...)`. A row is the path and
which of the declared strings the file holds, in the order declared. The model keeps the same rows in a
`Collection`, and `Select`s them. This is how a file the command writes, or must leave alone, is judged. Put the
read in `Service.watch` and give it a column in a matrix.

The model's row is one subclass of `Watched` that names `marks` and `source`. A book never writes its own record
fields, `declared` or `holding`. Make a row with `FileRecord.holding(path, *strings)`. It keeps the strings in
the order the marks list them.

```python
class FileRecord(Watched):
    marks = MARKS
    source = ("acme/outputs.py::write_text",)

row = FileRecord.holding("agents.yml", "claude: true")
```

Something a person does between commands is an `Outside` subclass with `happen(sandbox)` and a carried action.

## Input classes and twins

They apply to the fields of `args` as to a body. The wire is typed, so the classes `wrong type` and `null` are
not played, and `out of enum` is. A class of `Str(classes={"label": value})` is valid: the model answers it with a
rule. A required field gets `blank` and `missing`. A flag whose absence changes the tool's source of truth, such
as a library found on the machine, is declared optional and always sent, with a decision file saying why.

## Settle behaviour the pages leave out

Read the tool's source for it, write a `decisions/*.md` file citing the file and line, and list each place the
pages and the tool disagree in `DISAGREEMENTS.md` beside the book.
