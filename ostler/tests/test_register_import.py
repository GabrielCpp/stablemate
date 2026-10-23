"""The Import: ``ostler backlog adopt --repo R <file>`` turns an old bullet list into records once."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ostler import register
from ostler.api import Ostler
from ostler.cli import main
from ostler.model import load

HAND_WRITTEN = """
### Features

- Let acme storefront owners preview a theme before it goes live, using the
  staging site as the preview target. Owners asked for it twice.
- A way to replay a failed globex webhook from the dashboard without opening a ticket.
- Export the order history as CSV. Finance wants it monthly.
- Show the shipping estimate on the cart page before the customer signs in.
- Let support staff merge two customer accounts that share one email address.


### Ideas

- Offer a dark mode for the acme admin console.
- Can we template the onboarding emails per plan instead of per locale?
- [BL-001] Standardize linting per language in the shared overlay.
- [BL-002] Design a skill for the generic makefile with lint, test and build targets.
- [BL-003] The doctor should run as a standard check for every package.


### Open questions
- How do we show the staging banner on the globex preview without a redeploy?
- Should the cart keep its contents across devices?
- Which payment provider do we pilot in the second region?

### Planned

- Full customer documentation, a website and icons for a smooth release.

### Platform alignment | https://example.com/playbook

Assessed 2026-08-26: the rollout chain covers most of the playbook stages.
The gaps below are what full alignment would take, roughly in order:

1. Evals in CI
2. Review loop

- Wire evals into CI. The harness exists and scores fixtures, but nothing runs
  on changes to prompts, so every prompt edit ships ungated today.
  - Start with a cheap fixture-replay subset.
- Protect the checks during the repair loop. Nothing stops an agent weakening a
  test file while repairing a red run.
