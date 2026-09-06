"""Frozen inputs and exact-ID scoring for the controlled behavior audit."""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

from ostler.behavior import AuditPreparation, build_audit_packets, extract_book, extract_evidence
from ostler.model import load
from pydantic import BaseModel, ConfigDict, Field


class Defect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    explanation: str
    claim_suffixes: list[str] = Field(default_factory=list)
    candidate_kind: str = ""
    candidate_line: int = 0


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    defects: list[Defect]


class GroundTruth(BaseModel):
    cases: list[Case]


class Slice(BaseModel):
    id: str
    service: str
    source: str
    symbol: str
    book: str
    heading: str
    context: list[str] = Field(default_factory=list)
    defects: list[Defect]


class BookReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)


class RepairedSlice(Case):
    fixed_defect_ids: list[str] = Field(min_length=1)
    replacements: list[BookReplacement] = Field(min_length=1)


def repaired_truth(root: Path, selection: Slice, repair: RepairedSlice) -> Case:
    """Admit independent post-state truth only for the declared, observed replacement."""
    if repair.id != selection.id or not selection.id.startswith("stablemate-"):
        raise ValueError(f"{selection.id}: repaired truth belongs to another Stablemate slice")
    if set(repair.fixed_defect_ids) != {defect.id for defect in selection.defects}:
        raise ValueError(f"{selection.id}: repaired truth must name exactly the baseline defect IDs")
    if repair.defects:
        raise ValueError(f"{selection.id}: repaired slice must explicitly declare empty defect truth")
    book = (root / selection.book).read_text(encoding="utf-8")
    if book.count(selection.heading + "\n") != 1:
        raise ValueError(f"{selection.id}: expected one designated book section")
    section = book.split(selection.heading + "\n", 1)[1].split("\n### ", 1)[0]
    for replacement in repair.replacements:
        if replacement.before in book or replacement.after not in section:
            raise ValueError(f"{selection.id}: book does not contain the reviewed replacement")
    return Case(id=repair.id, defects=repair.defects)


class CacheTokens(BaseModel):
    read: int = 0
    write: int = 0


class Tokens(BaseModel):
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache: CacheTokens = Field(default_factory=CacheTokens)


class SessionInfo(BaseModel):
    id: str
    cost: float | None = None
    tokens: Tokens


class Transcript(BaseModel):
    info: SessionInfo


class Adjudication(BaseModel):
    """An independent reading bound to the exact reviewed packet, outside prompts."""
    packet_digest: str
    false_positive_repairs: list[str]
    explanation: str


def adjudicate(record: Adjudication, digest: str, unmatched: set[str]) -> dict[str, object]:
    if record.packet_digest != digest:
        raise ValueError("adjudication is stale or belongs to another packet")
    if set(record.false_positive_repairs) != unmatched:
        raise ValueError("adjudication must classify every unmatched adverse ID exactly")
    return record.model_dump(mode="json")


def usage(runs: Path) -> dict[str, object]:
    """Backend-reported usage, deduplicated by session, not a guessed API invoice."""
    sessions = {record.info.id: record.info for path in runs.glob("*/transcripts/*.export.json")
                for record in [Transcript.model_validate_json(path.read_text())]}
    return {
        "sessions": len(sessions),
        "input_tokens": sum(item.tokens.input for item in sessions.values()) if sessions else None,
        "output_tokens": sum(item.tokens.output for item in sessions.values()) if sessions else None,
        "reasoning_tokens": sum(item.tokens.reasoning for item in sessions.values()) if sessions else None,
        "cache_read_tokens": sum(item.tokens.cache.read for item in sessions.values()) if sessions else None,
        "cache_write_tokens": sum(item.tokens.cache.write for item in sessions.values()) if sessions else None,
        "reported_cost_usd": sum(item.cost for item in sessions.values() if item.cost is not None) if sessions else None,
        "estimated_cost_usd": None,
        "cost_note": "Subscription backend reports zero; no authorized unit-price schedule available. Zero is not an API-equivalent estimate.",
        "tokens_note": "Backend categories retained separately; reasoning/cache may overlap other counts.",
    }


