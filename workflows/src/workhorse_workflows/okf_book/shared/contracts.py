"""A file's contract: what it does, promises and refuses, each claim citing a symbol the file declares.

Contracts live for one run, under its run directory. Only a contract every citation of which
the file grounds is saved, so a saved contract is one the aggregation turns can build on.
"""
from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ostler.checks import Refusal, parse_check
from ostler.inventory import declared_names_at, declares_at, parse_python

CONTRACTS_DIR = "contracts"


class Claim(BaseModel):
    """One promise or refusal, the symbol it is about, and the check that would observe it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    symbol: str = ""
    verify: str = ""


class Contract(BaseModel):
    """What one repo-relative file is for, and what it promises and refuses its callers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str
    purpose: str
    promises: tuple[Claim, ...]
    refusals: tuple[Claim, ...] = ()

    @property
    def claims(self) -> tuple[Claim, ...]:
        return (*self.promises, *self.refusals)


class ContractReply(BaseModel):
    """A document turn's reply: one contract per file it was given."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contracts: tuple[Contract, ...]


def _is_docstring(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str)


def owes_a_promise(path: Path) -> bool:
    """False for a file that declares nothing and runs nothing, such as a docstring-only module or a manifest."""
    if declared_names_at(path):
        return True
    if path.suffix != ".py":
        return False
    module = parse_python(path.read_text(encoding="utf-8"))
    return module is None or not all(_is_docstring(statement) for statement in module.body)


def _claim_problems(root: Path, file: str, claim: Claim) -> list[str]:
    problems: list[str] = []
    if claim.symbol and not declares_at(root / file, claim.symbol):
        problems.append(f"`{claim.symbol}` is not declared in {file}. Cite a symbol the file itself declares, or leave `symbol` empty when it declares none that carries the claim.")
    if claim.verify:
        parsed = parse_check(claim.verify)
        if isinstance(parsed, Refusal):
            problems.append(f"`{claim.verify}` is not a check: {parsed.message}. The form is {parsed.form}.")
    return problems


def contract_problems(root: Path, contract: Contract) -> tuple[str, ...]:
    """Why the contract cannot be saved: a claim citing an undeclared symbol, a bad check, or no promise from code."""
    problems: list[str] = []
    if not contract.purpose.strip():
        problems.append(f"The contract of {contract.file} does not say what the file is for.")
    if not contract.promises and owes_a_promise(root / contract.file):
        problems.append(f"The contract of {contract.file} promises nothing, but the file runs code. State what a user sees because it runs, and leave `symbol` empty when the file declares none that carries it.")
    for claim in contract.claims:
        problems.extend(_claim_problems(root, contract.file, claim))
    return tuple(problems)


def contract_path(run_dir: Path, file: str) -> Path:
    return run_dir / CONTRACTS_DIR / f"{file}.json"


def save_contract(run_dir: Path, contract: Contract) -> Path:
    path = contract_path(run_dir, contract.file)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_contract(run_dir: Path, file: str) -> Contract | None:
    path = contract_path(run_dir, file)
    return Contract.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def read_contracts(run_dir: Path, files: Iterable[str]) -> tuple[Contract, ...]:
    """The saved contract of each file that has one, in the given order."""
    found = (read_contract(run_dir, file) for file in files)
    return tuple(contract for contract in found if contract is not None)
