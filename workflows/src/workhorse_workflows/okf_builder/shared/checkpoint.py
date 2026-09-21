"""The deterministic convergence gate, run when the drain is dry.

Ported from `base-library/workflows/okf-builder/scripts/checkpoint.py`. Two divergences,
both deliberate:

* **ostler is called as a library, not as a subprocess.** The script shelled out to
  `ostler fmt <features>` and `ostler doctor --json` and parsed the stdout back; here it
  is `run_fmt(okf.graph, [features])` and `okf.doctor()`, which is what the CLI itself
  does one layer down — `ostler/ostler/api.py` is "the *library* face of the `ostler` CLI
  … the CLI merely `json.dumps` what these return". What the subprocess bought was crash
  isolation, and what replaces it is the same `except` arm the script had for a failed
  `subprocess.run`.
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
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Checkpoint, Settled
from workhorse_workflows.okf_builder.shared.worklist import (
    doctor_row,
    reopen_row,
    repair_keys,
    settle_stale_rows,
)

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
    # Whether the two nodes really are one documented thing is a fact about what each one
    # says, not something the finding's own text can settle — mirroring the suggested
    # bullet without reading both sides turns a real divergence into a false `same-as:`.
    "one-way-same-as",
})

#: The drain's spend order, as code families from upstream to downstream. Scope first — a
#: node documenting test source is deleted, so no other repair on it is worth a turn. Then grounding:
#: a claim about a symbol that no longer exists is not worth rephrasing, and a check bound
#: to it observes nothing. Then claim shape (what the book asserts), then obligations (how
#: each assertion is observed), then the UI contract. A code in no family sorts after all
#: of them; errors sort before warns regardless of family, because an error blocks the
#: graph itself. The point is where a *bounded* run's allowance goes — the gate ("no
#: standing finding") is unchanged.
_CODE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"test-subject", "code-cites-test"}),
    frozenset({"missing-code-symbol", "dangling-code-ref", "dangling-link",
               "missing-anchor", "unresolved-relation"}),
    frozenset({"compound-normative-bullet", "overlong-normative-bullet",
               "unminted-claim", "relation-without-subject"}),
    frozenset({"unparsed-check", "misfiled-test-ref", "weak-check",
               "undeclared-obligation", "unstated-precondition"}),
    frozenset({"missing-placement", "malformed-placement", "ambiguous-locator",
               "unnamed-interactive", "unreachable-screen", "no-root-screen"}),
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
    edited — `same-as-disagreement` over a family, `conflicting-surface-driver` over a
    surface. Reading the field rather than the id list in the message is the point: the
    membership is data, and a consumer that had to recover it from a sentence would be
    matching prose that exists to be read by a person.
    """
    related = finding.get("related") or []
    return [str(member) for member in related] if isinstance(related, list) else []


#: A node documenting a test double rather than the product (ostler `test-subject`).
TEST_SUBJECT = "test-subject"

#: Findings only ostler itself ever clears, never an agent turn.
#:
#: `unstamped-citation` is closed by `stamp_turn`/the migration re-stamping the node, and
#: `unreachable-citation` by slice (e)'s provenance checkout mapping — neither is a defect an
#: agent can act on: there is no prose or code change that earns a digest, and "agents never
#: stamp" is load-bearing. Queuing a `fix:` row for one is a turn with no repair it can make,
#: and on a book mid-migration that is thousands of rows. Excluding them here, rather than in
#: `_repair_items` itself, keeps the exclusion in the one place seeding already decides which
#: findings are actionable — `_repair_items`'s own body stays about grouping, not eligibility.
#: `needs-snapshot` and `needs-out-of-band-observation` are compile.py declining a check
#: the book wrote correctly — a before/after pair or an out-of-band read the compiler has
#: no mechanism to take. No repair fragment applies: the fix is not a book edit an agent
#: turn can make, it is building the snapshot/out-of-band capability itself, which is
#: deliberately out of scope for this drain.
#: `needs-target-backend` and `needs-multi-target-runtime` are the same shape one level up:
#: a journey whose steps all share one target this compiler builds no *journey* path for
#: (`cli`), or names a *different* target for each step of one journey, which
#: `@scenario(target=...)` binds one of. Both say the book is already right and the
#: harness is what is missing, so sending them to a repair turn would aim an agent at a
#: correct page and ask it to change something.
#: `unwitnessed-check` belongs to the same family for its own reason: it says `ostler qa
#: sensitivity` could not build a witness observation any check on the claim accepts, so no
#: perturbation was ever tried — a statement about the sensitivity harness's reach, not an
#: obligation the book owes a proof of. `doctor.py` says as much twice, once in the finding's
#: own `suggestion` and once in the `#:` docstring excluding it from `OBLIGATION_CODES`. The
#: one edit that would silence it — a looser pattern the witness synthesizer can satisfy — is
#: the edit that makes `insensitive-check` true of the same claim, so a repair turn aimed here
#: can only make the book worse. It is a `warn` that never blocks: a book can be finished and
#: correct with `unwitnessed-check` standing on it.
NON_ACTIONABLE_CODES = frozenset({
    "unstamped-citation",
    "unreachable-citation",
    "needs-snapshot",
    "needs-out-of-band-observation",
    "needs-target-backend",
    "needs-multi-target-runtime",
    "unwitnessed-check",
})

