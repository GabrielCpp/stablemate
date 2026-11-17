"""The `ostler book` commands, played on the small book `demo` the sandbox holds under services/demo. The commands that
need a browser, a device, a server or a git checkout of the app are not played."""

from __future__ import annotations

from ostler.book import STDERR, Command, Exit, Lines, Object

from .model import documents as act

ARGS = Object("NoArgs")
OPAQUE = Lines(opaque=("",))
CORE = ("ostler/ostler/book/cli.py", "ostler/ostler/book/index.py", "ostler/ostler/book/model.py", "ostler/ostler/book/state.py",
        "ostler/ostler/book/domain.py", "ostler/ostler/book/command.py", "ostler/ostler/book/http.py", "ostler/ostler/book/journey.py",
        "ostler/ostler/book/tree.py::bind", "ostler/ostler/book/tree.py::fill", "ostler/ostler/book/tree.py::resolved", "ostler/ostler/book/tree.py::repoint",
        "ostler/ostler/book/tree.py::swapped", "ostler/ostler/book/tree.py::_reaches", "ostler/ostler/book/tree.py::unresolved")


class CheckBook(Command):
    does = "Build everything the book declares, with no stack, and name what is broken or stale."
    program = "ostler"
    argv = ("--full-ids", "book", "check", "services.demo")
    args = ARGS
    answers = (Exit(0, Lines(), "the book has no finding"),)
    carries = act.CheckBook
    source = (*CORE, "ostler/ostler/book/__init__.py", "ostler/ostler/book/__main__.py", "ostler/ostler/book/check.py",
              "ostler/ostler/book/matrix.py", "ostler/ostler/book/inputs.py", "ostler/ostler/book/service.py",
              "ostler/ostler/book/sources.py", "ostler/ostler/book/status.py", "ostler/ostler/book/eventmap.py",
              "ostler/ostler/book/questions.py")


class IndexBook(Command):
    does = "Write the service's index.tsv, which search reads without importing the service."
    program = "ostler"
    argv = ("--full-ids", "book", "index", "services.demo")
    args = ARGS
    answers = (Exit(0, Lines(), "the index file's path and whether it changed"),)
    carries = act.IndexBook
    source = (*CORE, "ostler/ostler/book/decisions.py", "ostler/ostler/book/questions.py", "ostler/ostler/book/search.py")


class SearchBook(Command):
    does = "Find a term among the endpoints, rules, actions, journeys, scenes and decisions of the book."
    program = "ostler"
    argv = ("--full-ids", "book", "search", "hello", "--service", "services.demo")
    args = ARGS
    answers = (Exit(0, OPAQUE, "each match with its kind, its place and a line of what it says"),)
    carries = act.Reading
    source = ("ostler/ostler/book/search.py", "ostler/ostler/book/index.py")


class ExplainBook(Command):
    does = "Print everything the book says of one endpoint, action or journey."
    program = "ostler"
    argv = ("--full-ids", "book", "explain", "services.demo", "Echo")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the element, its answers and the action it carries"),)
    carries = act.Reading
    source = ("ostler/ostler/book/cli.py::explain", "ostler/ostler/book/status.py", "ostler/ostler/book/index.py")


class ExplainNothing(Command):
    does = "Refuse to explain a name the book does not hold, and point at search."
    program = "ostler"
    argv = ("--full-ids", "book", "explain", "services.demo", "Nope")
    args = ARGS
    answers = (Exit(1, STDERR, "nothing in the book has the name; the refusal is on standard error"),)
    carries = act.ExplainNothing
    source = ("ostler/ostler/book/cli.py::explain",)


class ListBookDecisions(Command):
    does = "List the decisions the book settled, one line each: the slug, its story and date, and its first line."
    program = "ostler"
    argv = ("--full-ids", "book", "decisions", "services.demo")
    args = ARGS
    answers = (Exit(0, Lines(), "the decisions"),)
    carries = act.ListBookDecisions
    source = ("ostler/ostler/book/decisions.py", "ostler/ostler/book/index.py")


class ExploreBook(Command):
    does = "Walk the model's state graph to depth 4 without an app and report the cells it would play."
    program = "ostler"
    argv = ("--full-ids", "book", "explore", "services.demo", "--seed-only", "--out", "out")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the walk, its signatures per depth and the scenes it never reached"),)
    carries = act.Reading
    source = ("ostler/ostler/book/exploration.py", "ostler/ostler/book/explore.py", "ostler/ostler/book/check.py",
              "ostler/ostler/book/graph.py", "ostler/ostler/book/eventmap.py")


class RunBook(Command):
    does = "Walk every journey on the service's surface against its model, then its cells, input classes and twins."
    program = "ostler"
    argv = ("--full-ids", "book", "run", "services.demo", "--no-stack", "--out", "out")
    args = ARGS
    answers = (Exit(0, OPAQUE, "every journey, cell and class agrees with the app, with the times it took, and a closing verdict block that says green"),)
    carries = act.Reading
    source = ("ostler/ostler/book/runner.py", "ostler/ostler/book/cells.py", "ostler/ostler/book/defects.py",
              "ostler/ostler/book/environment.py", "ostler/ostler/book/httpsurface.py", "ostler/ostler/book/listing.py",
              "ostler/ostler/book/outcome.py", "ostler/ostler/book/owners.py", "ostler/ostler/book/progress.py::__init__", "ostler/ostler/book/progress.py::now", "ostler/ostler/book/progress.py::say", "ostler/ostler/book/progress.py::journey", "ostler/ostler/book/progress.py::phase", "ostler/ostler/book/progress.py::done", "ostler/ostler/book/progress.py::verdict_lines", 
              "ostler/ostler/book/register.py", "ostler/ostler/book/witness.py", "ostler/ostler/qa/__init__.py")


class DrawBook(Command):
    does = "Draw each record's state graph and table from the matrix, as dot and svg."
    program = "ostler"
    argv = ("--full-ids", "book", "graph", "services.demo")
    args = ARGS
    answers = (Exit(0, Lines(), "the two files it wrote under results"),)
    carries = act.DrawBook
    source = ("ostler/ostler/book/graph.py", "ostler/ostler/book/matrix.py")


ALL = (CheckBook, IndexBook, SearchBook, ExplainBook, ExplainNothing, ListBookDecisions, ExploreBook, RunBook, DrawBook)