def variant_book(book: str, case: str) -> str:
    if case == "control":
        return book
    if case == "omissions":
        return "".join(line for line in book.splitlines(keepends=True)
                       if not line.startswith("- raises:") and "For empty input" not in line)
    if case == "incorrect":
        return book.replace("exactly two", "exactly three").replace(
            "Appends the selected items, in input order, to the supplied sent list.",
            "Replaces the supplied sent list with the selected items in input order.",
        ).replace("status `sent`", "status `queued`")
    raise ValueError(f"unknown case: {case}")


def file_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file() and ".git" not in path.parts}


def exact_score(expected: dict[str, set[str]], adverse: set[str]) -> dict[str, object]:
    """Join validated model verdict IDs, never prose substrings or source tokens."""
    caught = sorted(key for key, targets in expected.items() if targets & adverse)
    aliases = {target for targets in expected.values() for target in targets}
    return {"caught": caught, "missed": sorted(set(expected) - set(caught)),
            "unmatched_adverse": sorted(adverse - aliases)}


def prepare(root: Path, source: str, *, context_paths: Sequence[str] = ()) -> AuditPreparation:
    evidence = extract_evidence(root, [source], context_paths=context_paths)
    failures = [f"{file.path}: {file.status}: {file.message}"
                for file in evidence.context_files if file.status != "parsed"]
    if failures:
        raise ValueError("Support context unavailable: " + "; ".join(failures))
    return build_audit_packets(evidence, extract_book(load(root)))


def bind_truth(case: Case, preparation: AuditPreparation) -> dict[str, set[str]]:
    """Freeze rubric aliases before review. Selectors describe locations, not detections."""
    claims = {claim.id: claim for packet in preparation.packets for claim in packet.claims}
    aliases: dict[str, set[str]] = {}
    for defect in case.defects:
        ids: set[str] = set()
        for suffix in defect.claim_suffixes:
            matched = [key for key in claims if key.endswith(":" + suffix)]
            if len(matched) != 1:
                raise ValueError(f"{defect.id}: ambiguous or absent claim {suffix}: {matched}")
            ids.update(matched)
        if defect.candidate_kind:
            matched = [item.id for item in preparation.inventory.candidates
                       if item.kind == defect.candidate_kind and item.start_line == defect.candidate_line]
            if len(matched) != 1:
                raise ValueError(f"{defect.id}: ambiguous or absent source witness: {matched}")
            ids.update(matched)
        if not ids:
            raise ValueError(f"{defect.id}: empty rubric")
        aliases[defect.id] = ids
    return aliases


def freeze_slice(checkout: Path, destination: Path, selection: Slice) -> dict[str, object]:
    """Keep original paths/line positions and full baselines alongside the review slice.

    AST is used only to bound source context. It never contributes a verdict or score.
    The original module is preserved under baseline/ for independent adjudication.
    """
    original = (checkout / selection.source).read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    matches = [node for node in ast.parse(original).body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == selection.symbol]
    if len(matches) != 1:
        raise ValueError(f"{selection.source}: expected one {selection.symbol}")
    node = matches[0]
    first = min([node.lineno, *[deco.lineno for deco in node.decorator_list]])
    last = node.end_lineno
    assert last is not None
    source = destination / selection.source
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("".join(line if first <= index <= last else "\n"
                              for index, line in enumerate(lines, 1)), encoding="utf-8")
    original_book = (checkout / selection.book).read_text(encoding="utf-8")
    book_lines = original_book.splitlines(keepends=True)
    start = next(index for index, line in enumerate(book_lines) if line.strip() == selection.heading)
    end = next((index for index in range(start + 1, len(book_lines))
                if book_lines[index].startswith("### ")), len(book_lines))
    section = next(index for index in range(start - 1, -1, -1) if book_lines[index].startswith("## "))
    front_end = next(index for index in range(1, len(book_lines)) if book_lines[index].strip() == "---")
    book = destination / selection.book
    book.parent.mkdir(parents=True, exist_ok=True)
    book.write_text("".join(line if index <= front_end + 1 or index == section or start <= index < end
                            else "\n" for index, line in enumerate(book_lines)), encoding="utf-8")
    for relative in selection.context:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkout / relative, target)
    baseline = destination.parent / "baseline"
    for relative in (selection.source, selection.book, *selection.context):
        target = baseline / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkout / relative, target)
    return {"source_lines": [first, last], "book_lines": [start + 1, end],
            "baseline_hashes": file_hashes(baseline), "selection": selection.model_dump()}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