#: `stale-citation` is a turn's to repair, but never through this path: `coverage.py`'s
#: `_regrounding` join already reads doctor's raw `stale-citation` findings and files them
#: as its own `fix:stale-citation` row, one per drifted file, naming every node that cites
#: it (`stale-citation.md`'s fragment is written for exactly that context shape — `file`,
#: `nodes`, `citations`). Left in `_repair_items`, the same finding would *also* mint a
#: second, node-scoped `fix:stale-citation` row here, whose context (`node`, `path`,
#: `findings`) the same fragment cannot read — two competing rows for one defect, one of
#: them prompting off keys that do not exist. Dropping it from the checkpoint's actionable
#: set (so a book with only `stale-citation` standing still reads as clean) is what lets the
#: book reach `compute_coverage`, where the regrounding join is the one place this code is
#: filed.
REGROUNDING_CODES = frozenset({"stale-citation"})


def _actionable_findings(findings: list[dict]) -> list[dict]:
    """Drop findings no agent turn can act on: test-subject nodes and ostler-only codes.

    The repair for `test-subject` is deleting the node — the whole page when the verdict sits
    on the page's own node — so any other finding on it asks a turn to make a mock provable
    and is undone by the deletion. Queuing them is what spent thousands of turns on legacy
    mock pages; once the node is gone doctor stops reporting them, and `settle_stale` closes
    rows already held for them as stale.

    A page-level verdict (`ref` is `<path>#code`, the file node's id being the bare path)
    covers every node on the page, its own node-level `test-subject` findings included: one
    deletion, one row.

    `NON_ACTIONABLE_CODES` findings are dropped outright rather than by node or page: a file
    can be otherwise sound and still unstamped, so nothing about the node warrants deleting or
    skipping its *other* findings — only the unstamped/unreachable finding itself is not a
    turn's to fix.
    """
    pages = {str(f.get("path", "")) for f in findings
             if f.get("code") == TEST_SUBJECT and f.get("ref") == f"{f.get('path', '')}#code"}
    nodes = {_node_of(str(f.get("ref", "") or ""), str(f.get("path", "")))
             for f in findings if f.get("code") == TEST_SUBJECT}
    kept = []
    for finding in findings:
        if finding.get("code") in NON_ACTIONABLE_CODES or finding.get("code") in REGROUNDING_CODES:
            continue
        path = str(finding.get("path", ""))
        page_verdict = finding.get("code") == TEST_SUBJECT and finding.get("ref") == f"{path}#code"
        if path in pages and not page_verdict:
            continue
        node = _node_of(str(finding.get("ref", "") or ""), path)
        if node in nodes and finding.get("code") != TEST_SUBJECT:
            continue
        kept.append(finding)
    return kept


