from __future__ import annotations

import json
from pathlib import Path

import pytest
from ostler.behavior import AuditVerdicts
from workhorse.templates import render
from workhorse_workflows import okf_builder
from workhorse_workflows.okf_builder.shared.audit import AuditScope, preparation


@pytest.mark.parametrize("directions", [
    ("`supported`: all clauses", "consistent with the observed evidence"),
    ("`contradicted`: observed behavior", "incompatible with the claim"),
    ("`partial`: identify a concrete unsupported or incorrect clause",
     "observed counterevidence", "not lack of context"),
    ("Insufficient evidence", "`unresolved`, with no repair"),
    ("complete enclosing source", "side effects", "early guards"),
    ("`missing` only after inspecting", "same-node book context",
     "non-normative signatures and prose", "explicit structural reason"),
    ("prose documents the behavior", "exact document lines", "signature-only coverage",
     "do not invent claims", "book_evidence", "not QA proof"),
])
def test_rendered_audit_requires_evidence_before_repair(
    booked: Path, directions: tuple[str, ...],
) -> None:
    packet = preparation(AuditScope(docs_path=str(booked), source_path="acme")).packets[0]
    packet_json = packet.model_dump_json(indent=2)
    schema = json.dumps(AuditVerdicts.model_json_schema(), indent=2)
    prompt = render(
        "audit/prompts/behavior-audit.md",
        {"packet": packet_json, "feedback": "contract-feedback", "result_schema": schema},
        Path(okf_builder.__file__).parent,
    )
    assert packet_json in prompt
    assert schema in prompt
    assert "contract-feedback" in prompt
    instructions = " ".join(prompt.split("## Packet", 1)[0].split())
    for direction in directions:
        assert direction in instructions
    assert "packet-only assessment" in instructions
    assert "do not use tools" in instructions
    definitions = AuditVerdicts.model_json_schema()["$defs"]
    assert "book_evidence" in definitions["CandidateVerdict"]["properties"]
    assert set(definitions["BookEvidenceRef"]["properties"]) == {"node", "start_line", "end_line"}
