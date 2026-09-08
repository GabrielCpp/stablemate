from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from ostler.behavior import AuditPacket, AuditVerdicts, CandidateVerdict, ClaimVerdict
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.records import parse_checkpoint
from workhorse.runner.failure import BackendInvocationError
from workhorse.templates import render
from workhorse_workflows import okf_builder
from workhorse_workflows.okf_builder.audit.flow import Audit
from workhorse_workflows.okf_builder.shared import audit as audit_nodes
from workhorse_workflows.okf_builder.shared.audit import BehaviorAuditOutcome
from workhorse_workflows.okf_builder.workflow import workflow


def test_standalone_audit_is_registered() -> None:
    """The evaluator must reach the real audit through the public CLI flow table."""
    assert "audit" in workflow.flows


@pytest.mark.parametrize("flow", ["audit", "default"])
def test_cli_dry_run_preflights_and_drives_audit(flow: str, tmp_path: Path) -> None:
    assert run_pyflow(RunInvocation(registry=workflow, flow=flow, runs_dir=tmp_path, dry_run=True)) == 0


class AuditAgent:
    def __init__(self, status: str = "missing") -> None:
        self.status = status
        self.packets: list[AuditPacket] = []
        self.prompts: list[str] = []

    def __call__(self, node: Any, ctx: Any, workflow_dir: Path, *args: Any, **kwargs: Any) -> Any:
        assert Path(node.prompt).stem == "behavior-audit"
        assert node.power == "medium"
        assert node.retries == 1
        assert not node.add_dirs
        packet = AuditPacket.model_validate_json(ctx.as_dict()["packet"])
        prompt = render(node.prompt, ctx.as_dict(), workflow_dir)
        assert packet.digest in prompt
        self.packets.append(packet)
        self.prompts.append(prompt)
        if self.status == "backend_failure":
            # What the ladder re-raises once its bounded retries are spent — the real
            # shape of the failure this node meets on a flaky provider.
            raise BackendInvocationError(f"No result text from opencode for node '{node.id}'")
        if self.status == "invalid_schema":
            return "scripted", {"claims": "not a list"}
        if self.status == "invalid_ids":
            return "scripted", AuditVerdicts(claims=(), candidates=()).model_dump()
        if self.status in {"partial", "contradicted"}:
            return prompt, AuditVerdicts(
                claims=tuple(ClaimVerdict(
                    id=claim.id, status="partial" if self.status == "partial" else "contradicted",
                    candidate_ids=tuple(candidate.id for candidate in packet.candidates),
                    explanation="The behavior differs from the cited claim",
                ) for claim in packet.claims),
                candidates=tuple(CandidateVerdict(
                    id=candidate.id, status="covered" if self.status == "partial" else "missing",
                    explanation="See claim mismatch",
                ) for candidate in packet.candidates),
            ).model_dump(mode="json")
        claims = tuple(ClaimVerdict(id=claim.id, status="unresolved", explanation="Needs more context")
                       for claim in packet.claims)
        candidates = tuple(CandidateVerdict(
            id=candidate.id,
            status="unresolved" if self.status == "unresolved" else "missing",
            explanation="The return value is not described in the book",
        ) for candidate in packet.candidates)
        return prompt, AuditVerdicts(claims=claims, candidates=candidates).model_dump(mode="json")


def audit_env(tmp_path: Path, agent: Callable[..., Any]) -> RunEnv:
    writer = ArtifactWriter("okf-builder", tmp_path / "runs", run_id="audit")
    return RunEnv(writer=writer, config=RunConfig(), workflow_dir=Path(okf_builder.__file__).parent,
                  session_id_path=writer.run_dir / ".session_id", agent_runner=StubRunner(agent))


