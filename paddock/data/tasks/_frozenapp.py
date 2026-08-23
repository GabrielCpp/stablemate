"""The frozen-app trial machinery: materialize a story, seed a defect, score the round.

Moved out of the retired replay harness rather than rewritten. Everything here was already
paid for in blood — the pre-image commit that makes a story's diff uncommitted, the
`stories`-at-the-root ignore rule, `$PWD` alignment, the three routes that count as a
catch, the `–` that is not a zero — and a re-implementation would have re-earned each of
those the same way. What changed is only the frame around it: the tree comes from a
paddock seed, the fan-out lives in one task's steps, and the evidence a trial leaves
behind is copied into the result so the score can be recomputed from the sealed zip.

The leading underscore keeps `paddock.loader` from treating this as a task module: it is
the library each frozen-app task module imports, not a second declaration.

Nothing here names an app. `policy-desk` and `seat-booking` are the same fixture wearing
different code — one answer-key schema, one story-image layout, one evidence map — so the
app is an argument (`app: Path`) everywhere it appears, and a task module is the round and
the paths, not a second copy of this.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
import _forensics as fx
from _stablemate import TrialError, effective, git, no_leaks, pin_held, stablemate_checkout, uv_run
from paddock import Run, Score

# ── the app tree ──────────────────────────────────────────────────────────────────────

#: The answer key and the story images sit inside the app tree and are not the app. They
#: are matched at the app *root* only: `shutil.ignore_patterns` matches a basename at any
#: depth, and `stories` is also what an epic calls its story folders — which silently
#: removed every story.md from the trial and left the run with nothing to plan against.
NOT_THE_APP = ("stories", "defects", "defects.yml")

#: What the QA flow *writes*, and therefore what a trial must remove before running it.
#: The flow's own `clear_qa_evidence` already drops `qa/` and `qa-evidence.json`, so those
#: are belt-and-braces; the plan files are the load-bearing ones, because a plan left on
#: disk is a plan the flow would repair instead of author — a different loop from the one
#: being measured.
#:
#: The list is explicit rather than a `qa*` prefix sweep, and has to stay that way: a
#: frozen app keeps its own harness beside the spec — policy-desk's `qa_plan.py` — and a
#: prefix rule would delete the fixture along with the evidence.
#:
#: `qa-okf-context.{json,md}` are deliberately absent: the qa flow's own
#: `build_qa_okf_context` node rebuilds them at entry, so a stale copy is overwritten
#: rather than believed.
QA_OUTPUTS = (
    "qa-plan.yml", "qa-plan.md", "qa.md", "qa-evidence.json",
    "qa-okf-verification-index.json", "qa",
    # Not a contract name — a file the QA agent invented for itself on expense-split's
    # balance-settlement story, and therefore one a fixed list only learns about by
    # finding it still sitting in the spec dir after a rewind. It is a smoke run's proof,
    # which is exactly the thing the trial is measuring the flow on producing.
    "qa-smoke-proof.txt",
)

#: The label a trial with nothing seeded in it carries.
CLEAN = "clean"


#: The three lists a story manifest may carry. A path belongs to exactly one of them.
DIFF_KINDS = ("changed", "added", "pinned")


def story_diff(app: Path, story: str) -> dict[str, list[str]]:
    """The `changed:`/`added:`/`pinned:` manifest for one story, validated against the tree.

    `changed:` and `added:` are the story's implementation diff — what `HEAD..WORKTREE` holds
    once the trial is materialized. `pinned:` is the third kind: a path the trial needs at a
    *story-specific* image on **both** sides of HEAD, so it is present and current in the
    worktree and contributes no line to the diff. The per-story book is the case that forced
    it: a book authored against the finished app cites symbols an earlier story has not
    written, and the trimmed copy that fixes it is not a change the story makes, it is the
    state the story is read against. One image, at `stories/<story>/pinned/<rel>`, written
    before the before-commit and never touched after — identical in HEAD and the worktree by
    construction rather than by a test that compares two copies.
    """
    manifest = app / "stories" / story / "diff.yml"
    if not manifest.is_file():
        known = ", ".join(sorted(p.name for p in (app / "stories").glob("*"))) or "none"
        raise TrialError(f"no diff manifest at {manifest} (stories: {known})")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    diff = {kind: [str(rel) for rel in data.get(kind) or []] for kind in DIFF_KINDS}
    seen: dict[str, str] = {}
    for kind in DIFF_KINDS:
        for rel in diff[kind]:
            if rel in seen:
                raise TrialError(
                    f"{manifest}: {rel} is listed under both {seen[rel]}: and {kind}: — "
                    "a path is exactly one of changed, added or pinned"
                )
            seen[rel] = kind
    return diff


def story_image(app: Path, story: str, rel: str, *, phase: str) -> Path:
    """Where the `pre`/`post` content of one path for one story lives.

    `post/` is optional and the fallback is the app tree, because the app tree IS the last
    story's post-image — that is what keeps it the single thing a reader checks the book
    against. `pre/` has no fallback: a `changed:` path with no pre-image would be committed
    at its final content, and the story's diff would silently come out empty.
    """
    image = app / "stories" / story / phase / rel
    if image.is_file():
        return image
    if phase == "pre":
        raise TrialError(f"story {story!r} lists {rel} as changed but has no pre/ image at {image}")
    if phase == "pinned":
        # No fallback either: the app tree is the *finished* image, and a pinned path exists
        # precisely because the finished image is wrong for this story.
        raise TrialError(f"story {story!r} pins {rel} but has no pinned/ image at {image}")
    return app / rel


def materialize(
    app: Path, story: str, dest: Path, install: Callable[[Path], None] | None = None
) -> Path:
    """Build, at `dest`, the git state a QA run for `story` is supposed to face.

    The coder's QA lane mints its obligations from *uncommitted* changes
    (`build_okf_context(..., base="HEAD", head="WORKTREE", ...)`), so a plain copy of a
    finished app obligates nothing at all and the run has nothing to prove. Hence:

      1. copy the app tree, minus the answer key;
      2. commit a *before* tree — each `changed:` path replaced by its `pre/` image, each
         `added:` path deleted, each `pinned:` path replaced by its `pinned/` image;
      3. restore this story's `changed:`/`added:` files into the worktree, uncommitted, from
         `post/` where that exists and from the app tree otherwise. A pinned path is not
         touched again: committed once, it is identical in HEAD and the worktree.

    `HEAD..WORKTREE` is then exactly this story's implementation diff, while the book, the
    specs and every other story's code sit at their authored state.

    *install* — `farrier install`, when the caller has one — runs between the git init and
    the before-commit, and that ordering is load-bearing rather than tidy. Run afterwards,
    the layer farrier generates (skill scripts, the hooks) sits untracked in the worktree,
    lands in `HEAD..WORKTREE` alongside the story's diff, and the QA lane mints obligations
    for half a dozen files nobody wrote — which every trial then spends a `repair-qa-context`
    lap discovering it cannot own. Committed with the before tree, the generated layer is
    part of the state the story is implemented *against*, which is what it actually is.
    """
    diff = story_diff(app, story)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def ignore(directory: str, names: list[str]) -> set[str]:
        top = NOT_THE_APP if Path(directory) == app else ()
        return {name for name in names if name in top or name in ("__pycache__", ".git")}

    shutil.copytree(app, dest, ignore=ignore)

    # The finished content this story is responsible for, held aside while the before tree
    # is committed.
    after = {
        rel: story_image(app, story, rel, phase="post").read_bytes()
        for rel in [*diff["changed"], *diff["added"]]
    }
    for rel in diff["added"]:
        (dest / rel).unlink(missing_ok=True)
    for rel in diff["changed"]:
        (dest / rel).write_bytes(story_image(app, story, rel, phase="pre").read_bytes())
    for rel in diff["pinned"]:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(story_image(app, story, rel, phase="pinned").read_bytes())

    git("init", "--quiet", "--initial-branch", "main", cwd=dest)
    # Identity on the repo rather than the machine: a trial must not depend on whether the
    # host has a global git config, and must not write to it either.
    git("config", "user.email", "benchmark@example.com", cwd=dest)
    git("config", "user.name", "stablemate benchmark", cwd=dest)
    if install is not None:
        install(dest)
    git("add", "--all", cwd=dest)
    git("commit", "--quiet", "-m", f"before {story}", cwd=dest)

    for rel, body in after.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

    # A rewind belongs here rather than in the seed: the seed is the app as tracked, and
    # the state `run qa` is entered in is the app minus this story's plan and evidence.
    spec = dest / "docs" / "specs" / story
    if not spec.is_dir():
        raise TrialError(f"no spec dir {spec} — is the seed the app tree it should be?")
    for name in QA_OUTPUTS:
        target = spec / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    return dest


def reset_stack_state(dest: Path) -> None:
    """Drop the trial's compose volumes, once, before the run starts.

    The app's `runbook` node deliberately does not do this in its service step: a bring-up
    happens at the head of every plan lane, so a `down -v` there can land in the middle of a
    story proving a record survives a restart, and empty the ledger under it. Here there is
    no run in flight yet, which makes this the one safe moment to reset.

    Every trial shares one compose project name (farrier ties the trial directory's basename
    to its generated skills, so the directory cannot be named after the defect), which is
    exactly why the previous trial's volume is still there to drop.
    """
    if not (dest / "compose.yml").is_file():
        return
    subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "down", "-v", "--remove-orphans"],
        cwd=str(dest), capture_output=True, text=True, check=False,
    )


# ── the answer key ────────────────────────────────────────────────────────────────────


#: The routes a row's `caught_by` may name. `run` is a declared check the plan runs failing
#: (or the defect being repaired); `audit` is the auditor reading the evidence against the
#: clause when no assertion fails. The route is load-bearing in `classify`: an `audit` row
#: on a configuration that never turns the auditor on is `inconclusive`, not a miss.
CATCH_ROUTES = frozenset({"run", "audit"})

#: Every trial runs the QA lane to its *first verdict* — one plan, one suite run, no repair
#: loop — which is what makes a seeded defect's first red comparable across rounds. Under it
#: the lane never enters `audit`, so `audit_result` is empty for every trial and a row whose
#: only route is the auditor cannot be scored by this configuration. Recorded per trial as
#: `audit_turn` so a re-score of an old ledger knows which configuration wrote it.
FIRST_VERDICT = True


def load_defects(app: Path) -> list[dict[str, str]]:
    path = app / "defects.yml"
    if not path.is_file():
        raise TrialError(f"no answer key at {path} — the round can be run but not scored")
    rows = list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("defects") or [])
    if not rows:
        raise TrialError(f"{path} lists no defects")
    for row in rows:
        route = str(row.setdefault("caught_by", "run"))
        if route not in CATCH_ROUTES:
            raise TrialError(
                f"{path}: defect {row.get('id')!r} has caught_by: {route!r}; "
                f"the routes are {', '.join(sorted(CATCH_ROUTES))}"
            )
    return rows


def validate_defects(app: Path) -> list[str]:
    """Every way an answer-key row can be wrong *without* failing a trial, named at once.

    A defect whose `path` is outside its story's `diff.yml` is the silent one: `seed_defect`
    overwrites it all the same, but the path is committed as part of the *before* tree, so
    nothing in the run under measurement is asked about it — the defect is real, present
    and out of scope, and the row scores as a miss against QA for a fixture bug. Worse,
    the overwrite adds a path to `HEAD..WORKTREE` the control trial never had, so the two
    are no longer the same measurement. A row naming an unknown story or a variant that
    does not exist fails louder, but just as late; `plan_round` asks here first so a bad
    key costs nothing.
    """
    problems: list[str] = []
    stories = {p.name for p in (app / "stories").glob("*") if p.is_dir()}
    diffs: dict[str, set[str]] = {}
    for row in load_defects(app):
        rid, story, path = str(row.get("id")), str(row.get("story")), str(row.get("path"))
        if story not in stories:
            problems.append(f"{rid}: story {story!r} is not one of {', '.join(sorted(stories))}")
            continue
        if story not in diffs:
            diff = story_diff(app, story)
            diffs[story] = {*diff["changed"], *diff["added"]}
        if path not in diffs[story]:
            where = "pinned by" if path in story_diff(app, story)["pinned"] else "not in"
            problems.append(
                f"{rid}: {path} is {where} {story}'s diff — the defect would be committed in "
                "the before tree and no obligation would be minted for it"
            )
        if not variant_path(app, row).is_file():
            problems.append(f"{rid}: no variant at {variant_path(app, row)}")
        if str(row.get("expect")) != "contradicted":
            problems.append(f"{rid}: expect must be 'contradicted', not {row.get('expect')!r}")
    return problems


def select_defects(app: Path, wanted: tuple[str, ...]) -> list[dict[str, str]]:
    rows = load_defects(app)
    if not wanted:
        return rows
    by_id = {str(row["id"]): row for row in rows}
    unknown = [name for name in wanted if name not in by_id]
    if unknown:
        raise TrialError(
            f"no such defect(s): {', '.join(unknown)} (have: {', '.join(sorted(by_id))})"
        )
    return [by_id[name] for name in wanted]


def variant_path(app: Path, row: dict[str, str]) -> Path:
    return app / "defects" / str(row["id"]) / str(row["path"])


def seed_defect(app: Path, row: dict[str, str], repo: Path) -> None:
    """Plant one defect in a materialized tree.

    A whole-file overwrite: the variant either lands on a path that exists or raises here,
    where the trial has not yet cost anything. A patch would apply cleanly against a stale
    app and leave the trial measuring an app with no defect in it at all.
    """
    variant = variant_path(app, row)
    if not variant.is_file():
        raise TrialError(f"defect {row['id']}: no variant at {variant}")
    diff = story_diff(app, str(row["story"]))
    if str(row["path"]) not in {*diff["changed"], *diff["added"]}:
        raise TrialError(
            f"defect {row['id']}: {row['path']} is not in {row['story']}'s diff — seeding it "
            "would plant a defect in the before tree, outside what the trial is measured on"
        )
    target = repo / str(row["path"])
    if not target.is_file():
        raise TrialError(f"defect {row['id']}: {row['path']} is not in the materialized tree")
    shutil.copyfile(variant, target)


def defect_survived(app: Path, row: dict[str, str], witness: Path) -> bool:
    """Is the seeded file still byte-for-byte the defect variant at the end of the trial?

    This is the half of the score the terminal evidence map cannot see. The QA lane does not
    only observe — it triages a failing observation as `code` and repairs the product. When
    it does, the *last* evidence map is computed over a fixed app and reads `covered`, which
    is indistinguishable from a run that never noticed anything. Reading only that end state
    scores the loudest possible detection as a miss.

    So the seeded file itself is the witness. It was planted by an overwrite and nothing but
    the flow can have touched it since; if it no longer matches the variant, the flow acted
    on the defect. Byte equality, not a semantic check, because the question is only whether
    the code under test is still the code that was seeded — a repair that differs from the
    canonical app is still a repair.
    """
    target = witness / str(row["path"])
    if not target.is_file():
        return False
    return target.read_bytes() == variant_path(app, row).read_bytes()


# ── what a trial leaves behind ────────────────────────────────────────────────────────


def capture_witness(repo: Path, dest: Path, extra: tuple[str, ...] = ()) -> Path:
    """Copy the part of a finished trial tree the score reads, into the staged result.

    The trial tree itself lives in `scratch/` and is never sealed — fourteen copies of an
    application is a result zip nobody keeps. What the score needs is small and specific:
    `docs/` (the book, the spec, the plan, the evidence and the run ledger), the config
    files ostler roots on, and the one file the defect was seeded into.

    `docs/` is also what makes the copy work at all: `ostler.model.find_root` stops at a
    directory holding `docs/`, so the witness *is* a repo as far as the book loader is
    concerned, and a sealed result stays re-scorable on a machine that never ran it.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if (repo / "docs").is_dir():
        shutil.copytree(repo / "docs", dest / "docs", dirs_exist_ok=True)
    for name in ("agents.yml", ".agents.yml", "ostler.yml", "ostler.yaml"):
        if (repo / name).is_file():
            shutil.copyfile(repo / name, dest / name)
    for rel in extra:
        source = repo / rel
        if source.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest / rel)
    return dest


