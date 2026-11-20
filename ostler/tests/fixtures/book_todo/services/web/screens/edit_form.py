"""A row turned into a form. Sends only what changed; Cancel puts the row back."""

from ostler.book import Field as Wire, Phase, Screen, Str, Stored, T, Transition, When, request
from ostler.book.screen import Button, DateField, Field, Select, Spinner, Text, TextArea

from .labels import ASSIGNEE, DESCRIPTION, DUE, SAVE, TITLE
from .list_page import ListPage, ready
from .users import EDIT, RECEIVED

form = Text("edit-form", does="the form element that replaces the row")
title = Field("todo-title", TITLE, takes="title", holds=Wire(Str(max_len=120)))
description = TextArea("todo-description", DESCRIPTION, takes="description",
                       holds=Wire(Str(max_len=2000), required=False, nullable=True))
due = DateField("todo-due", DUE, takes="due_on", holds=Wire(Str(format="date"), required=False))
clear_due = Button("todo-due-clear", T(en="Clear due date", fr="Effacer l'échéance"), "empties the date and marks it cleared")
assignee = Select("todo-assignee", ASSIGNEE, lists=EDIT)
save = Button("todo-save", SAVE, "PATCH /todos/{id} with the changed fields only; a cleared date is null")
cancel = Button("todo-cancel", T(en="Cancel", fr="Annuler"), "the row comes back unchanged")
saving = Spinner("todo-saving")
error = Text("todo-error", does="the API's error text, role=alert")

idle = Phase("idle", hides=(saving, error))
saving_phase = Phase("saving", shows=(saving,), disabled=(title, description, due, clear_due, assignee, save, cancel))
refused = Phase("refused", shows=(error,), because="the fields keep what was typed")


class EditForm(Screen):
    source = ("web/index.html", "web/app.js")
    api = "/todos"
    sends = (request("PUT", "/todos"), RECEIVED)
    name = T(en="Edit todo", fr="Modifier la tâche")
    inside = ListPage
    shown_in = ready
    root = form
    title = title
    description = description
    due = due
    clear_due = clear_due
    assignee = assignee
    save = save
    cancel = cancel
    saving = saving
    error = error

    stored = (
        Stored("title, description, due, assignee", "as the add form, prefilled from the row", "the row's values"),
        Stored("dueCleared", "whether Clear due date was pressed since the last save", "false"),
        Stored("phase", "idle | saving | refused", "idle"),
        Stored("error", "the last refusal's message, or empty", '""'),
    )
    phases = (idle, saving_phase, refused)
    transitions = (
        Transition(idle, When("click", save), saving_phase, only_if="title is not blank and online"),
        Transition(idle, When("click", cancel), idle, then="editingId = null; the row is back"),
        Transition(idle, When("click", clear_due), idle, then="due = empty; dueCleared = true"),
        Transition(saving_phase, When("200"), idle, then="editingId = null; list refetched"),
        Transition(saving_phase, When("4xx or 5xx"), refused, then="error = body.error; fields kept"),
        Transition(refused, When("edit any field"), idle, then="error hidden"),
    )
