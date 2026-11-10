"""The /todos endpoints. Each class is the whole contract of one endpoint and
has no method of its own: `send` comes from ostler and does what is declared.
`carries` names the model action the call carries; the state runs it."""

from ostler.book import Answer, ApiKey, Bearer, Endpoint, Enum, Field, Id, List, Object, Str

from .shapes import ERROR, TODO, TODO_INPUT
from ..model import actions
from ..model.todo import STATUSES, USERS, TodoRecord

CREDENTIALS = (Bearer(), ApiKey())
NO_CREDENTIAL = Answer(401, ERROR, "no accepted credential")
STORE_DOWN = Answer(503, ERROR, "the store is down; nothing was written or read",
                    why="The app cannot tell a saved todo from a lost one while the store is away, so it answers nothing rather than something false.")
NOT_FOUND = Answer(404, ERROR, "no todo has this id, or it was removed")
MAIN = "app.py::"
BY_ID = Object(id=Field(Id(TodoRecord), does="the todo's id"))


class AddTodo(Endpoint):
    method = "POST"
    path = "/todos"
    auth = CREDENTIALS
    body = TODO_INPUT
    answers = (
        Answer(201, TODO, "created; the id and the derived status come back", creates="id"),
        Answer(400, ERROR, "a field rule is broken: the first one, in field order"),
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    source = (MAIN + "create_todo", MAIN + "parse_fields", MAIN + "todos_handler")
    does = "Creates one todo; the service assigns its id. Two identical posts make two todos."
    carries = actions.AddTodo


class ReadTodo(Endpoint):
    method = "GET"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = BY_ID
    answers = (Answer(200, TODO, "the todo, with its status as of the service's today"), NOT_FOUND, NO_CREDENTIAL, STORE_DOWN)
    source = (MAIN + "todos_handler", MAIN + "find", MAIN + "view")
    does = "Reads one todo."
    carries = actions.ReadTodo


class UpdateTodo(Endpoint):
    method = "PUT"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = BY_ID
    body = TODO_INPUT
    answers = (
        Answer(200, TODO, "the todo after the change"),
        Answer(400, ERROR, "a field rule is broken; nothing changed"),
        NOT_FOUND,
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    source = (MAIN + "put_todo", MAIN + "parse_fields", MAIN + "todos_handler")
    does = "Replaces the whole todo with the body sent; a field left out is cleared."
    carries = actions.ReplaceTodo


class RemoveTodo(Endpoint):
    method = "DELETE"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = BY_ID
    answers = (Answer(204, None, "removed; the id never resolves again"), NOT_FOUND, NO_CREDENTIAL, STORE_DOWN)
    source = (MAIN + "todos_handler", MAIN + "find")
    does = "Removes one todo."
    carries = actions.RemoveTodo


class FindTodos(Endpoint):
    method = "GET"
    path = "/todos"
    auth = CREDENTIALS
    query = Object(
        text=Field(Str(), required=False, does="matches title or description, case folded"),
        assignee=Field(Enum(USERS), required=False, does="an unknown assignee matches nothing"),
        status=Field(Enum(STATUSES), required=False),
    )
    answers = (
        Answer(200, List(TODO), "the matches: overdue soonest first, then scheduled soonest first, then unscheduled newest first"),
        Answer(400, ERROR, "status is not one of the three"),
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    source = (MAIN + "list_todos", MAIN + "order", MAIN + "todos_handler")
    does = "Lists todos, all of them or the ones matching every filter sent."
    carries = actions.FindTodos