# ── classification ────────────────────────────────────────────────────────────────────


def evidence_statuses(witness: Path, story: str) -> dict[str, str] | None:
    """`{obligation id: status}` for the run's owed obligations, or None if unbuildable.

    None is not an empty map. `build_evidence_map` refuses when an input is missing, and a
    map computed over a missing run log reports every obligation `uncovered` — which is
    indistinguishable from a run that genuinely asserted nothing and would score a trial
    that never started as a wall of detections.
    """
    from ostler import qa as qa_mod

    try:
        data = qa_mod.build_evidence_map(witness / "docs" / "specs" / story)
    except qa_mod.EvidenceMapError:
        return None
    return {str(row["id"]): str(row["status"]) for row in data["obligations"]}


def audit_result(artifacts: Path, run_id: str) -> dict[str, Any]:
    """The auditor's last verdict for a trial, or an empty dict if it never ran."""
    path = artifacts / f"coder-{run_id}" / "audit-qa" / "output.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def classify(
    row: dict[str, str] | None,
    statuses: dict[str, str] | None,
    audit: dict[str, Any],
    *,
    survived: bool = True,
    audit_ran: bool = True,
) -> tuple[str, str]:
    """Score one trial against its row. Returns `(verdict, the status that decided it)`.

    Three routes count as a catch, because the flow has three places a defect can surface
    and which one fires is a property of the QA plan — the thing under measurement:

    * the **evidence map** puts the named obligation at the row's `expect`, which is a set
      operation over the run's own artifacts, or
    * the **auditor** refuted the pass and its findings name that obligation, or
    * the seeded code **did not survive** the run: QA observed the defect, triaged it as a
      code failure and repaired it. That path ends with the obligation `covered` — the map
      is right, the app really is fixed — so only the seeded file distinguishes it from a
      run that never noticed. It is checked last, since the first two say *where* the
      detection was recorded and this one only says that it happened.

    A miss is the specific, worse outcome: the run published a pass, claimed the obligation
    covered, *and* left the defect in place. Anything else — no map, an obligation out of
    scope, a run that blocked before it asserted anything — is `inconclusive` rather than a
    catch or a miss, since scoring an infrastructure failure either way is a number about
    this machine.

    The row's `caught_by` route is read, not merely recorded. A catch by either route still
    counts — which route fires is the plan's choice — but a catch that arrived by the other
    one is annotated `(expected run)` / `(expected audit)` so the surprise is legible in the
    same column as the verdict. And a row filed `audit` can only be missed by a configuration
    that gave the auditor a turn (`audit_ran`): under `FIRST_VERDICT` the lane never enters
    audit, so scoring such a row `missed` would grade the absence of a lane, not the plan.
    """
    refuted = str(audit.get("verdict", "")) == "refuted"
    # `unproven` is deliberately not read anywhere below. On the clean control it is not a
    # false alarm — the run never observed the product, so it accused nothing — and on a
    # defect row it is neither a catch nor a miss, since a plan that aborted had no chance to
    # notice. Both fall through to `inconclusive`, which is what an aborted scenario is.
    if row is None:  # the clean control: any contradiction at all is a false alarm
        if statuses is None:
            return "inconclusive", "no evidence map"
        contradicted = sorted(k for k, v in statuses.items() if v == "contradicted")
        if contradicted:
            return "false", contradicted[0]
        return ("false", "audit refuted") if refuted else ("clean", "no contradiction")

    obligation = str(row["obligation"])
    route = str(row.get("caught_by") or "run")
    by_run = "" if route == "run" else " (expected audit)"
    by_audit = "" if route == "audit" else " (expected run)"
    status = (statuses or {}).get(obligation, "")
    if status == str(row["expect"]):
        return "caught", status + by_run
    cited = obligation in json.dumps(audit)
    if refuted and cited:
        return "caught", "audit refutation" + by_audit
    if not survived:
        return "caught", "defect repaired" + by_run
    if route == "audit" and not audit_ran:
        return "inconclusive", "no audit turn in this configuration"
    if statuses is None:
        return "inconclusive", "no evidence map"
    if not status:
        return "inconclusive", "obligation not owed by this trial"
    if status == "covered":
        return "missed", status
    return "inconclusive", status