def test_read_only_audit_reports_missing_behavior_and_persists_receipts(booked: Path, tmp_path: Path) -> None:
    before = {path.relative_to(booked): path.read_bytes() for path in booked.rglob("*")
              if path.is_file()}
    agent = AuditAgent()
    env = audit_env(tmp_path, agent)
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), env)
    assert isinstance(result, BehaviorAuditOutcome)
    assert result.status == "assessed"
    assert not result.scope_clear
    assert result.repairs[0].target == "acme/service.py"
    assert "return amount" in result.repairs[0].context
    assert result.assessed_packets == len(agent.packets) == 1
    saved = BehaviorAuditOutcome.model_validate_json(Path(result.report_path).read_text())
    assert saved == result
    packet_dir = env.run_dir / "behavior-audit" / agent.packets[0].digest
    assert (packet_dir / "packet.json").is_file()
    assert (packet_dir / "raw-1.json").is_file()
    assert (packet_dir / "report.json").is_file()
    after = {path.relative_to(booked): path.read_bytes() for path in booked.rglob("*")
             if path.is_file()}
    assert after == before


def test_uncited_exported_file_is_queued_without_a_packet(booked: Path, tmp_path: Path) -> None:
    (booked / "acme/shipping.py").write_text(
        "def ship(order):\n    return order\n\n\ndef _pack(order):\n    return order\n", encoding="utf-8",
    )
    agent = AuditAgent()
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), audit_env(tmp_path, agent))
    assert isinstance(result, BehaviorAuditOutcome)
    assert result.status == "assessed"
    assert not result.scope_clear
    assert result.undocumented_files == ("acme/shipping.py",)
    assert [packet.group for packet in agent.packets] == ["source_file"]
    assert all(candidate.path == "acme/service.py" for packet in agent.packets for candidate in packet.candidates)
    repair = next(item for item in result.repairs if item.target == "acme/shipping.py")
    assert "Undocumented file acme/shipping.py" in repair.context
    assert "ship (line 2)" in repair.context and "_pack" not in repair.context


@pytest.mark.parametrize("status", ["invalid_ids", "invalid_schema"])
def test_invalid_verdicts_retry_twice_then_checkpoint_await(
    booked: Path, tmp_path: Path, status: str,
) -> None:
    agent = AuditAgent(status)
    env = audit_env(tmp_path, agent)

    def parked(*args: Any, **kwargs: Any) -> None:
        raise InterruptedError("parked")

    with patch.object(driver, "wait_for_answer", parked), pytest.raises(InterruptedError):
        drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), env)
    assert len(agent.packets) == 2
    checkpoint = json.loads((env.run_dir / "checkpoint.json").read_text())
    assert checkpoint["waiting_on"].endswith("behavior-audit-context.md")
    report = BehaviorAuditOutcome.model_validate_json((env.run_dir / "behavior-audit.json").read_text())
    assert not report.scope_clear
    assert report.status == "invalid" and report.error
    assert report.assessed_packets == 0


def test_a_spent_reviewer_turn_is_gated_not_fatal(booked: Path, tmp_path: Path) -> None:
    """The provider giving up is the node's own recorded failure, not the run's death.

    `behavior-audit` runs on a model that returns an empty result on roughly a third of
    fresh sessions. The ladder is bounded here on purpose, so the case that matters is
    what reaches the state once the ladder is spent — and until this test, nothing did:
    the verdict arrived as a `BackendInvocationError`, a name from `workhorse.runner`
    that a workflow may not import, so the `except` below could not name it and the run
    ended on a packet the operator was never shown.
    """
    agent = AuditAgent("backend_failure")
    env = audit_env(tmp_path, agent)

    def parked(*args: Any, **kwargs: Any) -> None:
        raise InterruptedError("parked")

    with patch.object(driver, "wait_for_answer", parked), pytest.raises(InterruptedError):
        drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), env)
    assert len(agent.packets) == 2, "one retry on a fresh packet, then the gate"
    checkpoint = json.loads((env.run_dir / "checkpoint.json").read_text())
    assert checkpoint["waiting_on"].endswith("behavior-audit-context.md")
    report = BehaviorAuditOutcome.model_validate_json((env.run_dir / "behavior-audit.json").read_text())
    assert report.status == "invalid" and "No result text" in (report.error or "")


