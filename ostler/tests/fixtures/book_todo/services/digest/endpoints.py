"""The digest's two reads and its one write. None carries an action: the todo API's answer is what each read is judged against, and the todo API's call is what the write must reach."""

from ostler.book import Answer, ApiKey, Bearer, Endpoint, Bool, Field, Int, List, Object, Passes, Reaches, Str

from ..api.endpoints import FindTodos, ReadTodo, RemoveTodo

from .foreign import AS_IS, late_only, one_entry

CREDENTIALS = (Bearer(), ApiKey())
ERROR = Object("Error", error=Field(Str(), does="the reason, as the todo API gave it"))
NO_CREDENTIAL = Answer(401, ERROR, "the todo API accepted no credential")
NOT_FOUND = Answer(404, ERROR, "the todo API has no such todo")

LATE = Object(
    "Late",
    id=Field(Str(), does="the todo's id, as the todo API issued it"),
    label=Field(Str(), does="the todo's title"),
)

DIGEST = Object(
    "Digest",
    late=Field(List(LATE), does="the overdue todos, in the order the todo API listed them"),
    count=Field(Int(), does="how many are late"),
)

ENTRY = Object(
    "Entry",
    id=Field(Str(), does="the todo's id"),
    label=Field(Str(), does="the todo's title"),
    late=Field(Bool(), does="whether the todo is overdue"),
)


class ReadDigest(Endpoint):
    method = "GET"
    path = "/digest"
    auth = CREDENTIALS
    answers = (Answer(200, DIGEST, "the overdue todos"), NO_CREDENTIAL)
    source = ("digest/app.py::digest",)
    does = "Lists the overdue todos the todo API holds."
    carries = None
    passes = Passes(asks=lambda step: FindTodos(), derived=late_only, refused=AS_IS)


class ReadDigestEntry(Endpoint):
    method = "GET"
    path = "/digest/{id}"
    auth = CREDENTIALS
    params = Object(id=Field(Str(), does="the todo's id"))
    answers = (Answer(200, ENTRY, "the todo, and whether it is late"), NOT_FOUND, NO_CREDENTIAL)
    source = ("digest/app.py::entry",)
    does = "Reads one todo and says whether it is late."
    carries = None
    passes = Passes(asks=lambda step: ReadTodo(step.of), derived=one_entry, refused=AS_IS)


class FinishFromDigest(Endpoint):
    method = "POST"
    path = "/digest/{id}/done"
    auth = CREDENTIALS
    params = Object(id=Field(Str(), does="the todo's id"))
    answers = (Answer(204, None, "the todo API finished the todo"), NOT_FOUND, NO_CREDENTIAL)
    source = ("digest/app.py::done",)
    does = "Finishes one todo, which the todo API does by removing it."
    carries = None
    reaches = Reaches(lambda step: RemoveTodo(step.of), refused=AS_IS)