def _repair_items(findings: list[dict]) -> list[dict[str, Any]]:
    """One item per `(file, node, code)`, chunked, carrying that group's findings only.

    **One remedy per item, because the prompt is chosen from the code.** The kind *is* the
    finding code — `fix:compound-normative-bullet` — so the turn's instructions are knowable
    before it starts, and `main/prompts/repair.md` can dispatch to a fragment written for that
    one defect. An item mixing a dangling link with an unfalsifiable check has no such
    fragment: the only prompt that fits it is the generic one that made both repairs shallow.

    The row is the unit of tracking, not the unit of work: a document with three codes over
    two nodes is six rows, each a single, checkable question with its own attempts, but
    `worklist.select_item` hands every open row on one file to a single turn, and the prompt
    carries one fragment per code in it. What a turn costs is reading the file and its source,
    and that is paid once per file however the rows are keyed.

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
    for finding in _actionable_findings(findings):
        path = str(finding.get("path", ""))
        if _related_of(finding):
            # A group finding is about N book locations and `path` names one of them
            # arbitrarily (doctor picks the lowest-sorting member). Keying it on `path`
            # addressed a member instead of the defect: the item moved when that member did,
            # two unrelated defects that happened to share a first document were batched into
            # one, and — the reason it could never be repaired — the other members were out
            # of the item's declared scope, which the repair prompt's own guardrail then
            # correctly refused to leave.
            #
            # The finding's `ref` is what the defect is *about* — the family root and key,
            # the surface — so it is the identity: stable while the book is edited, and one
            # item per defect.
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


def scoped_findings(report: dict, repo_root: str, features: str) -> list[dict]:
    """Doctor's standing findings located in the service book being built.

    A monorepo's unrelated epic/spec history may already contain doctor findings. Those
    cannot be repaired by a docs/features-only workflow and must not prevent one service
    book converging.

    **Standing means every finding doctor reports, not "error".** Severity is the wrong
    discriminator for a gate whose job is a *complete* book: `undeclared-obligation` and
    `compound-normative-bullet` are warns, and they are the bulk of what makes an existing
    book unprovable — draining errors alone converges on a book whose every claim is still
    unfalsifiable. A finding leaves this gate in the book, not around it: repaired, or
    excused by a `known-defect:` bullet doctor itself honours while the seed it names is
    open — so what doctor reports is exactly what stands.

    On an empty `features` the filter keeps everything: reachable only with no book to
    scope to, which the graph reaches only by failing first, and the one reading the
    checkpoint's own "doctor findings are unscoped" warning describes.
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
        and (not prefix
             or str(finding.get("path", "")) == prefix
             or str(finding.get("path", "")).startswith(prefix + "/"))
    ]


#: How many drained items between two mid-drain settles. A doctor pass over a large book
#: costs a minute or two of wall clock and no agent turn; a stale repair row costs a whole
#: turn. Twenty-five turns of drain against one doctor read keeps the read well under the
#: cost of the first stale row it would have caught.
SETTLE_EVERY = 25