def test_sampling_and_unsupported_source_are_explicit_partial_reports(booked: Path, tmp_path: Path) -> None:
    # A module-level candidate is tier 1 without being an exported, uncited symbol.
    (booked / "acme/a.py").write_text("LIMIT = 2\nif LIMIT < 0:\n    raise ValueError('no')\n")
    # Ruby has no extractor; TypeScript did not either when this test was written, and
    # the point is a language the audit must *report* rather than silently skip.
    (booked / "acme/client.rb").write_text("X = 1\n")
    agent = AuditAgent()
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme", max_packets=1),
                   audit_env(tmp_path, agent))
    assert result.status == "partial"
    assert result.omitted_packets == result.total_packets - 1 > 0
    assert len(agent.packets) == 1
    assert any("client.rb: unsupported" in reason for reason in result.unresolved)
    assert not result.scope_clear


def test_turn_budget_ends_the_pass_with_the_unaudited_packets_listed(booked: Path, tmp_path: Path) -> None:
    (booked / "acme/a.py").write_text("LIMIT = 2\nif LIMIT < 0:\n    raise ValueError('no')\n")
    (booked / "acme/b.py").write_text("MORE = 3\nif MORE < 0:\n    raise ValueError('no')\n")
    agent = AuditAgent()
    env = audit_env(tmp_path, agent)
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme", turn_budget=1), env)
    assert isinstance(result, BehaviorAuditOutcome)
    assert result.status == "partial"
    assert len(agent.packets) == 1
    assert result.assessed_packets == 1
    assert len(result.unaudited_packets) == result.total_packets - 1 == 2
    assert all(len(entry.split()) >= 2 for entry in result.unaudited_packets), "digest then paths"
    assert any("Turn budget spent: 1 of 1" in note for note in result.limitations)
    assert not result.scope_clear
    # The receipt on disk is the partial one, and a resume under a fresh budget reads on.
    saved = BehaviorAuditOutcome.model_validate_json(Path(result.report_path).read_text())
    assert saved.unaudited_packets == result.unaudited_packets
    resumed = drive(Audit(docs_path=str(booked), source_path="acme", service="acme", turn_budget=0), env)
    assert isinstance(resumed, BehaviorAuditOutcome)
    assert resumed.status == "assessed" and not resumed.unaudited_packets
    assert len(agent.packets) == 3


def test_clear_except_unaudited_names_only_the_budget_shape() -> None:
    def outcome(**fields: object) -> BehaviorAuditOutcome:
        scope = audit_nodes.AuditScope(docs_path="x", source_path="y")
        return BehaviorAuditOutcome.model_validate(
            {"status": "partial", "report_path": "r", "scope_digest": "d", "scope": scope, **fields},
        )

    repair = audit_nodes.AuditRepair(target="t", context="c")
    assert outcome(unaudited_packets=("abc acme/a.py",)).clear_except_unaudited
    assert not outcome().clear_except_unaudited
    assert not outcome(unaudited_packets=("abc",), omitted_packets=1).clear_except_unaudited
    assert not outcome(unaudited_packets=("abc",), unresolved=("u",)).clear_except_unaudited
    assert not outcome(unaudited_packets=("abc",), repairs=(repair,)).clear_except_unaudited


@pytest.mark.parametrize("status", ["partial", "contradicted"])
def test_book_to_source_mismatches_queue_only_the_selected_book(
    booked: Path, tmp_path: Path, status: str,
) -> None:
    doc = booked / "docs/features/acme/concepts/charge.md"
    doc.write_text(doc.read_text() + "\n- consistency: Charge always returns zero.\n")
    other = booked / "docs/features/globex/concepts/unrelated.md"
    other.parent.mkdir(parents=True)
    other.write_text(doc.read_text().replace("slug: charge", "slug: unrelated") + "\n## Effects\n\n- does: Twice.\n")
    agent = AuditAgent(status)
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), audit_env(tmp_path, agent))
    assert result.status == "assessed" and not result.scope_clear
    assert any(repair.target == "docs/features/acme/concepts/charge.md" for repair in result.repairs)
    assert result.selected_claims == 1
    assert len(agent.packets) == 1
    assert all("globex" not in claim.path for claim in agent.packets[0].claims)
    assert not any("globex" in note for note in agent.packets[0].limitations), (
        "a duplicate heading in another service's book is not this audit's limitation")