# ── leverage ──────────────────────────────────────────────────────────────────────────


#: Printed in place of a metric whose inputs are not there, and never `0`. A trial that
#: blocked before writing a plan navigated through no links and addressed no roles; a
#: `roles 0/0` there is a claim about the QA it produced rather than a report that there
#: was none — the same lie `classify` refuses when it scores a missing evidence map
#: `inconclusive` instead of a miss.
BLANK = "–"

#: The scorecard, in print order. Detection says whether the QA flow noticed a defect;
#: these say whether the plan it wrote used the book it was handed — entered each flow
#: where the book says the flow starts, moved between screens by clicking rather than by
#: re-navigating, addressed the UI by the roles the book documents, and closed the
#: obligations and the journeys it owed. A plan can catch a seeded defect while doing none
#: of that, and it is the difference between QA and a regression suite of URL fetches.
LEVERAGE_KEYS = ("entry", "deep_links", "roles", "obligations", "journeys", "sensitivity")

LEVERAGE_LABELS = {
    "entry": "entry",
    "deep_links": "deep-links",
    "roles": "roles",
    "obligations": "obligations",
    "journeys": "journeys",
    "sensitivity": "sensitivity",
}

#: The one evidence-map status that is a discharged obligation. The other five
#: (`uncovered`, `claimed-but-unasserted`, `contradicted`, `unproven`, `insensitive`) are
#: each a different way of not having proved it, and none of them counts here.
PASSING_STATUS = "covered"


