"""The quick-start workflow, whole. Copy this file, rename it, and you have a workflow.

The four things every workflow is made of, once each:

* a **node** — a plain function taking `logger` first, registered on a `Blueprint`;
* a **state** — a public method on a `Workflow` subclass, returning the next one;
* an **agent turn** — a Jinja prompt rendered, run, and validated back into a model;
* a **registry** — the module-level object the `workhorse.workflows` entry point names,
  and whose `main(...)` return value is the `workhorse-hello-world` console script.

Deliberately absent: a repo to clone, a context manifest to load, a sub-flow, a
counter, an `Await`. Those are all in `workhorse/docs/AUTHORING.md`, and every one of
them would make this file worse at the one job it has.
"""
from __future__ import annotations

from logging import Logger

from pydantic import BaseModel

from workhorse.pyflow import Blueprint, Continue, Done, Registry, Workflow

blueprint = Blueprint("hello-world")


class Subject(BaseModel):
    """What the node returns. A node returns a typed model, not a JSON envelope."""

    name: str
    letters: int


class Greeting(BaseModel):
    """What the agent turn must reply with. `returns=` is the contract, and the
    runner validates the reply against it before the state ever sees it."""

    greeting: str


# `stub=` is the author's answer to "what would this have returned", and it is what
# `--dry-run` calls instead of the body. Without one a dry run gets a *blank* model,
# whose fields raise on access — which is fine for a node whose result nothing reads,
# and not fine here, because `start` reads `.letters`.
@blueprint.node(stub=lambda logger, name: Subject(name=name, letters=0))
def measure(logger: Logger, name: str) -> Subject:
    """Ordinary Python, called through `self.call` so it earns a span and an
    `output.json`. The `logger` is injected; the callsite neither passes nor sees it."""
    logger.info("measuring %r", name, extra={"activity": True})
    return Subject(name=name, letters=len(name))


class HelloWorld(Workflow):
    """Two states: measure the subject, then ask an agent to greet it."""

    #: An input — filled from `--params '{"name": "globex"}'`, frozen for the run.
    name: str = "world"

    def start(self) -> Continue:
        subject = self.call(measure, self.name)
        # Whatever a state computes travels in the transition, because the transition
        # is what the checkpoint stores. `self.letters = …` would raise.
        return Continue(subject, self.greet, letters=subject.letters)

    def greet(self, letters: int) -> Done:
        reply = self.agent(
            "prompts/greet.md",
            returns=Greeting,
            args={"name": self.name, "letters": letters},
        )
        self.logger.info("%s", reply.greeting)
        return Done(reply)


#: The name `workhorse run hello-world` resolves, and the run's composition root.
#: `stub_agents` declares what `--dry-run` gets back for `prompts/greet.md`, keyed by
#: the prompt's stem — which is what lets the dry run walk this machine end to end with
#: no agent CLI installed.
workflow = (
    Registry("hello-world")
    .add_blueprints(blueprint)
    .stub_agents({"greet": {"greeting": "Hello from a dry run."}})
)

#: `main(...)` RETURNS the console-script callable; it never calls it, so importing this
#: module stays free — which entry-point discovery depends on.
main = workflow.main(HelloWorld)