def test_resume_rebuilds_source_and_claims_before_reusing_receipts(booked: Path, tmp_path: Path) -> None:
    agent = AuditAgent()
    env = audit_env(tmp_path, agent)
    audit = Audit(docs_path=str(booked), source_path="acme", service="acme")
    first = drive(audit, env)
    second = drive(audit, env)
    assert len(agent.packets) == 1
    assert first.scope_digest == second.scope_digest
    (booked / "acme/service.py").write_text("def charge(amount):\n    return amount + 1\n")
    changed = drive(audit, env)
    assert len(agent.packets) == 2
    assert changed.scope_digest != first.scope_digest
    doc = booked / "docs/features/acme/concepts/charge.md"
    doc.write_text(doc.read_text() + "\n- idempotency: Repeating an amount returns the same incremented amount.\n")
    resumed_env = replace(env, writer=ArtifactWriter.resume(env.run_dir))
    checkpoint = parse_checkpoint((env.run_dir / "checkpoint.json").read_text())
    resumed = drive(audit, resumed_env, resume=read_resume(checkpoint))
    assert len(agent.packets) == 3
    assert resumed.scope_digest != changed.scope_digest
    assert agent.packets[-1].claims


def test_memoized_verdicts_cost_no_turn_in_another_run(
    booked: Path, tmp_path: Path,
) -> None:
    """The same bytes under the same contract are judged once, whichever run asks."""
    doc = booked / "docs/features/acme/concepts/charge.md"
    doc.write_text(doc.read_text() + "\n- consistency: Charge always returns zero.\n")
    agent = AuditAgent("contradicted")
    audit = Audit(docs_path=str(booked), source_path="acme", service="acme")
    first = drive(audit, audit_env(tmp_path / "one", agent))
    assert first.memo_hits == 0 and len(agent.packets) == 1
    other = audit_env(tmp_path / "two", agent)
    second = drive(audit, other)
    assert len(agent.packets) == 1, "the second run spent no reviewer turn"
    assert second.status == "assessed" and second.memo_hits == 1 and second.assessed_packets == 1
    assert second.reports[0].verdicts == first.reports[0].verdicts
    packet_dir = other.run_dir / "behavior-audit" / agent.packets[0].digest
    assert (packet_dir / "verdicts.json").is_file() and (packet_dir / "review-contract.json").is_file()
    assert [repair.target for repair in second.repairs] == [repair.target for repair in first.repairs]


def test_a_new_claim_reduces_the_packet_to_what_the_memo_lacks(
    booked: Path, tmp_path: Path,
) -> None:
    """A claim added in another node keeps the first claim's verdict; the reviewer reads the rest."""
    doc = booked / "docs/features/acme/concepts/charge.md"
    doc.write_text(doc.read_text() + "\n- consistency: Charge always returns zero.\n")
    agent = AuditAgent("contradicted")
    audit = Audit(docs_path=str(booked), source_path="acme", service="acme")
    env = audit_env(tmp_path, agent)
    drive(audit, env)
    refund = booked / "docs/features/acme/concepts/refund.md"
    refund.write_text(doc.read_text().replace("slug: charge", "slug: refund").replace("# Charge", "# Refund"))
    second = drive(audit, env)
    assert len(agent.packets) == 2
    reduced = agent.packets[1]
    assert second.selected_claims == 2 and second.memo_partial == 0, "the reduced reply became a whole receipt"
    assert len(reduced.claims) == 1 and "refund" in reduced.claims[0].path
    assert len(reduced.candidates) == 1, "a missed claim keeps every candidate in front of the reviewer"
    assert reduced.omitted_claims == 1
    assert (env.run_dir / "behavior-audit" / reduced.digest / "parent.json").is_file()
    report = second.reports[0]
    assert {claim.status for claim in report.verdicts.claims} == {"contradicted"} and len(report.verdicts.claims) == 2
    assert report.packet_digest != reduced.digest
    third = drive(audit, env)
    assert len(agent.packets) == 2 and third.assessed_packets == 1