@blueprint.node
def settle_stale(
    logger: logging.Logger,
    worklist_path: str,
    repo_root: str = ".",
    features_root: str = "",
    every: int = SETTLE_EVERY,
) -> Settled:
    """Mid-drain, reconcile the repair rows against doctor: close the open rows it no longer
    reports, and reopen the done rows it still does.

    `record` already settles stale `fix:` rows — but only on the checkpoint's write, and
    the checkpoint only runs when the drain goes dry. On a book queued with hundreds of
    repairs that is hundreds of turns away, and every row whose finding has meanwhile
    stopped firing (a rule retired under the run, a sibling repair that cleared the whole
    node, an autofix) is still handed out and costs a turn to learn there is nothing to do.
    Measured on live worklists before this existed: well over half of the pending repair
    rows were already stale.

    So the drain reads doctor itself, amortized: on first entry (no `settled_done` on the
    worklist yet, which is also every reload and every resume) and then once every `every`
    completed items. Doctor only — no autofix, no fmt: this pass must not rewrite the book
    under an agent turn that may be editing it. The standing set is exactly what the
    checkpoint would queue (`scoped_findings` → `_repair_items`), so a row this pass keeps
    is a row the checkpoint would keep too.

    **Both directions, because the read is the observation and the row is only a claim.** A
    turn closes its row on its own report; whether the finding cleared is known only when
    doctor reads the book again. Closing what stopped firing and leaving standing done rows
    for the checkpoint read the same report half-way: every survivor waited until the drain
    went dry, then cost a second turn on a file the drain had meanwhile repaired for other
    rows — measured on a live worklist, 849 standing findings on done rows across 94 files,
    61 of those files still being drained, 275 batched turns where 219 would do. The reopen
    goes through `reopen_row`, `record`'s own rule, so attempts and blocks are counted
    exactly as the checkpoint would count them — just sooner. Findings doctor marks
    `fixable` are left to the checkpoint: its autofix clears them before its doctor read, and
    this pass must not rewrite the book, so reopening them here would buy a turn for work
    no agent has to do.

    `every=0` makes the pass unconditional — the blocked gate's call, which has to print
    what doctor reports at the moment it asks, not what it reported rounds ago.

    A worklist with no doctor row at all skips the doctor read; a doctor failure is
    reported and the watermark still advances, so a broken doctor costs one warning per
    `every` items rather than a minute per pick.
    """
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    items: list[dict[str, Any]] = [row for row in data.get("items", []) if isinstance(row, dict)]
    done = sum(1 for i in items if i.get("status") == "done")
    pending = sum(1 for i in items if i.get("status") == "pending")
    last = data.get("settled_done")
    # The done count is not monotonic — a checkpoint requeue and an unblock both reopen
    # done rows — so a watermark above it was taken before a reopen and is stale, not
    # a settle `done - last` items in the future.
    due = not isinstance(last, int) or done < last or done - last >= every
    fixable = any(
        i.get("status") in ("pending", "blocked", "done") and doctor_row(i) for i in items
    )
    if not due or not fixable:
        return Settled(pending_count=pending, at_done=done if isinstance(last, int) else 0)

    error = ""
    standing: list[dict[str, Any]] = []
    settled = reopened = 0
    try:
        findings = scoped_findings(Ostler(repo_root).doctor().data, repo_root, features_root)
        standing = _repair_items(findings)
        settled = settle_stale_rows(items, standing, where="mid-drain")
        by_key = {key: i for i in items if doctor_row(i) for key in repair_keys([i])}
        for item in standing:
            row = by_key.get(next(iter(repair_keys([item]))))
            if row is None or row.get("status") != "done":
                continue
            if all(f.get("fixable") for f in json.loads(item["context"])["findings"]):
                continue
            reopened += reopen_row(logger, row, item, repo_root)
    except (OSError, ValueError, RuntimeError) as exc:
        error = str(exc)
        logger.warning("settle skipped — ostler doctor failed: %s", exc)
    # The watermark is the count *after* the close: a settled row is a done row, so a pass
    # that closes more than `every` of them would otherwise be due again on the next pick
    # and spend a second doctor read to find nothing.
    done = sum(1 for i in items if i.get("status") == "done")
    data["items"] = items
    data["settled_done"] = done
    path.write_text(json.dumps(data, indent=2))
    pending = sum(1 for i in items if i.get("status") == "pending")
    logger.info(
        "settle at %d done: %d standing repair item(s), closed %d stale row(s), "
        "reopened %d standing row(s), %d pending",
        done, len(standing), settled, reopened, pending,
    )
    return Settled(
        ran=True, settled=settled, reopened=reopened, standing=len(standing),
        pending_count=pending,
        at_done=done, error=error,
    )


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

    **The gate is: no standing finding.** Not "no errors" — the codes that decide whether
    a book's claims can ever be *observed* (`undeclared-obligation`,
    `compound-normative-bullet`, `weak-check`, `unstated-precondition`) are all warns, so
    an error-only gate converges happily on a book nobody can falsify. A finding leaves
    this gate inside the book: repaired, or excused by a `known-defect:` bullet naming the
    seed that fixes the code, which doctor honours while that seed is open and reports as
    `stale-defect` afterwards.

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
    # A book carrying only NON_ACTIONABLE_CODES findings has nothing left for a turn to
    # repair — `unstamped-citation` in particular fires on every citation a from-scratch
    # book has never run through `stamp_turn`, so gating on the raw list never converges:
    # nothing repairs it, nothing reduces it, and the drain loop parks forever waiting on
    # work it will never queue. `_actionable_findings` is the same filter `_repair_items`
    # already applies to decide what to queue; the gate now agrees with what it queues.
    clean = not _actionable_findings(findings)

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


__all__ = ["GROUNDED_CODES", "MAX_FINDINGS_PER_ITEM", "SETTLE_EVERY", "checkpoint_book",
           "scoped_findings", "settle_stale"]
