"""The form above the list. One todo per Save; the fields clear when it lands."""

from ostler.book import Field as Wire, Phase, Screen, Str, Stored, T, Transition, When, request
from ostler.book.screen import Button, DateField, Field, Select, Spinner, Text, TextArea

from .labels import ASSIGNEE, DESCRIPTION, DUE, SAVE, TITLE
from .list_page import ListPage
from .users import FORM, RECEIVED

form = Text("add-form", does="the form element, role=form")
title = Field(None, TITLE, takes="title", holds=Wire(Str(max_len=120)))
description = TextArea("todo-description", DESCRIPTION, takes="description",
                       holds=Wire(Str(max_len=2000), required=False, nullable=True))
due = DateField("todo-due", DUE, takes="due_on", holds=Wire(Str(format="date"), required=False))
assignee = Select(None, ASSIGNEE, lists=FORM)
save = Button(None, SAVE, "POST /todos with the non-empty fields")
saving = Spinner("todo-saving", "the request is out")
error = Text("todo-error", does="the API's error text, role=alert")

idle = Phase("idle", hides=(saving, error), because="Save is enabled only when the title is not blank")
saving_phase = Phase("saving", shows=(saving,), disabled=(title, description, due, assignee, save))
refused = Phase("refused", shows=(error,), because="the fields keep what was typed")


class AddForm(Screen):
    source = ("web/index.html", "web/app.js")
    api = "/todos"
    sends = (request("POST", "/todos"), RECEIVED)
    name = T(en="Add a todo", fr="Ajouter une tâche")
    inside = ListPage
    root = form
    title = title
    description = description
    due = due
    assignee = assignee
    save = save
    saving = saving
    error = error

    stored = (
        Stored("title", "any text; Save needs it non-blank", '""'),
        Stored("description", "any text", '""'),
        Stored("due", "YYYY-MM-DD or empty", '""'),
        Stored("assignee", '"" | "ana" | "bo"', '""'),
        Stored("phase", "idle | saving | refused", "idle"),
        Stored("error", "the last refusal's message, or empty", '""'),
    )
    phases = (idle, saving_phase, refused)
    transitions = (
        Transition(idle, When("click", save), saving_phase, only_if="title is not blank and online"),
        Transition(saving_phase, When("201"), idle, then="fields cleared; list refetched"),
        Transition(saving_phase, When("4xx or 5xx"), refused, then="error = body.error; fields kept"),
        Transition(saving_phase, When("network error"), refused, then="error = a generic message"),
        Transition(refused, When("edit any field"), idle, then="error hidden"),
        Transition(refused, When("click", save), saving_phase, only_if="title is not blank"),
    )