def route_matches(route: str, url: str) -> bool:
    """Whether a planned `goto` lands on a route the book documents.

    Ostler's own `_route_matches` when it imports: it is the rule `qa validate` already
    applied to this plan, and a second implementation here would score plans against a
    gate that never ran. The fallback below is a transcription of that function, for an
    environment without ostler on the path.
    """
    try:
        from ostler.qa.plan import _route_matches
    except ImportError:
        planned = [part for part in urlsplit(url).path.strip("/").split("/") if part]
        documented = [part for part in urlsplit(route).path.strip("/").split("/") if part]
        if len(planned) != len(documented):
            return False
        return all(
            part.startswith((":", "{")) or other.startswith((":", "{")) or part == other
            for part, other in zip(planned, documented, strict=True)
        )
    return _route_matches(route, url)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in (value if isinstance(value, list) else [value])]


def _route_of(node: dict[str, Any]) -> str:
    """The route a screen node documents, or `""`.

    First whitespace token of the `route:` bullet with its backticks stripped, because the
    bullet is prose-shaped — ``- route: `/policies/:id` (the detail screen)`` — and only the
    path is a route.
    """
    for value in _values(node.get("bullets", {}).get("route")):
        token = value.strip().split()[0].strip("`") if value.strip() else ""
        if token.startswith("/"):
            return token
    return ""