def test_support_context_reaches_packets_and_invalidates_receipts(booked: Path, tmp_path: Path) -> None:
    helper = booked / "helper.py"
    helper.write_text("def delegated():\n    return 1\n", encoding="utf-8")
    agent = AuditAgent()
    env = audit_env(tmp_path, agent)
    audit = Audit(docs_path=str(booked), source_path="acme", service="acme",
                  context_paths=("helper.py",))
    first = drive(audit, env)
    assert first.scope.context_paths == ("helper.py",)
    assert "def delegated()" in agent.packets[0].model_dump_json()
    assert all(item.path != "helper.py" for item in agent.packets[0].candidates)
    drive(audit, env)
    assert len(agent.packets) == 1
    helper.write_text("def delegated():\n    return 2\n", encoding="utf-8")
    changed = drive(audit, env)
    assert len(agent.packets) == 2
    assert changed.scope_digest != first.scope_digest
    assert changed.selected_candidates == first.selected_candidates


def test_missing_support_context_is_invalid_without_model_spend(booked: Path, tmp_path: Path) -> None:
    agent = AuditAgent()
    env = audit_env(tmp_path, agent)

    def parked(*args: Any, **kwargs: Any) -> None:
        raise InterruptedError("parked")

    with patch.object(driver, "wait_for_answer", parked), pytest.raises(InterruptedError):
        drive(Audit(docs_path=str(booked), source_path="acme", context_paths=("missing.py",)), env)
    report = BehaviorAuditOutcome.model_validate_json((env.run_dir / "behavior-audit.json").read_text())
    assert report.status == "invalid"
    assert "missing.py" in report.error
    assert not agent.packets


