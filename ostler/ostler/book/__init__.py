"""A draft of the runtime ostler hands every service book.

A book imports nothing else. It describes one service as an executable model,
the surface that reaches it, and the journeys a user takes through it. This
package runs those journeys against the model and against the real service side
by side, searches the model's state graph, computes the lifecycle matrices and
lists what a state refuses.
"""

from ostler.book.arrange import Arrange
from ostler.book.asked import asked
from ostler.book.backstage import Backstage, CannotArrange
from ostler.book.boundary import Foreign, Needs, Passes, Person, Reaches, View
from ostler.book.browser import Browser, Received, action, answer, refusal, request
from ostler.book.cast import SOLE, Actor
from ostler.book.delivery import Again, Bus, Delivery
from ostler.book.domain import (Action, App, Become, Change, Collection, Create, Delete, Documentation, Entry, Fixture, Heard, Index, MoveToday,
                                Select, Show, State, Total, Transaction, Unique, Update)
from ostler.book.command import STDERR, Command, CommandSurface, Exit, Files, Flag, Lines, Mark, Outside, Positional, Sandbox, Seed, Switch, Watched
from ostler.book.entries import in_order, no_repeat, of_pairs
from ostler.book.environment import Environment
from ostler.book.errors import BookError, Unhealthy
from ostler.book.event import Event
from ostler.book.http import (Answer, ApiKey, Bearer, Bool, Bytes, Client, Endpoint, Enum, Field, Id, Int, Itself, List, Map, Num, Object,
                              OffShape, On, Reference, Str, Token, Undeclared, error_field, problem)
from ostler.book.journey import Check, Given, Journey, Listed, OwnerRefused, Refused, Relates, Same, Seen, Shows, Undo, masked, pluck
from ostler.book.inputs import Diverges
from ostler.book.model import Defect, Model, Rule
from ostler.book.pagedata import handed
from ostler.book.pagesurface import PageSurface
from ostler.book.mobilesurface import MobileSurface
from ostler.book.device import Device
from ostler.book.outcome import CannotReach, Done, Outcome, Refusal, Refusals, Unreachable
from ostler.book.httpsurface import HttpSurface
from ostler.book.rpc import STATUS, GrpcClient, GrpcSurface, Rpc
from ostler.book.screen import Aspect, Component, Condition, Form, Interaction, Is, Phase, Screen, Stored, T, Transition, Viewport, When
from ostler.book.service import Service
from ostler.book.signed import Signed
from ostler.book.stack import Fresh, Process, Stack
from ostler.book.state import Axes, Impossible, Scene
from ostler.book.status import Code, Exited, refused, succeeded
from ostler.book.surface import Surface
from ostler.book.workspace import checkout
from ostler.book.witness import Because, Unseen

__all__ = [
    "Actor", "Again", "Arrange", "Bus", "Delivery", "Backstage", "CannotArrange", "Environment", "SOLE", "in_order", "no_repeat", "of_pairs",
    "checkout", "Browser", "Device", "MobileSurface", "PageSurface", "Received", "action", "answer", "asked", "handed", "refusal", "request",
    "Action", "App", "Become", "Change", "Collection", "Create", "Delete", "Documentation", "Entry", "Event", "Fixture", "Heard", "Index", "MoveToday", "Select",
    "Show", "State", "Total", "Transaction", "Unique", "Update",
    "Answer", "ApiKey", "Axes", "Bearer", "Bool", "BookError", "Unhealthy", "Bytes", "CannotReach", "Check", "Client", "Component", "Defect", "Diverges", "Done",
    "Endpoint", "Enum", "Field", "Foreign", "Form", "Fresh", "Given", "Id", "Impossible", "Int", "Interaction", "Itself", "Journey", "List", "Listed", "Map", "Model", "Object", "OffShape", "Outcome",
    "Needs", "Num", "On", "OwnerRefused", "Passes", "Person", "Phase", "Aspect", "Condition", "Is", "Viewport", "Process", "Reaches", "Reference", "Refusal", "Refusals", "Refused", "Relates", "Rule", "Same", "Scene", "Screen", "Seen", "Service", "Shows", "Stack", "Stored", "Str", "Surface", "Token",
    "Command", "CommandSurface", "Exit", "Files", "Flag", "Lines", "Mark", "Outside", "Positional", "STDERR", "Sandbox", "Seed", "Switch", "Watched",
    "Code", "Exited", "GrpcClient", "GrpcSurface", "HttpSurface", "Rpc", "STATUS", "Signed", "refused", "succeeded",
    "T", "Transition", "Undeclared", "Undo", "Unreachable", "Unseen", "View", "Because", "When", "error_field", "masked", "pluck", "problem",
]