- Name the incident-to-eval convention. We already do it informally.
- Add a continuous intake entry point for one new intent.
- Run a review pass on the pull request side.
- Feed review findings back into the shared skills.
- Decide deliberately on deployment and production monitoring.
"""


def run(root: Path, *argv: str) -> int:
    return main(["-C", str(root), *argv])


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def commit_subjects() -> list[str]:
    if not (artifacts() / ".git").exists():
        return []
    done = subprocess.run(
        ["git", "-C", str(artifacts()), "log", "--format=%s"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    return done.stdout.splitlines()


def source(repo: Path, text: str, name: str = "docs/backlog.md") -> Path:
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def imported(repo: Path) -> dict[str, register.Record]:
    return {r.id: r for r in register.records(load(repo)).records}


def test_a_hand_written_list_becomes_one_record_per_bullet(tmp_path: Path, capsys) -> None:
    file = source(tmp_path, HAND_WRITTEN)

    code = run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme")

    assert code == 0
    records = imported(tmp_path)
    assert len(records) == 21
    assert {i for i in records if i.startswith("BL-")} == {"BL-001", "BL-002", "BL-003"}
    minted = [i for i in records if not i.startswith("BL-")]
    assert len(minted) == 18 and all(i.startswith("acme-") for i in minted)
    assert {r.repo for r in records.values()} == {"acme-shop"}
    assert {r.filed_by for r in records.values()} == {"person"}
    assert {r.pattern for r in records.values()} == {"untriaged"}
    areas: dict[str, int] = {}
    for r in records.values():
        areas[r.area] = areas.get(r.area, 0) + 1
    assert areas == {"features": 5, "ideas": 5, "open-questions": 3, "planned": 1,
                     "platform-alignment": 7}
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 22
    assert lines[-1] == "imported 21 records, kept 3 ids"
    assert not file.exists()


def test_the_records_are_one_artifacts_commit_and_the_code_repo_is_untouched(tmp_path: Path) -> None:
    file = source(tmp_path, HAND_WRITTEN)

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme") == 0

    assert commit_subjects() == ["chore(acme-shop): import the backlog list"]
    status = subprocess.run(
        ["git", "-C", str(artifacts()), "status", "--porcelain", "-uall", "--", "backlog"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    assert status.stdout.strip() == ""
    left = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert left == [".agents/ids.json"]


def test_a_body_holds_the_whole_bullet_and_where_it_sat(tmp_path: Path) -> None:
    file = source(tmp_path, HAND_WRITTEN)
    run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme")
    records = imported(tmp_path)

    wired = next(r for r in records.values() if r.summary.startswith("Wire evals into CI."))
    assert wired.summary == "Wire evals into CI."
    assert wired.body.startswith("Wire evals into CI. The harness exists")
    assert "ships ungated today." in wired.body
    assert "- Start with a cheap fixture-replay subset." in wired.body
    assert "## Context" in wired.body
    assert 'Platform alignment | https://example.com/playbook' in wired.body
    assert "Assessed 2026-08-26" in wired.body
    assert "1. Evals in CI" in wired.body and "2. Review loop" in wired.body
    assert "Name the incident" not in wired.body

    kept = records["BL-002"]
    assert "[BL-002]" not in kept.body and "[BL-002]" not in kept.summary
    assert kept.summary == "Design a skill for the generic makefile with lint, test and build targets."

    preview = next(r for r in records.values() if r.summary.startswith("Let acme storefront"))
    assert preview.summary == "Let acme storefront owners preview a theme before it goes live, using the staging site as the preview target."
    assert "\n" not in preview.summary
    assert "Owners asked for it twice." in preview.body


def test_a_long_first_sentence_is_cut_at_a_word_boundary_with_an_ellipsis(tmp_path: Path) -> None:
    words = " ".join(["storefront"] * 30)
    file = source(tmp_path, f"### Ideas\n\n- {words} is too long.\n")

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme") == 0

    [only] = imported(tmp_path).values()
    assert only.summary.endswith("…")
    assert len(only.summary) <= 161
    assert only.summary[:-1].rstrip().endswith("storefront")
    assert words in only.body


def test_the_known_section_titles_set_who_filed_the_record(tmp_path: Path) -> None:
    file = source(tmp_path, (
        "# Backlog\n\n"
        "## Filed by coder\n\n- Fix the stale cart total. Seen while on the checkout story.\n\n"
        "## deferred by CODER\n\n- Extract the tax rules.\n\n"
        "## Book checks QA could not run\n\n- Book page `docs/services/cart.md` gives QA no check.\n\n"
        "## Survey findings\n\n- The cart module owns three concerns.\n\n"
        "## Legacy surfaces missing from the new app\n\n- The old invoice export screen.\n\n"
        "## Planned\n\n- Something a person wrote.\n"
    ))

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme") == 0

    by_summary = {r.summary: r for r in imported(tmp_path).values()}
    got = {s: (r.filed_by, r.area) for s, r in by_summary.items()}
    assert got == {
        "Fix the stale cart total.": ("qa", "untriaged"),
        "Extract the tax rules.": ("coder", "untriaged"),
        "Book page `docs/services/cart.md` gives QA no check.": ("qa-deferred", "book"),
        "The cart module owns three concerns.": ("survey", "untriaged"),
        "The old invoice export screen.": ("parity", "untriaged"),
        "Something a person wrote.": ("person", "planned"),
    }


def test_a_bullet_under_no_heading_or_only_a_document_title_goes_to_general(tmp_path: Path) -> None:
    file = source(tmp_path, "# Backlog\n\n- First thing.\n- Second thing.\n")
    other = source(tmp_path, "- Third thing.\n", "docs/other.md")

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme") == 0
    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(other), "--prefix", "acme") == 0

    records = imported(tmp_path).values()
    assert {(r.summary, r.area) for r in records} == {
        ("First thing.", "general"), ("Second thing.", "general"), ("Third thing.", "general")}


def test_numbered_lists_and_paragraphs_are_prose_not_records(tmp_path: Path) -> None:
    file = source(tmp_path, "### Plan\n\nIntro paragraph.\n\n1. one\n2. two\n\n- The only record.\n")

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme") == 0

    [only] = imported(tmp_path).values()
    assert only.summary == "The only record."
    assert "Intro paragraph." in only.body and "2. two" in only.body


def test_a_kept_id_already_on_the_shelf_refuses_everything(tmp_path: Path, capsys) -> None:
    graph = load(tmp_path)
    register.file_record(graph, repo="api-service", area="billing", pattern="x",
                         summary="Already here", filed_by="person", record_id="BL-002")
    file = source(tmp_path, HAND_WRITTEN)
    before = file.read_text(encoding="utf-8")
    capsys.readouterr()

    code = run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme")

    assert code == 1
    assert "BL-002" in capsys.readouterr().out
    assert [r.id for r in register.records(load(tmp_path)).records] == ["BL-002"]
    assert file.read_text(encoding="utf-8") == before
    assert commit_subjects() == []


def test_a_kept_id_a_story_holds_refuses_everything(tmp_path: Path, capsys) -> None:
    okf = Ostler(tmp_path)
    okf.create_epic("checkout", "Checkout", prefix="acme")
    epic_id = next(e["id"] for e in okf.list("epic"))
    file = source(tmp_path, f"### Ideas\n\n- [{epic_id}] Clashes with an epic.\n- Fine.\n")
    capsys.readouterr()

    code = run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme")

    assert code == 1 and "already taken" in capsys.readouterr().out
    assert register.records(load(tmp_path)).records == ()
    assert file.exists()


def test_a_kept_id_twice_in_the_list_refuses_everything(tmp_path: Path, capsys) -> None:
    file = source(tmp_path, "### Ideas\n\n- [BL-1] One.\n- [BL-1] Two.\n")
    capsys.readouterr()

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file), "--prefix", "acme") == 1

    assert "BL-1" in capsys.readouterr().out
    assert register.records(load(tmp_path)).records == ()
    assert file.exists()


def test_a_list_with_no_bullets_is_refused_and_kept(tmp_path: Path, capsys) -> None:
    file = source(tmp_path, "# Backlog\n\nJust prose.\n")

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file)) == 1

    assert "no bullets" in capsys.readouterr().out
    assert file.exists()


def test_a_bad_repo_name_is_refused_before_anything_is_written(tmp_path: Path, capsys) -> None:
    file = source(tmp_path, HAND_WRITTEN)

    assert run(tmp_path, "backlog", "adopt", "--repo", "Acme Shop", str(file), "--prefix", "acme") == 1

    assert "repo" in capsys.readouterr().out
    assert register.records(load(tmp_path)).records == ()
    assert file.exists()


def test_a_missing_source_file_is_refused(tmp_path: Path, capsys) -> None:
    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(tmp_path / "nope.md")) == 1

    assert "nope.md" in capsys.readouterr().out


def test_json_emits_the_records(tmp_path: Path, capsys) -> None:
    file = source(tmp_path, "### Ideas\n\n- [BL-9] One.\n- Two.\n")
    capsys.readouterr()

    assert run(tmp_path, "backlog", "adopt", "--repo", "acme-shop", str(file),
               "--prefix", "acme", "--json") == 0

    rows = json.loads(capsys.readouterr().out)
    assert sorted(r["summary"] for r in rows) == ["One.", "Two."]
    assert {r["repo"] for r in rows} == {"acme-shop"}
    assert "BL-9" in {r["id"] for r in rows}


def test_the_import_leaves_the_old_in_place_adoption_to_the_facade(tmp_path: Path) -> None:
    file = source(tmp_path, "# Backlog\n\n- Unnamed work.\n")

    result = Ostler(tmp_path).backlog_adopt(prefix="acme")

    assert result.ok
    assert "[acme-" in file.read_text(encoding="utf-8")


def test_the_import_needs_a_repo(tmp_path: Path) -> None:
    file = source(tmp_path, "- One.\n")

    with pytest.raises(SystemExit) as exc:
        run(tmp_path, "backlog", "adopt", str(file))

    assert exc.value.code == 2
