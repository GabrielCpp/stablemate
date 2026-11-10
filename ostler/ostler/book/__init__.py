"""A draft of the runtime ostler hands every service book.

A book imports nothing else. It describes one service as an executable model,
the surface that reaches it, and the journeys a user takes through it. This
package runs those journeys against the model and against the real service side
by side, searches the model's state graph, computes the lifecycle matrices and
lists what a state refuses.
"""

from ostler.book.arrange import Arrange
from ostler.book.backstage import Backstage, CannotArrange
from ostler.book.cast import SOLE, Actor
from ostler.book.domain import (Action, App, Become, Change, Collection, Create, Delete, Entry, Fixture, Heard, Index, MoveToday,
                                Select, Show, State, Total, Transaction, Unique, Update)
from ostler.book.environment import Environment
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http import (Answer, ApiKey, Bearer, Bool, Bytes, Client, Endpoint, Enum, Field, Id, Int, List, Map, Num, Object,
                              OffShape, On, Reference, Str, Undeclared, error_field, problem)
from ostler.book.journey import Check, Given, Journey, Listed, Refused, Relates, Same, Seen, Shows, Undo, masked, pluck
from ostler.book.inputs import Diverges
from ostler.book.model import Defect, Model, Rule
from ostler.book.outcome import CannotReach, Done, Outcome, Refusal, Refusals, Unreachable
from ostler.book.httpsurface import HttpSurface
from ostler.book.rpc import STATUS, GrpcClient, GrpcSurface, Rpc
from ostler.book.screen import Component, Interaction, Phase, Screen, Stored, T, Transition, When
from ostler.book.service import Service
from ostler.book.stack import Process, Stack
from ostler.book.state import Axes, Impossible, Scene
from ostler.book.status import Code, refused, succeeded
from ostler.book.surface import Surface
from ostler.book.witness import Because, Unseen

__all__ = [
    "Actor", "Arrange", "Backstage", "CannotArrange", "Environment", "SOLE",
    "Action", "App", "Become", "Change", "Collection", "Create", "Delete", "Entry", "Fixture", "Heard", "Index", "MoveToday", "Select",
    "Show", "State", "Total", "Transaction", "Unique", "Update",
    "Answer", "ApiKey", "Axes", "Bearer", "Bool", "BookError", "Unhealthy", "Bytes", "CannotReach", "Check", "Client", "Component", "Defect", "Diverges", "Done",
    "Endpoint", "Enum", "Field", "Given", "Id", "Impossible", "Int", "Interaction", "Journey", "List", "Listed", "Map", "Model", "Object", "OffShape", "Outcome",
    "Num", "On", "Phase", "Process", "Reference", "Refusal", "Refusals", "Refused", "Relates", "Rule", "Same", "Scene", "Screen", "Seen", "Service", "Shows", "Stack", "Stored", "Str", "Surface",
    "Code", "GrpcClient", "GrpcSurface", "HttpSurface", "Rpc", "STATUS", "refused", "succeeded",
    "T", "Transition", "Undeclared", "Undo", "Unreachable", "Unseen", "Because", "When", "error_field", "masked", "pluck", "problem",
]
