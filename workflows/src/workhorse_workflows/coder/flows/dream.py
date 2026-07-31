"""The dream as a state machine — the port of `coder/workflow.yaml`'s `flows.dream`
(4 nodes, lines 4036-4083).

It runs *after* the build work, like sleep, and never inline in the per-story pipeline, so
it cannot slow or gate a story. It consolidates a whole run's **process** record — loops,
stalls, retries, from `events.jsonl` and the per-node transcripts — into layered
improvement proposals, drained into a durable deduplicated ledger a human reviews::

    gather evidence → reflect → record

Four nodes become three states, and the fourth was the terminal. Nothing here branches, so
nothing collapsed: this is the one flow in the coder port that is the same shape in both
engines, which makes it the cheapest parity check available.

The loop closes at human review, not at auto-mutation. The dream never edits the workflow
it reflected on.

Divergences from the YAML, all deliberate:

* `run_digest` is handed to the reflection turn as **JSON**. The YAML rendered
  `{{ run_digest }}` into the prompt, which stringifies a mapping as a Python repr —
  single-quoted keys, `True`/`None` — while the prompt asks the turn to read it as JSON.
  It parsed anyway often enough to look fine; this makes it actually so.
* `gather_run_evidence` echoes back the run directory it resolved, and every node after it
  reads that rather than the input var. The YAML did the same thing by declaring
  `run_dir` as an output key and letting it overwrite the input var — a mechanism that
  only exists because a YAML var is one global slot. Here it is a field on a model.
* the agent node has no `default:`, and its reply is not branched on either: what
  reflection produces goes to disk, in the inbox `record` drains. The model's `""`
  defaults are what an empty turn leaves behind.
* the `run_dir` var is the field `reflect_on`, **aliased back to `run_dir`**. `Workflow`
  is a pydantic model and `run_dir` is already a property on it — the engine's own run
  directory — so declaring an input by that name shadows it. The alias is what keeps
  `--params '{"run_dir": ""}'` working unchanged, which is the invocation the YAML
  documents; `populate_by_name` is what keeps a **resume** working, because the
  checkpoint records inputs by field name and re-instantiates from them. That the
  driver reserves `ctx`, `logger`, `run_dir` and `run_id` as input names is recorded in
  the progress ledger — it is the first name collision the port has hit, and it is a
  documentation gap rather than a driver defect.
"""
from __future__ import annotations

import json

from typing import ClassVar

from pydantic import ConfigDict, Field
from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.coder import paths
from workhorse_workflows.coder.nodes.dream import gather_run_evidence, record_improvements
from workhorse_workflows.coder.schemas.dream import ReflectionResult


class Dream(Workflow):
    """One finished run's process record, digested and drained into the ledger."""

    #: `populate_by_name` is not cosmetic: the checkpoint records inputs as
    #: `wf.model_dump(mode="json")`, i.e. by FIELD name, and a resume re-instantiates from
    #: that mapping. Alias-only population would accept the operator's `--params` and then
    #: refuse its own checkpoint.
    model_config = ConfigDict(populate_by_name=True)

    #: The coder run to reflect on. Empty resolves to the newest non-dream run under the
    #: docs root, which is the normal invocation — reflection follows the run it reads.
    #: Named `reflect_on` and aliased to the YAML's `run_dir`; see the module docstring.
    reflect_on: str = Field(default="", alias="run_dir")
    #: The docs repo root the run and the ledger live under. Empty walks up from
    #: `repo_dir`, then the working directory.
    docs_path: str = ""
    #: An optional focus for the reflection turn. Not read by either script node.
    epic: str = ""

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def start(self) -> Continue:
        """Digest `events.jsonl` (and every nested `_flow`) into the signals that matter.

        Deterministic, and deliberately so: it grounds the reflection in what the run
        actually did rather than in what a model remembers of it.
        """
        evidence = self.call(gather_run_evidence, self.reflect_on, self.docs_path)
        return Continue(evidence, self.reflect)

    def reflect(self) -> Continue:
        """Turn the digest and the per-node transcripts into layered proposals.

        A state of its own because it is the expensive step, and because the inbox it
        writes is on disk — a resume that re-ran it would append a second round of
        proposals for the same run. `power: low`: the digest has already done the
        measuring, and the turn is reading it rather than re-deriving it.
        """
        evidence = self.output(gather_run_evidence)
        result = self.agent(
            "prompts/dream-reflect.md",
            returns=ReflectionResult,
            power="low",
            args={
                "run_dir": evidence.run_dir,
                "epic": self.epic,
                "run_digest": json.dumps(evidence.digest, indent=2, sort_keys=True),
            },
        )
        return Continue(result, self.record)

    def record(self) -> Done:
        """Drain the inbox into the durable ledger, deduping and bumping counts.

        This is what makes the reflection real: a proposal observed across many runs is
        the signal the ledger exists to produce, so a repeat bumps a count rather than
        landing as a second entry.
        """
        evidence = self.output(gather_run_evidence)
        return Done(self.call(record_improvements, self.docs_path, evidence.run_dir))


__all__ = ["Dream"]