def _literal(node: ast.expr | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _called(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def plan_scenarios(source: str) -> dict[str, dict[str, Any]]:
    """`{scenario id: {"covers": [...], "actions": [...]}}`, read statically from a `qa_plan.py`.

    From the plan rather than the run log because a `goto` URL never reaches
    `qa-run.ndjson`: the ledger records steps and assertions, not the browser calls inside
    them. The plan is also the artifact `ostler qa validate` judges, so scoring it scores
    the thing the flow was gated on.

    The action list comes from ostler's own `extract_locators` — the parser
    `_validate_book_locators` reads — so a locator counted here is the locator that gate
    saw, computed roles (`"*"`) and all. Only the `@scenario(...)` header is parsed
    locally, and only for the two fields the harness's static half does not return: the
    id, which is what the run log calls a scenario, and `covers`, which is what ties a
    scenario to the book.
    """
    from ostler.qa.harness_host import load_harness_module

    actions = load_harness_module("ostler_qa").extract_locators(source)
    found: dict[str, dict[str, Any]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or _called(decorator) != "scenario":
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords if kw.arg}
            given = _literal(keywords.get("id"))
            covers = _literal(keywords.get("covers"))
            found[given if isinstance(given, str) else node.name.replace("_", "-")] = {
                "covers": [str(item) for item in covers] if isinstance(covers, list) else [],
                "actions": actions.get(node.name, []),
            }
    return found


def _gotos(scenario: dict[str, Any]) -> list[str]:
    return [
        str(action["url"])
        for action in scenario["actions"]
        if isinstance(action, dict) and action.get("do") == "goto" and action.get("url")
    ]


def _locators(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        action["locator"]
        for action in scenario["actions"]
        if isinstance(action, dict) and isinstance(action.get("locator"), dict)
    ]


def required_flows(packet: dict[str, Any]) -> list[str]:
    """The flow nodes this story owes live evidence for.

    Off the obligations rather than the packet's `journeys:` list, because that list is
    every flow the graph closure reached and most of them are context: a story touching one
    endpoint pulls in every journey that endpoint appears in, and scoring a plan for not
    walking all of them would report a correct plan as a third of one.
    """
    return sorted({
        str(obligation["node"])
        for obligation in packet.get("obligations", []) or []
        if isinstance(obligation, dict)
        and obligation.get("kind") == "journey"
        and obligation.get("required", True)
        and obligation.get("node")
    })


def flow_starts(book: dict[str, Any]) -> dict[str, str]:
    """`{flow node id: the route its `start:` screen documents}`.

    Two hops, because neither end carries both halves: the flow names its start screen as a
    link, and the route lives on the screen. `via` is the bullet key the link was written
    under, which is what keeps a `start:` edge apart from a `steps:` one pointing at the
    same screen.
    """
    routes = {str(node["id"]): _route_of(node) for node in book.get("nodes", []) or []}
    starts: dict[str, str] = {}
    for edge in book.get("edges", []) or []:
        if edge.get("via") == "start" and routes.get(str(edge.get("to"))):
            starts.setdefault(str(edge["from"]), routes[str(edge["to"])])
    return starts


def entry_routes(book: dict[str, Any]) -> set[str]:
    """Every route a user may legitimately arrive at from outside in-app navigation.

    A flow's start plus any screen carrying an `entry:` bullet — the book's own word for
    "reached by an app root, an emailed link or an OAuth callback". Navigating straight to
    one of these mid-scenario is arriving, not deep-linking.
    """
    routes = {
        _route_of(node)
        for node in book.get("nodes", []) or []
        if node.get("bullets", {}).get("entry") and _route_of(node)
    }
    return routes | set(flow_starts(book).values())


def documented_routes(book: dict[str, Any]) -> set[str]:
    return {route for node in book.get("nodes", []) or [] if (route := _route_of(node))}


def book_sensitivity(repo: Path) -> list[int] | None:
    """`[claims observed by a check that could fail, claims the book mints]`, or None.

    A property of the book rather than of the run, which is exactly why it is worth printing
    beside the run's numbers: `obligations 220/263` counts assertions that passed, and this
    is the denominator's other half — how many of them could have done anything else.

    The denominator is every claim, including the ones no `verify:` observes. Counting only
    the observed ones would let a book raise this number by deleting a weak check instead of
    strengthening it.
    """
    try:
        from ostler import model
        from ostler.qa import sensitivity as sensitivity_mod
    except ImportError:
        return None
    try:
        rows = sensitivity_mod.report(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None
    return [sum(1 for row in rows if row.status == "sensitive"), len(rows)] if rows else None


def leverage_from(
    book: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    plan_source: str | None,
    run_log: list[dict[str, Any]] | None,
    statuses: dict[str, str] | None,
    sensitivity: list[int] | None = None,
) -> dict[str, Any]:
    """The six leverage metrics, each a `[n, of]` pair, an int, or None when incomputable.

    None rather than a zero everywhere an input is missing. Every one of these is a
    fraction whose denominator is a property of the *book* — flows documented, obligations
    owed, locators written — so an absent artifact makes the question unaskable rather than
    the answer bad, and `leverage_line` prints `–` for it.
    """
    scenarios = plan_scenarios(plan_source) if plan_source else {}
    if run_log is not None:
        # Only what the run actually started. A scenario the plan declares and the driver
        # never reached entered nothing and clicked nothing, and crediting it for the entry
        # its source says it would have made scores an intention.
        started = {
            str(record.get("scenario", ""))
            for record in run_log
            if record.get("kind") == "scenario_start"
        }
        scenarios = {name: data for name, data in scenarios.items() if name in started}

    flows = required_flows(packet) if packet else []
    starts = flow_starts(book) if book else {}
    covering: dict[str, list[dict[str, Any]]] = {flow: [] for flow in flows}
    for data in scenarios.values():
        for flow in flows:
            if any(cover.startswith(f"okf:{flow}:") for cover in data["covers"]):
                covering[flow].append(data)

    entry: list[int] | None = None
    if flows and any(starts.get(flow) for flow in flows):
        entry = [
            sum(
                1
                for flow in flows
                if (route := starts.get(flow))
                and any(
                    (gotos := _gotos(data)) and route_matches(route, gotos[0])
                    for data in covering[flow]
                )
            ),
            len(flows),
        ]

    deep_links: int | None = None
    if book and scenarios:
        elsewhere = documented_routes(book)
        arrivals = entry_routes(book)
        deep_links = sum(
            1
            for data in scenarios.values()
            for url in _gotos(data)[1:]
            if any(route_matches(route, url) for route in elsewhere)
            and not any(route_matches(route, url) for route in arrivals)
        )

    roles: list[int] | None = None
    uses = [locator for data in scenarios.values() for locator in _locators(data)]
    if uses:
        # `role` and `css` are the two strategies the book can vouch for — a `role:` bullet
        # and a `selector:` one. `text` and `label` address a rendered string, which is what
        # the next copy edit changes; `test_id` addresses a hook the book never mentions.
        roles = [sum(1 for locator in uses if "role" in locator or "css" in locator), len(uses)]

    obligations = (
        [sum(1 for status in statuses.values() if status == PASSING_STATUS), len(statuses)]
        if statuses
        else None
    )

    journeys = (
        [
            sum(1 for flow in flows if statuses.get(f"okf:{flow}:end-state") == PASSING_STATUS),
            len(flows),
        ]
        if statuses and flows
        else None
    )

    return {
        "entry": entry,
        "deep_links": deep_links,
        "roles": roles,
        "obligations": obligations,
        "journeys": journeys,
        "sensitivity": sensitivity,
    }


def read_ndjson(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def load_book(repo: Path) -> dict[str, Any] | None:
    """The feature graph as `{"nodes": [...], "edges": [...]}`, or None if it will not load.

    The same `graph.build` behind `ostler graph`, in this process. A trial's book is the
    frozen app's book plus whatever the flow wrote, and it is the only artifact carrying a
    flow's start screen — the packet lifts `route:` onto an obligation but never `start:`.
    """
    try:
        from ostler import graph as graph_mod
        from ostler import model
    except ImportError:
        return None
    try:
        return graph_mod.build(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None


def leverage(witness: Path, story: str, statuses: dict[str, str] | None) -> dict[str, Any]:
    """Score one trial's artifacts. Every input is optional; a missing one prints `–`."""
    spec = witness / "docs" / "specs" / story
    plan_file = spec / "qa_plan.py"
    return leverage_from(
        load_book(witness),
        read_json(spec / "qa-okf-context.json"),
        plan_file.read_text(encoding="utf-8") if plan_file.is_file() else None,
        read_ndjson(spec / "qa" / "qa-run.ndjson"),
        statuses,
        book_sensitivity(witness),
    )


#: Metrics that measure the book rather than the trial, and so must not be summed over trials.
BOOK_LEVEL_KEYS = frozenset({"sensitivity"})


def pool_leverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the metrics across trials, keeping a metric None when no trial could compute it.

    Summed rather than averaged, for the reason laps are pooled: these are counts over a
    denominator that varies per story, and averaging per-trial fractions would weight a
    one-flow story the same as a five-flow one.

    Except for a `BOOK_LEVEL_KEYS` metric, whose denominator is the same book every trial
    read. Summing that one multiplies both halves by the trial count and prints a book with
    fifty-eight claims as one with eight hundred — a true ratio over an invented total, which
    reads as far more evidence than the round holds. The widest one seen is taken instead,
    since a trial that failed to load part of the book should not shrink it.
    """
    pooled: dict[str, Any] = dict.fromkeys(LEVERAGE_KEYS)
    for row in rows:
        metrics = row.get("leverage") or {}
        for key in LEVERAGE_KEYS:
            value = metrics.get(key)
            if value is None:
                continue
            current = pooled[key]
            if isinstance(value, list):
                pair = [int(value[0]), int(value[1])]
                if current is None:
                    pooled[key] = pair
                elif key in BOOK_LEVEL_KEYS:
                    pooled[key] = max(current, pair, key=lambda seen: seen[1])
                else:
                    pooled[key] = [current[0] + pair[0], current[1] + pair[1]]
            else:
                pooled[key] = int(value) + (current or 0)
    return pooled


def leverage_line(metrics: dict[str, Any], keys: tuple[str, ...] = LEVERAGE_KEYS) -> str:
    """Print the metrics the fixture declared it can own, and say how many it left out.

    A fixture with no screen has no entry point to enter and no link to deep-link through:
    `claims-api` prints `entry –  deep-links –  roles –` on every round, and three blanks
    out of six read as three metrics that failed to compute rather than three that do not
    apply. The fixture says which keys its book can own; the others are not printed, and
    the line ends with `(of 6 metrics)` so the omission is visible rather than silent.
    """
    parts = []
    for key in keys:
        value = metrics.get(key)
        if value is None:
            shown = BLANK
        elif isinstance(value, list):
            shown = f"{value[0]}/{value[1]}"
        else:
            shown = str(value)
        parts.append(f"{LEVERAGE_LABELS[key]} {shown}")
    line = "leverage: " + "  ".join(parts)
    if len(keys) < len(LEVERAGE_KEYS):
        line += f"  ({len(keys)} of {len(LEVERAGE_KEYS)} metrics)"
    return line


# ── the round, rendered ───────────────────────────────────────────────────────────────


def headline(trials: list[dict[str, Any]]) -> str:
    seeded = [trial for trial in trials if trial["defect"] != CLEAN]
    caught = sum(1 for trial in seeded if trial["verdict"] == "caught")
    missed = sum(1 for trial in seeded if trial["verdict"] == "missed")
    false = sum(1 for trial in trials if trial["verdict"] == "false")
    unknown = sum(1 for trial in trials if trial["verdict"] == "inconclusive")
    line = f"caught {caught}/{len(seeded)}  missed {missed}  false {false}{fx.convergence(trials)}"
    if unknown:
        # Loudly, and never folded into a miss: an inconclusive trial is the harness
        # failing, and averaging it into the detection rate hides the outage as a result.
        line += f"  inconclusive {unknown}"
    return line


def detail(trials: list[dict[str, Any]], leverage: tuple[str, ...] = LEVERAGE_KEYS) -> list[str]:
    lines: list[str] = []
    for trial in trials:
        timing = trial.get("timing") or {}
        lines.append(
            f"  {trial['defect']:<6} {trial['verdict']:<13} {trial['because']}"
            f"  [{timing.get('wall_s', 0) / 60:.0f}m]"
        )
        lines.append(f"    {trial['obligation'] or '(control)'}")
    lines.append("")
    lines.append("  " + leverage_line(pool_leverage(trials), leverage))
    if (leveraged := fx.time_leverage(trials)):
        lines.append("  " + leveraged)
    lines.append("")
    lines.extend(fx.node_table(trials))
    return lines


# ── the round, run ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Fixture:
    """Everything that distinguishes one frozen-app task from another.

    Two paths and a budget. The round itself — a control per story, a trial per row of the
    answer key, a witness per trial — is identical across apps because the fixtures are:
    same answer-key schema, same story-image layout, same evidence map. A task module that
    re-implemented the loop would be a second place to fix every change to it.
    """

    #: The tracked app tree, relative to the data directory.
    app: str
    #: The basename every trial materializes into. Load-bearing and therefore constant
    #: across trials: farrier derives the generated skill filenames from the repo
    #: directory's name and the app's compose project is named after it, so a directory
    #: named per defect would give each trial a different skill set and a different stack.
    repo_dir: str
    #: The default wall-clock budget for one trial, in seconds. Enforced by workhorse
    #: between states, so an over-budget trial stops at a node boundary with its telemetry
    #: intact and still reports a partial lap count — a budget death is a measurement.
    budget_s: float = 2400.0
    #: The leverage metrics this fixture's book can own, in `LEVERAGE_KEYS` order. A
    #: fixture with no screen declares the three a contract can carry and its scorecard
    #: prints those, with `(3 of 6 metrics)` after them, instead of three blanks that read
    #: as metrics that failed to compute. Every key must be one of `LEVERAGE_KEYS`.
    leverage: tuple[str, ...] = LEVERAGE_KEYS

    def __post_init__(self) -> None:
        unknown = [key for key in self.leverage if key not in LEVERAGE_KEYS]
        if unknown or not self.leverage:
            raise ValueError(
                f"{self.app}: leverage must name one or more of {', '.join(LEVERAGE_KEYS)}; "
                f"got {self.leverage!r}"
            )


#: Where a round's own ledger lives inside the stage. Named explicitly rather than via
#: `run.artifacts`, because that property is relative to the *current step* and `score`
#: runs outside every step.
TRIALS = ("artifacts", "trials")


def key_dir(run: Run, fixture: Fixture) -> Path:
    """The tracked app tree, which is where `defects.yml` and the variants are read from.

    The seed is a capture of exactly this tree and the trials run against the capture — but
    the **answer key** is read from here, from the copy git tracks and `check_public.py`
    scans. A score that read its key out of the unpacked zip would be a score whose ruler
    travels inside the thing being measured.
    """
    directory = run.data_dir / fixture.app
    if not (directory / "defects.yml").is_file():
        raise TrialError(f"no answer key under {directory} — is --data-dir the repo's paddock/data/?")
    return directory


def trials_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*TRIALS)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def plan_round(run: Run, app: Path) -> list[tuple[str, dict[str, str] | None]]:
    """The trials to run: one control per story, then one per selected defect.

    One control per *story*, not one per round: the obligations a trial owes are minted
    from that story's diff, so a control for one story says nothing about whether another
    raises a false alarm. The control is what makes the detection number readable at all —
    a lane that refuted everything would score every defect caught, and only a trial with
    nothing wrong in it tells the two apart.
    """
    problems = validate_defects(app)
    if problems:
        raise TrialError(f"{app / 'defects.yml'} cannot be scored:\n  " + "\n  ".join(problems))
    rows = select_defects(app, run.param_list("defects"))
    stories = sorted({str(row["story"]) for row in rows})
    control: list[tuple[str, dict[str, str] | None]] = (
        [] if run.param_bool("no_control") else [(story, None) for story in stories]
    )
    return [*control, *[(str(row["story"]), row) for row in rows]]


def run_round(run: Run, fixture: Fixture) -> None:
    """Run the round: materialize, seed, drive `workhorse-coder run qa`, keep the witness."""
    app = key_dir(run, fixture)
    checkout = stablemate_checkout(run)
    budget = run.param_float("budget", fixture.budget_s)
    config = effective(run)
    runs_dir = trials_dir(run) / "runs"

    with no_leaks(checkout, pinned=pin_held(run.pinned)):
        ledger: list[dict[str, Any]] = []
        for index, (story, row) in enumerate(plan_round(run, app), start=1):
            variant = str(row["id"]) if row else CLEAN
            run_id = f"{fixture.repo_dir}-{run.label}-qa-{story}-{variant}-{index}"
            # farrier regenerates `.agents/agents-context.json`, which is gitignored and so is
            # absent from a materialized tree; every prompt path in the run would fail to
            # resolve without it. It is also where the unpacked seed's machine-local paths get
            # re-pointed at this machine. It runs *inside* materialize, before the before-commit,
            # so the layer it generates is part of the baseline rather than of the story's diff.
            def install(repo: Path, run_id: str = run_id) -> None:
                run.cli(
                    *uv_run(checkout, "farrier"),
                    "farrier", "install", "--repo", str(repo),
                    cwd=checkout, log_name=f"{run_id}-farrier", check=True,
                )

            repo = materialize(run.repo, story, run.workdir(run_id) / fixture.repo_dir, install)
            if row:
                seed_defect(app, row, repo)
            reset_stack_state(repo)

            # Two clocks: `monotonic` measures the trial and cannot go backwards, while the
            # epoch second is what groom's spans are stamped with, so it is the only one that
            # can bound this trial's telemetry away from an earlier round under the same id.
            started, since = time.monotonic(), time.time()
            result = run.cli(
                # `uv_run` rather than an inherited cwd: the trial process stands *in the
                # tree under test* (see `cwd=repo`), so uv is told where its workspace is
                # instead of finding it underfoot — and which member's environment to run
                # in, so the pinned checkout's code is what actually runs.
                *uv_run(checkout, "workhorse-workflows"),
                "workhorse-coder", "run", "qa",
                "--runs-dir", str(runs_dir), "--run-id", run_id,
                # Whole-file: the round's models are the tracked config's, not whatever this
                # machine happens to have set. A label whose trials inherited the shell is not
                # a configuration anyone can compare against.
                "--config", str(config),
                # `first_verdict`: a trial asks what one plan and one suite run say about
                # the product — the lane ends at the first verdict instead of repairing
                # toward green, so a seeded defect reports its first red without entering
                # the fix loop and a clean control's pass costs no repair/refute turns.
                "--params", json.dumps(
                    {"story": story, "docs_path": str(repo), "first_verdict": FIRST_VERDICT}
                ),
                cwd=repo,
                # Enforced by workhorse between states rather than by killing the process, so an
                # over-budget trial stops at a node boundary with its spans intact.
                env={**os.environ, "WORKHORSE_MAX_RUNTIME_S": str(budget), "AGENT_REPO_DIR": str(repo)},
                log_name=f"{run_id}-qa",
            )
            wall = time.monotonic() - started

            witness = capture_witness(
                repo,
                trials_dir(run) / run_id / "witness",
                extra=(str(row["path"]),) if row else (),
            )
            ledger.append({
                "run_id": run_id, "story": story, "defect": variant,
                "obligation": str(row["obligation"]) if row else "",
                "path": str(row["path"]) if row else "",
                "rc": result.returncode,
                # Whether this configuration gave the auditor a turn at all — what separates
                # an `audit` row's miss from a row this lane could never have caught.
                "audit_turn": not FIRST_VERDICT,
                "witness": str(witness.relative_to(run.stage)),
                "timing": fx.timing_of(run_id, wall, since),
                "laps": fx.laps_of(run_id, since),
            })
            run.write_json(trials_dir(run) / "trials.json", ledger)


def score_round(run: Run, fixture: Fixture) -> Score:
    """Detection beside cost beside leverage — exactly the round the replay harness printed.

    Read-only over the stage, and read entirely from what the trials left in it: the
    verdicts are recomputed here rather than recorded by the step, so a result zip can be
    re-scored after the classifier changes without re-running the whole round.
    """
    ledger = run.stage.joinpath(*TRIALS) / "trials.json"
    if not ledger.is_file():
        return Score(headline="no trials recorded — the round did not reach a run", detail=())

    app = key_dir(run, fixture)
    by_id = {str(row["id"]): row for row in load_defects(app)}
    trials: list[dict[str, Any]] = []
    for entry in json.loads(ledger.read_text(encoding="utf-8")):
        row = by_id.get(str(entry["defect"]))
        witness = run.stage / str(entry["witness"])
        statuses = evidence_statuses(witness, str(entry["story"]))
        audit = audit_result(run.stage.joinpath(*TRIALS) / "runs", str(entry["run_id"]))
        verdict, because = classify(
            row,
            statuses,
            audit,
            survived=defect_survived(app, row, witness) if row else True,
            # A ledger written before `audit_turn` was recorded came from the same
            # first-verdict configuration; an auditor verdict on disk is proof either way.
            audit_ran=bool(audit) or bool(entry.get("audit_turn", not FIRST_VERDICT)),
        )
        trials.append({
            **entry,
            "verdict": verdict,
            "because": because,
            # In the same row the verdict lands in, because the two are read together: a
            # round that caught everything by fetching URLs and one that caught everything
            # by walking the product are the same headline and different products.
            "leverage": leverage(witness, str(entry["story"]), statuses),
        })

    return Score(
        headline=headline(trials),
        detail=tuple(detail(trials, fixture.leverage)),
        data={"trials": trials, "leverage": pool_leverage(trials)},
    )