@pytest.mark.parametrize("change", ["same", "prompt", "schema", "schema_order", "legacy", "replaced_reply"])
def test_resume_binds_receipts_to_review_contract(
    booked: Path, tmp_path: Path, change: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = tmp_path / "workflow/audit/prompts/behavior-audit.md"
    prompt.parent.mkdir(parents=True)
    shutil.copyfile(Path(okf_builder.__file__).parent / "audit/prompts/behavior-audit.md", prompt)
    monkeypatch.setattr(audit_nodes, "AUDIT_PROMPT", prompt)
    agent = AuditAgent("unresolved")
    env = replace(audit_env(tmp_path, agent), workflow_dir=prompt.parents[2])
    audit = Audit(docs_path=str(booked), source_path="acme", service="acme")
    first = drive(audit, env)
    assert first.unresolved
    assert first.schema_version == 2
    assert first.review_contract is not None
    assert first.review_contract.prompt_digest == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert first.review_contract.schema_digest == hashlib.sha256(json.dumps(
        AuditVerdicts.model_json_schema(), sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert first.policy_digest == first.review_contract.digest
    packet_dir = env.run_dir / "behavior-audit" / agent.packets[0].digest
    schema = AuditVerdicts.model_json_schema()
    if change == "prompt":
        prompt.write_text(prompt.read_text() + "\nReview signature evidence explicitly.\n")
    elif change == "schema":
        schema["description"] = "An upgraded review output contract"
    elif change == "schema_order":
        schema = dict(reversed(list(schema.items())))
    elif change == "legacy":
        (packet_dir / "review-contract.json").unlink()
    elif change == "replaced_reply":
        receipt = packet_dir / "verdicts.json"
        replacement = AuditVerdicts.model_validate_json(receipt.read_text())
        replacement = replacement.model_copy(update={"candidates": (
            replacement.candidates[0].model_copy(update={"explanation": "A different, still valid reply"}),
            *replacement.candidates[1:],
        )})
        receipt.write_text(replacement.model_dump_json(indent=2))
    with patch.object(AuditVerdicts, "model_json_schema", return_value=schema):
        checkpoint = parse_checkpoint((env.run_dir / "checkpoint.json").read_text())
        resumed = drive(audit, replace(env, writer=ArtifactWriter.resume(env.run_dir)),
                        resume=read_resume(checkpoint))
    # A lost or tampered receipt is rebuilt from the verdict memo; only a new
    # contract sends the packet back to a reviewer.
    assert len(agent.packets) == (2 if change in {"prompt", "schema"} else 1)
    assert resumed.scope_digest == first.scope_digest
    assert all(packet.digest == agent.packets[0].digest for packet in agent.packets)
    assert (packet_dir / "review-contract.json").is_file()
    policy = audit_nodes.ReceiptPolicy.model_validate_json((packet_dir / "review-contract.json").read_text())
    assert policy.contract == resumed.review_contract
    assert policy.verdicts_digest == hashlib.sha256((packet_dir / "verdicts.json").read_bytes()).hexdigest()
    assert (resumed.policy_digest != first.policy_digest) == (change in {"prompt", "schema"})
    if change == "prompt":
        assert "Review signature evidence explicitly." in agent.prompts[-1]
    historical = first.model_dump(exclude={"schema_version", "review_contract", "policy_digest"})
    legacy = BehaviorAuditOutcome.model_validate(historical)
    assert legacy.schema_version == 1 and legacy.review_contract is None and not legacy.policy_digest


@pytest.mark.parametrize("timing", ["before_render", "after_render"])
@pytest.mark.parametrize("change", ["prompt", "schema"])
def test_in_flight_contract_change_never_marks_reply_current(
    booked: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timing: str, change: str,
) -> None:
    prompt = tmp_path / "workflow/audit/prompts/behavior-audit.md"
    prompt.parent.mkdir(parents=True)
    shutil.copyfile(Path(okf_builder.__file__).parent / "audit/prompts/behavior-audit.md", prompt)
    monkeypatch.setattr(audit_nodes, "AUDIT_PROMPT", prompt)
    schema = AuditVerdicts.model_json_schema()
    captured = audit_nodes.review_contract(prompt, audit_nodes.verdict_schema())

    def upgrade() -> None:
        if change == "prompt":
            prompt.write_text(prompt.read_text() + "\nChanged during dispatch.\n")
        else:
            schema["description"] = "Changed during dispatch"
            monkeypatch.setattr(AuditVerdicts, "model_json_schema", lambda: schema)

    class ChangingAgent(AuditAgent):
        def __call__(self, node: Any, ctx: Any, workflow_dir: Path, *args: Any, **kwargs: Any) -> Any:
            if timing == "before_render":
                upgrade()
            reply = super().__call__(node, ctx, workflow_dir, *args, **kwargs)
            if timing == "after_render":
                upgrade()
            return reply

    agent = ChangingAgent()
    env = replace(audit_env(tmp_path, agent), workflow_dir=prompt.parents[2])

    def parked(*args: Any, **kwargs: Any) -> None:
        raise InterruptedError("parked")

    with patch.object(driver, "wait_for_answer", parked), pytest.raises(InterruptedError):
        drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), env)
    assert len(agent.packets) == 1
    packet_dir = env.run_dir / "behavior-audit" / agent.packets[0].digest
    assert (packet_dir / "raw-1.json").is_file()
    assert not (packet_dir / "review-contract.json").exists()
    report = BehaviorAuditOutcome.model_validate_json((env.run_dir / "behavior-audit.json").read_text())
    assert report.status == "invalid" and not report.scope_clear
    assert "review contract changed" in report.error.lower()
    assert report.review_contract == captured
    assert report.review_contract != audit_nodes.review_contract(prompt, audit_nodes.verdict_schema())
    stable_agent = AuditAgent()
    stable = drive(Audit(docs_path=str(booked), source_path="acme", service="acme"),
                   replace(env, agent_runner=StubRunner(stable_agent)))
    assert len(stable_agent.packets) == 1
    assert stable.policy_digest != report.policy_digest
    assert (packet_dir / "raw-2.json").is_file()
    policy = audit_nodes.ReceiptPolicy.model_validate_json((packet_dir / "review-contract.json").read_text())
    assert policy.contract == stable.review_contract


#: `booked` documents one function with one candidate, and a packet of one cannot be
#: short by one. This gives the cited file a branch, so its packet carries two.
BRANCHING_SOURCE = '''"""The billing service."""


def charge(amount):
    """Charge an amount."""
    if amount < 0:
        raise ValueError("negative")
    return amount
'''


class ShortReviewer:
    """A reviewer that omits one candidate verdict, for the first *short_turns* turns.

    This is the real failure the repair rung exists for: the reply carried eighteen sound
    judgements out of nineteen, and `_exact_ids` discarded all eighteen. Which id is
    dropped is deliberately the *first* one, so the reduced packet is not the tail of the
    list and a repair that merely truncated would still be wrong.
    """

    def __init__(self, short_turns: int = 1) -> None:
        self.short_turns = short_turns
        self.packets: list[AuditPacket] = []
        self.feedback: list[str] = []

    def __call__(self, node: Any, ctx: Any, workflow_dir: Path, *args: Any, **kwargs: Any) -> Any:
        packet = AuditPacket.model_validate_json(ctx.as_dict()["packet"])
        self.packets.append(packet)
        self.feedback.append(ctx.as_dict()["feedback"])
        claims = tuple(ClaimVerdict(id=claim.id, status="unresolved", explanation="Needs more context")
                       for claim in packet.claims)
        candidates = tuple(CandidateVerdict(id=candidate.id, status="missing",
                                            explanation="The return value is not described in the book")
                           for candidate in packet.candidates)
        if len(self.packets) <= self.short_turns:
            candidates = candidates[1:]
        return "scripted", AuditVerdicts(claims=claims, candidates=candidates).model_dump(mode="json")


def test_a_dropped_verdict_is_re_asked_on_its_own_not_by_re_asking_the_packet(
    booked: Path, tmp_path: Path,
) -> None:
    """The pass completes on a reply that answered for all but one candidate.

    Before the repair rung this reached an operator gate: the retry handed the reviewer
    the identical packet, and it dropped an id a second time. The proof that this is a
    repair and not a retry is the second packet — it carries only the owed item, and it
    is a different digest from the first.
    """
    (booked / "acme/service.py").write_text(BRANCHING_SOURCE, encoding="utf-8")
    agent = ShortReviewer()
    env = audit_env(tmp_path, agent)
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), env)
    assert isinstance(result, BehaviorAuditOutcome)
    assert result.status == "assessed" and result.assessed_packets == 1
    full, repair = agent.packets
    owed = full.candidates[0].id
    assert [candidate.id for candidate in repair.candidates] == [owed]
    assert repair.digest != full.digest
    assert owed in agent.feedback[1], "the repair turn is told which ids it still owes"
    # The receipt is the full packet's, because that is what the report is owed on.
    receipt = BehaviorAuditOutcome.model_validate_json((env.run_dir / "behavior-audit.json").read_text())
    assert receipt.status == "assessed"
    parent_dir = env.run_dir / "behavior-audit" / full.digest
    assert (parent_dir / "report.json").is_file()
    repair_dir = env.run_dir / "behavior-audit" / repair.digest
    assert (repair_dir / "packet.json").is_file() and (repair_dir / "parent.json").is_file()
    assert (repair_dir / "recall.json").is_file(), "the salvaged verdicts the memo cannot yet hold"


def test_a_repair_that_also_comes_back_short_still_reaches_the_operator_gate(
    booked: Path, tmp_path: Path,
) -> None:
    """One repair per packet, then the budget the reviewer already had.

    A reviewer that keeps dropping ids is not a reply to salvage; it is a reviewer that
    cannot answer this packet, which is exactly what the gate is for. The rung must not
    turn that into an unbounded sequence of ever-smaller packets.
    """
    (booked / "acme/service.py").write_text(BRANCHING_SOURCE, encoding="utf-8")
    agent = ShortReviewer(short_turns=99)
    env = audit_env(tmp_path, agent)

    def parked(*args: Any, **kwargs: Any) -> None:
        raise InterruptedError("parked")

    with patch.object(driver, "wait_for_answer", parked), pytest.raises(InterruptedError):
        drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), env)
    checkpoint = json.loads((env.run_dir / "checkpoint.json").read_text())
    assert checkpoint["waiting_on"].endswith("behavior-audit-context.md")
    report = BehaviorAuditOutcome.model_validate_json((env.run_dir / "behavior-audit.json").read_text())
    assert report.status == "invalid" and report.error
