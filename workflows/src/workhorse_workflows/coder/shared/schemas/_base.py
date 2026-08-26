"""The base every agent reply and node return in this workflow derives from.

**Who produces a status decides whether it defaults.** The two kinds of status this
workflow carries fail in opposite directions, so they are typed in opposite ways:

* **An agent produces it** — the field is a *required* `Literal` over the closed set of
  arms. The model is told the arms (the prompt renders the schema), so a reply that omits
  one or invents one is a parse failure, and the runner answers a parse failure with a
  retry turn. That is the right answer: a turn allowed to get away with not saying what
  it did buys a silent arm somewhere downstream. An agent is never allowed to fail its
  own contract by staying quiet.
* **Python produces it** — the field is a `Literal` *with* a default, and the default is
  the pessimistic arm. After the resilience ladder's last rung a node that could not be
  answered emits its declared output keys as `null` and the run advances
  (`workhorse/docs/GUARDRAILS.md`, "Default to the next node"); the default is what that
  node falls back to, and it has to be the arm that does not pass a gate nobody ran.

A third kind stays an open `str`: a field whose values come from the *repo's* config — a
gate name, a suite id, a tool label — has no closed set to write down here.

`extra="ignore"` and `_drop_nulls` are what make the second bullet work: unknown keys are
ignored and nulls are dropped, so a missing answer falls back to the field's own default
instead of raising. On a required agent status there is no default to fall back to, which
is precisely how the parse retry gets triggered.

That is also why `blocked` is *derived* rather than a field of its own. A dead node emits
nulls, `_drop_nulls` drops them, and every Python-produced field falls back to its
default; if "hand this to the operator" were a defaulted field it would fire on every
node the ladder failed to answer, and "pessimistic" would silently become "blocked".
Read off `status` instead, an unanswered Python node is whatever pessimistic arm it
declared — not blocked, and still on the conservative arm it was already taking.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

#: The four spellings the coder workflow grew for one thing: this node cannot finish, and
#: something outside it has to decide. They were four because each schema declared its own
#: free-form `status` and nothing shared a vocabulary — `blocked` in dev and docs,
#: `unfixable` in the QA fix loop, `not_passed` at the QA gate, `invalid` for a plan or an
#: evidence packet. Nothing downstream ever distinguished them.
#:
#: The statuses are `Literal`s now, so each of these four spellings is a declared arm of
#: some model rather than a string that might turn up. Membership stays the derivation
#: because it is a *union* across models: `blocked` has to answer for every schema in the
#: tree, and the type checker cannot join arms that no single class declares together.
#: What the Literals buy is that the set is now closed on the producing side too — a fifth
#: spelling cannot arrive without someone adding an arm here.
#:
#: A *deterministic* validator returning `invalid` is not what this is about. `PlanValidation`
#: and the evidence scaffold are ports, not agents; their verdicts are already evidence and
#: already have a repair loop pointed at them, and their arms stay as they are. This set is
#: what an **agent** says when it has run out of road — the report that used to be dropped.
BLOCKED_STATUSES = frozenset({"blocked", "unfixable", "not_passed", "invalid"})


class _Result(BaseModel):
    """Extra keys ignored, nulls dropped. The two rules the module docstring explains."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class Finding(_Result):
    """One defect with somewhere to go: where it is, and what has to change there.

    This is the shape `QaFinding` already had — `target`, `issue`, `repair` — lifted to the
    base so the other lanes can be held to it. It is the whole of the evidence test: a
    result carrying at least one finding with **both** a target and a repair is a fix
    demand and routes back to whoever can act on it; a result carrying none goes to the
    operator, however much prose it came with.

    The test is mechanical because the router cannot read. A non-empty list of complaints
    reads as evidence and is not: seven `apply-qa-fixes` laps acted on one without ever
    converging, and five of those laps reported `passed` while the gate they were repairing
    had never passed.
    """

    #: Where the defect is — a repo-relative path, a `path:line`, or a spec/AC id. Any of
    #: those is somewhere a fixer can go; prose describing a feeling is not.
    target: str = ""
    #: What is wrong there.
    issue: str = ""
    #: What has to change. Without this a finding names a problem and nominates nobody,
    #: which is the shape that bills a repair budget and buys nothing.
    repair: str = ""

    @property
    def actionable(self) -> bool:
        """Both halves present. See the class docstring for why both are required."""
        return bool(self.target.strip() and self.repair.strip())


class CoderResult(_Result):
    """Base for every agent reply and node return in the coder workflow."""

    @property
    def blocked(self) -> bool:
        """This node cannot finish and something outside it has to decide.

        Derived from `status` rather than declared, so a schema without one is never
        blocked, and a Python-produced status falling back to its pessimistic default is
        not blocked either — see the module docstring. An agent-produced status has no
        default to fall back to, so this answers a `blocked` the agent actually said.
        """
        return str(getattr(self, "status", "")).strip().lower() in BLOCKED_STATUSES

    @property
    def actionable(self) -> list[Finding]:
        """The findings a fixer could actually act on — possibly none.

        Empty is the answer that sends a block to the operator instead of round the loop
        again, so it is deliberately not the same question as "did the agent complain".

        `findings` is read off the subclass rather than declared here, because the schemas
        that have one narrow its element type — `QaAssessment` and `QaAudit` carry
        `list[QaFinding]`. A field declared on this base would make each of those an
        incompatible override (a `list` is invariant), which buys a type error in exchange
        for nothing this property cannot do by asking.
        """
        found = getattr(self, "findings", [])
        return [f for f in found if isinstance(f, Finding) and f.actionable]


__all__ = ["BLOCKED_STATUSES", "CoderResult", "Finding"]
