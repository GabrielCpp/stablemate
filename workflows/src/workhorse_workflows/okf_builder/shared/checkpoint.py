"""The deterministic convergence gate, run when the drain is dry.

Ported from `base-library/workflows/okf-builder/scripts/checkpoint.py`. Two divergences,
both deliberate:

* **ostler is called as a library, not as a subprocess.** The script shelled out to
  `ostler fmt <features>` and `ostler doctor --json` and parsed the stdout back; here it
  is `run_fmt(okf.graph, [features])` and `okf.doctor()`, which is what the CLI itself
  does one layer down — `ostler/ostler/api.py` is "the *library* face of the `ostler` CLI
  … the CLI merely `json.dumps` what these return". This is a *convergence*, not a
  narrowing: `auto-waive.py` already computed the identical scoped finding set through
  `okf.doctor()`, and said in its own docstring that it "mirrors
  checkpoint._doctor_for_features" — so the two nodes disagreed on mechanism while
  claiming to agree on result. What the subprocess bought was crash isolation, and what
  replaces it is the same `except` arm the script had for a failed `subprocess.run`.
* **The graph is reloaded between fmt and doctor.** `run_fmt` writes files, and
  `Ostler.graph` is a cached snapshot whose contract says a mutation invalidates it. The
  subprocess version got this for free by starting a second process; in-process it has to
  be asked for, or doctor reads the book as it was *before* canonicalization.
* **The rename.** The node is `checkpoint_book`, not `checkpoint`, because the state that
  calls it is `checkpoint` and a method body resolves a free name against module globals.
  Both spellings would work; only one is readable.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from ostler import Ostler
from ostler.autofix import run_autofix
from ostler.fmt import run_fmt
from ostler.source_snapshots import write_catalog
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Checkpoint

#: Findings whose remedy cannot be read off the finding: the value has to come from the
#: source. Everything else is mechanical and stays a `fixup`.
GROUNDED_CODES = frozenset({
    "missing-required-bullet",
    "unreachable-screen",
    # A collision is resolved by reading the two controls' real accessible names off the
    # running app or the source — renaming one to silence the check invents a label the UI
    # does not have.
    "ambiguous-locator",
    "unnamed-interactive",
    # Splitting one overlong bullet into several needs the source to say which clauses are
    # actually separate requirements; cutting it on punctuation invents obligations.
    "overlong-normative-bullet",
    # A placement band has to be measured on the running UI. Guessing one either invents a
    # constraint the product never had, or picks a band so wide it can never go red.
    "missing-placement",
    # Whether a stray claim belongs under a normative key or in prose is a fact about what
    # the code does — filed from the finding text alone it becomes an obligation nobody
    # read the source for, or prose that buries a real requirement.
    "unminted-claim",
    # The subject is the record, event or lock the code actually touches; naming one off
    # the bullet's own wording just restates the vagueness the finding is about.
    "relation-without-subject",
    # The cited symbol moved or was renamed; where it went is in the source (or the source
    # inventory), and re-aiming the citation without reading it points the node at a
    # neighbour that happens to exist.
    "missing-code-symbol",
    # Whether a competition is settled is a fact about the cited code — a deprecation
    # annotation, a migrated call site. A selection rule written without reading it is a
    # ranking nobody made; an unsettled competition is recorded, not resolved by invention.
    "competing-implementations",
    # The successor is whatever the deprecation evidence in the source actually names;
    # filling `prefers:` from the finding text alone invents a winner.
    "deprecation-without-successor",
    # The citation is the record that settled the decision — a decision doc, a stated
    # convention, an acceptance criterion. A link invented to clear the finding decorates
    # a gap; with nothing real to cite, the bullet is deleted, not decorated.
    "ungrounded-unspecified",
    # Whether the braces are a repeat missing its declaration or decoration to flatten is
    # a fact about the rendering code — deleting the holes to clear the finding writes a
    # literal name the UI never renders.
    "template-outside-repeat",
})

#: The drain's spend order, as code families from upstream to downstream. Grounding first:
#: a claim about a symbol that no longer exists is not worth rephrasing, and a check bound
#: to it observes nothing. Then claim shape (what the book asserts), then obligations (how
#: each assertion is observed), then the UI contract. A code in no family sorts after all
#: of them; errors sort before warns regardless of family, because an error blocks the
#: graph itself. The point is where a *bounded* run's allowance goes — the gate ("no
#: standing non-waived finding") is unchanged.
_CODE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"missing-code-symbol", "dangling-code-ref", "dangling-link",
               "missing-anchor", "unresolved-relation"}),
    frozenset({"compound-normative-bullet", "overlong-normative-bullet",
               "unminted-claim", "relation-without-subject"}),
    frozenset({"unparsed-check", "weak-check", "undeclared-obligation",
               "unstated-precondition"}),
    frozenset({"missing-placement", "malformed-placement", "ambiguous-locator",
               "unnamed-interactive", "unreachable-screen", "no-entry-point"}),
)


def _family_rank(code: str) -> int:
    return next((n for n, family in enumerate(_CODE_FAMILIES) if code in family),
                len(_CODE_FAMILIES))


#: How many findings one repair item may carry. A doc's findings overwhelmingly share a
#: cause — the same component file, the same route module — so batching them is both
#: cheaper and *better* work: the agent reads the source once and fixes everything it
#: explains. The cap exists because that stops being true past a point, where a huge item
#: invites a shallow pass over its tail.
MAX_FINDINGS_PER_ITEM = 25


def _node_of(ref: str, path: str) -> str:
    """The node a finding sits on, out of a doctor `ref` — `<path>#<node>[#<member>]`.

    The member matters to the finding and not to the grouping: `…#field-accounttype#semantics`
    and `…#field-accounttype#verify` are two questions about one node, and a turn that opens
    the node answers both. So the ref is cut after its *node* segment, not at its first `#` —
    which was a real defect while it lasted, because `<path>#…` means the first segment is the
    path and every finding in a document collapsed into one item regardless of node.

    Two refs do not have that shape and fall back to the path: a file-level finding with no
    ref, and a code-symbol ref (`acme/service.py::refund`) that names source rather than book.
    Both are honest groupings — the item is then "this file, this code".

    A document's *file* node has the bare path as its id, so its findings ref `<path>#<member>`
    and this reads the member as the node. That over-splits — two members of one file node
    become two items — which is the safe direction: an item still carries one code over one
    place, and no finding is dropped.
    """
    if not ref.startswith(path + "#"):
        return path
    return f"{path}#{ref[len(path) + 1 :].split('#')[0]}"


def _related_of(finding: dict) -> list[str]:
    """The book locations a *group* finding is about beyond its own `path` — or `[]`.

    Doctor stamps `related` on a finding whose remedy is only complete when every member is
    edited (`competing-implementations` today). Reading the field rather than the id list in
    the message is the point: the membership is data, and a consumer that had to recover it
    from a sentence would be matching prose that exists to be read by a person.
    """
    related = finding.get("related") or []
    return [str(member) for member in related] if isinstance(related, list) else []


def _repair_items(findings: list[dict]) -> list[dict[str, Any]]:
    """One item per `(file, node, code)`, chunked, carrying that group's findings only.

    **One remedy per item, because the prompt is chosen from the code.** The kind *is* the
    finding code — `fix:compound-normative-bullet` — so the turn's instructions are knowable
    before it starts, and `main/prompts/repair.md` can dispatch to a fragment written for that
    one defect. An item mixing a dangling link with an unfalsifiable check has no such
    fragment: the only prompt that fits it is the generic one that made both repairs shallow.

    Grouping by *node* as well as file is the price of that. An earlier version grouped by
    file alone so a component with a hundred findings was one reading rather than a hundred
    turns; here the file stays in the key (so a node's findings never scatter across
    documents) but a document with three codes over two nodes is six items. What that buys
    back is that each of the six is a single, checkable question.

    Findings stay sorted by line so an agent works top-down, and each chunk is bounded by
    `MAX_FINDINGS_PER_ITEM` — a node with forty compound bullets is two items.

    **The target names the work, not the round that found it.** A survivor is re-queued by
    `requeue`, which reopens the row `record` already holds, so the same defect is the same
    row across every round and its `attempts` accumulate on it. The round used to be in the
    target instead — `r3:<path>#<node>#<code>` — which did re-queue the survivor, but by
    minting an identity `record`'s `(kind, target)` dedupe could not recognise: one new row
    per unrepairable finding per round, forever, and no counter that could ever notice. That
    is what let the fixup loop run nineteen rounds on sixteen findings it was not fixing.

    **The item order is the drain order.** `select_item` hands out the first pending item,
    so the sort here decides where a budget-capped run's allowance is spent: errors before
    warns, then by `_CODE_FAMILIES` (grounding → claim shape → obligations → UI), then
    alphabetically for stability. On a drifted book with thousands of findings, a run that
    stops early has then fixed the dead citations before the prose polish, not whichever
    codes sort first in the alphabet.

    `GROUNDED_CODES` no longer picks the item kind (the code does); it rides in the context
    as `grounded`, which is the repair prompt's cue to demand a value read out of the source
    rather than derived from the finding text.
    """
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for finding in findings:
        path = str(finding.get("path", ""))
        if _related_of(finding):
            # A group finding is about N book locations and `path` names one of them
            # arbitrarily (doctor's `competing-implementations` picks the lowest-sorting
            # member). Keying it on `path` addressed a member instead of the defect: the
            # item moved when that member did, two unrelated competitions that happened to
            # share a first document were batched into one, and — the reason it could never
            # be repaired — the other members were out of the item's declared scope, which
            # the repair prompt's own guardrail then correctly refused to leave.
            #
            # The citation is what the competition is *about*, so it is the identity: stable
            # while the book is edited, and one item per competition.
            #
            # The path slot is left empty for the same reason: it would put the arbitrary
            # member back into the item's identity. The paths the turn must open come out of
            # `related`, which names all of them.
            code = str(finding.get("code", ""))
            groups.setdefault(("", str(finding.get("ref", "") or ""), code),
                              []).append(finding)
            continue
        node = _node_of(str(finding.get("ref", "") or ""), path)
        groups.setdefault((path, node, str(finding.get("code", ""))), []).append(finding)

    items: list[dict[str, Any]] = []
    ordered = sorted(
        groups.items(),
        key=lambda kv: (
            0 if any(f.get("severity") == "error" for f in kv[1]) else 1,
            _family_rank(kv[0][2]),
            kv[0],
        ),
    )
    for (path, node, code), group in ordered:
        group.sort(key=lambda f: (f.get("line", 0), str(f.get("ref", ""))))
        chunks = [group[i:i + MAX_FINDINGS_PER_ITEM]
                  for i in range(0, len(group), MAX_FINDINGS_PER_ITEM)]
        for n, chunk in enumerate(chunks, start=1):
            # The suffix only appears when a group actually split, so the common target
            # stays readable — and two chunks remain distinct worklist entries.
            suffix = f"#{n}" if len(chunks) > 1 else ""
            related = sorted({member for finding in chunk
                              for member in _related_of(finding)})
            context: dict[str, Any] = {"code": code}
            if related:
                # `related` is the item's scope, and `paths` is that scope as files — the
                # repair prompt's "one node" guardrail admits exactly this enumerated set,
                # so a remedy spanning several documents is in scope without the turn
                # touring the book. There is no `path`/`node` here on purpose: either one
                # would name an arbitrary member as *the* place to open, which is the read
                # that made this class unrepairable.
                context["citation"] = node
                context["related"] = related
                context["paths"] = sorted({member.split("#")[0] for member in related})
            else:
                context["node"] = node
                context["path"] = path
            context["grounded"] = code in GROUNDED_CODES
            context["findings"] = chunk
            items.append({
                "kind": f"fix:{code}",
                "target": f"{path}#{node}#{code}{suffix}" if path else f"{node}#{code}{suffix}",
                "context": json.dumps(context, indent=2),
                # A finding still standing after its repair is the *same* work, so it reopens
                # its own row rather than opening a second one.
                "requeue": True,
            })
    return items


def _signature(findings: list[dict]) -> str:
    """A stable fingerprint of a finding SET, order-independent.

    Keyed on `(code, path, ref)` — the identity of a finding, not its prose (a reworded
    message must not read as a different finding) and not its *position*. `line` was in the
    key and had to come out: a repair landing anywhere renumbers every finding below it in
    the file, so an untouched set fingerprinted differently every round and the stall this
    signature exists to detect could not be detected. Empty findings → `""` so a clean round
    can never match a prior dirty signature.

    This stays the coarse whole-book signal it was written as — it moves when *any* finding
    in the book moves. What bounds a single stubborn repair is the per-target `attempts`
    counter `record` keeps, not this.
    """
    if not findings:
        return ""
    keys = sorted(
        (str(f.get("code", "")), str(f.get("path", "")), str(f.get("ref", "")))
        for f in findings
    )
    return hashlib.sha1(json.dumps(keys).encode()).hexdigest()[:16]


def scoped_findings(report: dict, repo_root: str, features: str, *,
                    errors_only: bool = False) -> list[dict]:
    """Doctor's standing findings located in the service book being built.

    A monorepo's unrelated epic/spec history may already contain doctor findings. Those
    cannot be repaired by a docs/features-only workflow and must not prevent one service
    book converging.

    **Standing means not waived, not "error".** Severity is the wrong discriminator for a
    gate whose job is a *complete* book: `undeclared-obligation` and
    `compound-normative-bullet` are warns, and they are the bulk of what makes an existing
    book unprovable — draining errors alone converges on a book whose every claim is still
    unfalsifiable. Waiving demotes a finding to `warn` *and* stamps `waived: true`
    (`doctor._apply_waivers`), so reading the stamp rather than the severity leaves the
    waivers file as the one and only way a finding leaves this gate — with its reason
    recorded in the book.

    `errors_only=True` is for `nodes/waivers.py` alone, which mints one backlog IOU per
    standing finding: widening *that* would file thousands of IOUs for prose warns.

    Shared with `nodes/waivers.py`, which needs the identical set — in the YAML it was
    *copied* into `auto-waive.py` under a comment saying it mirrored this one, and the two
    copies had already drifted: on an empty `features` the checkpoint's version scoped to
    whatever `Path("").resolve()` came out as (the process's cwd) and kept almost nothing,
    while auto-waive's `if not prefix` kept everything. Unified on auto-waive's reading,
    which is the one the checkpoint's own "doctor findings are unscoped" warning describes.
    Reachable only with no book to scope to, which the graph reaches only by failing first.
    """
    try:
        prefix = Path(features).resolve().relative_to(
            Path(repo_root).resolve()
        ).as_posix().rstrip("/") if features else ""
    except ValueError:
        prefix = Path(features).as_posix().rstrip("/")
    return [
        finding for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and (finding.get("severity") == "error" if errors_only
             else not finding.get("waived"))
        and (not prefix
             or str(finding.get("path", "")) == prefix
             or str(finding.get("path", "")).startswith(prefix + "/"))
    ]


def scoped_error_findings(report: dict, repo_root: str, features: str) -> list[dict]:
    """The error-only view of `scoped_findings`, kept for the one caller that needs it."""
    return scoped_findings(report, repo_root, features, errors_only=True)


def _watermark(logger: logging.Logger, okf: Ostler) -> None:
    """Record what every cited symbol currently *is*, so the next run can tell what moved.

    Written on a clean round and only on a clean round. The watermark's whole meaning is
    "a node was written against these bytes"; taking it while doctor still has findings
    would stamp symbols nobody re-read as current, and the drift it exists to detect would
    be erased by the run that failed to document it.

    A failure here is logged and dropped. The catalog is an accelerator — its absence
    makes the next `ostler backfill plan` do more work, never wrong work — and a book that
    converged must not be reported as a failed round because a cache could not be written.
    """
    try:
        path = write_catalog(okf.graph, ())
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning("could not write the source watermark: %s", exc)
        return
    logger.info("watermarked the cited source at %s", path)


@blueprint.node(stub=stubs.clean)
def checkpoint_book(
    logger: logging.Logger,
    repo_root: str = ".",
    features_root: str = "",
    prev_round: int = 0,
    prev_signature: str = "",
    prev_stall: int = 0,
) -> Checkpoint:
    """Canonicalize the book, then read doctor, then queue the repairs it names.

    Auto-formats (`ostler fmt`) then runs `ostler doctor`, turning a dirty doctor into
    worklist items the drain loop repairs before re-converging. Orphan / stub / coverage
    detection is left to the recheck agent (it needs to read code and walk `ostler trace`);
    this node owns only the deterministic part.

    **The gate is: no standing finding that is not explicitly waived.** Not "no errors" —
    the codes that decide whether a book's claims can ever be *observed*
    (`undeclared-obligation`, `compound-normative-bullet`, `weak-check`,
    `unstated-precondition`) are all warns, so an error-only gate converges happily on a
    book nobody can falsify. A finding leaves this gate one way, through the waivers file,
    which is the spelling that leaves the reason behind.

    **One item per node and code.** An earlier version packed every finding into a single
    item whose context was the last 4000 characters of the findings JSON — so on a book with
    more than a dozen findings the rest were dropped silently, and the loop churned without
    ever seeing them. Truncation that looks like completion is the failure this gate exists
    to prevent. Per file fixed that; per `(file, node, code)` is what makes the *repair*
    specialisable, because an item that can only ever carry one defect has a prompt that can
    be written for it. See `_repair_items`.

    **The kind is the code, and grounding is a flag.** A dangling link or a mis-ordered
    bullet is mechanical: the finding names its own remedy. A *missing required bullet* is
    not — the profile evolves, and every book authored before a bullet became required is
    retroactively behind, with no way to derive the value from the finding text. Those carry
    `grounded: true` in their context, and the repair prompt demands the value be read out
    of source. Treated as mechanical they would be "fixed" by writing an empty or `none`
    stub, which satisfies the linter while asserting something nobody checked.

    **Stall detection.** The drain-then-recheck loop assumes each fixup round *reduces* the
    findings — but a defect whose only real fix is a code change (two controls that
    genuinely co-render with the same accessible name) survives its doc-repair and doctor
    re-flags the identical set every round. That is an infinite loop the transition budget
    never catches, because each round still marks its fixup item done. So this node
    fingerprints the finding set and reports how many consecutive rounds it has recurred
    *unchanged* (`stall_rounds`); the workflow bounds the loop on that, not on the raw
    round count — which legitimately climbs on a big book that takes many *productive*
    fixup rounds to converge.
    """
    rnd = prev_round + 1
    okf = Ostler(repo_root)
    if features_root:
        try:
            # Autofix first: a mechanical drift repair must never cost an agent turn, and
            # fmt then sorts whatever autofix moved into canonical position. Both are
            # idempotent shape rewrites, so on a clean or from-scratch book this is a no-op.
            fixed = run_autofix(okf.graph, [features_root])
            if fixed.changed:
                logger.info("autofixed %d drifted file(s) under %s", len(fixed.changed), features_root)
            result = run_fmt(okf.graph, [features_root])
            if result.changed:
                logger.info("canonicalized %d file(s) under %s", len(result.changed), features_root)
        except (OSError, ValueError, RuntimeError) as exc:
            # The subprocess version swallowed a failed `ostler fmt` too: doctor is the
            # gate, and an un-canonicalized book fails it loudly rather than quietly.
            logger.warning("ostler fmt failed for %s: %s", features_root, exc)
        # fmt writes; the cached snapshot is now the book as it was *before* it did.
        okf.reload()
    else:
        # No book to canonicalize: doctor still runs, but its findings can't be scoped to
        # a service, so every unrelated error in the repo lands on this round.
        logger.warning("no features root given — skipping ostler fmt; doctor findings are unscoped")

    try:
        findings = scoped_findings(okf.doctor().data, repo_root, features_root)
        out = json.dumps(findings, indent=2)
    except (OSError, ValueError, RuntimeError) as exc:
        findings = [{"severity": "error", "message": str(exc), "path": features_root}]
        out = str(exc)
    clean = not findings

    signature = _signature(findings)
    if clean:
        stall = 0
    elif signature and signature == prev_signature:
        # The identical finding set as last round: a repair that cannot land (a
        # code-fix-only defect re-flagged unchanged). Count it so the workflow can bound
        # the loop.
        stall = prev_stall + 1
    else:
        # Findings changed — something was repaired or discovered. Real progress; reset.
        stall = 0

    fixups: list[dict[str, Any]] = []
    backfills = 0
    if clean:
        logger.info(
            "round %d: doctor is clean for %s — the gate converges", rnd, features_root or repo_root
        )
        _watermark(logger, okf)
    else:
        fixups = _repair_items(findings)
        backfills = sum(1 for i in fixups
                        if str(i["kind"]).removeprefix("fix:") in GROUNDED_CODES)
        errors = sum(1 for f in findings if f.get("severity") == "error")
        logger.info(
            "round %d: doctor reports %d finding(s): %d error, %d warn across %d item(s) "
            "in %s — queuing %d backfill + %d fixup item(s)%s",
            rnd, len(findings), errors, len(findings) - errors, len(fixups),
            features_root or repo_root, backfills, len(fixups) - backfills,
            f" [stall {stall}: same findings as last round]" if stall else "",
        )
    return Checkpoint(
        checkpoint_clean=clean,
        doctor_output=out[-4000:],
        round=rnd,
        fixup_items=fixups,
        backfill_count=backfills,
        fixup_signature=signature,
        stall_rounds=stall,
    )


__all__ = ["GROUNDED_CODES", "MAX_FINDINGS_PER_ITEM", "checkpoint_book",
           "scoped_error_findings", "scoped_findings"]
