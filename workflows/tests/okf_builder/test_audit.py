from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
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
        assert node.retries == 0
        assert not node.add_dirs
        packet = AuditPacket.model_validate_json(ctx.as_dict()["packet"])
        prompt = render(node.prompt, ctx.as_dict(), workflow_dir)
        assert packet.digest in prompt
        self.packets.append(packet)
        self.prompts.append(prompt)
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


def audit_env(tmp_path: Path, agent: AuditAgent) -> RunEnv:
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


def test_sampling_and_unsupported_source_are_explicit_partial_reports(booked: Path, tmp_path: Path) -> None:
    (booked / "acme/a.py").write_text("def _other():\n    return 2\n")
    (booked / "acme/client.ts").write_text("export const x = 1;")
    agent = AuditAgent()
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme", max_packets=1),
                   audit_env(tmp_path, agent))
    assert result.status == "partial"
    assert result.omitted_packets == result.total_packets - 1 > 0
    assert len(agent.packets) == 1
    assert any("client.ts: unsupported" in reason for reason in result.unresolved)
    assert not result.scope_clear


def test_turn_budget_ends_the_pass_with_the_unaudited_packets_listed(booked: Path, tmp_path: Path) -> None:
    (booked / "acme/a.py").write_text("def _other():\n    return 2\n")
    (booked / "acme/b.py").write_text("def _more():\n    return 3\n")
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
    other.write_text(doc.read_text().replace("slug: charge", "slug: unrelated"))
    agent = AuditAgent(status)
    result = drive(Audit(docs_path=str(booked), source_path="acme", service="acme"), audit_env(tmp_path, agent))
    assert result.status == "assessed" and not result.scope_clear
    assert any(repair.target == "docs/features/acme/concepts/charge.md" for repair in result.repairs)
    assert result.selected_claims == 1
    assert len(agent.packets) == 1
    assert all("globex" not in claim.path for claim in agent.packets[0].claims)


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
    assert len(agent.packets) == (1 if change in {"same", "schema_order"} else 2)
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
