"""The bodies the API sends and accepts, each declared once."""

from ostler.book import Bool, Enum, Field, Id, Object, Str

from ..model.todo import STATUSES, USERS, TodoRecord

TODO = Object(
    "Todo",
    id=Field(Id(TodoRecord), does="assigned by the service, a UUID"),
    title=Field(Str(max_len=120)),
    description=Field(Str(max_len=2000), nullable=True),
    due_on=Field(Str(format="date"), nullable=True),
    assignee=Field(Enum(USERS), nullable=True),
    status=Field(Enum(STATUSES), does="read off due_on against the service's today"),
    created_at=Field(Str(format="date-time"), opaque="the service stamps its own clock and the model keeps no time of day"),
)

TODO_INPUT = Object(
    "TodoInput",
    title=Field(Str(max_len=120), does="blank is refused"),
    description=Field(Str(max_len=2000), required=False, nullable=True, does="absent or null clears"),
    due_on=Field(Str(format="date"), required=False, nullable=True,
                 does="today or later; on an update the stored day may stay as it is; absent or null clears"),
    assignee=Field(Enum(USERS), required=False, nullable=True, does="absent or null clears"),
)

ERROR = Object("Error", error=Field(Str(), does="the reason, as a user reads it"))

CLOCK = Object("Clock", today=Field(Str(format="date")))

STORE = Object("Store", down=Field(Bool()))
