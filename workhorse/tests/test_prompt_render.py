from __future__ import annotations

from pathlib import Path

from workhorse.templates import render


def _workflow(base: Path) -> Path:
    workflow_dir = base / "lib" / "workflows" / "author"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "prompts" / "write-story.md").write_text("Generic authoring instructions.\n")
    return workflow_dir


def test_a_prompt_renders_from_the_workflow_directory(tmp_path):
    out = render("prompts/write-story.md", {}, _workflow(tmp_path))
    assert out == "Generic authoring instructions.\n"


def test_a_repo_file_under_the_retired_flavors_path_changes_nothing(tmp_path):
    workflow_dir = _workflow(tmp_path)
    repo = tmp_path / "repo"
    flavors = repo / ".agents" / "flavors" / "author"
    flavors.mkdir(parents=True)
    (flavors / "write-story.md").write_text("REPO RULE\n")
    out = render("prompts/write-story.md", {"_repo_root": str(repo)}, workflow_dir)
    assert out == "Generic authoring instructions.\n"


def test_a_prompt_includes_a_partial_beside_it(tmp_path):
    workflow_dir = _workflow(tmp_path)
    prompts = workflow_dir / "qa" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "_contract.md").write_text("THE CONTRACT")
    (prompts / "qa-story.md").write_text('Own the story.\n{% include "_contract.md" %}\n')
    out = render("qa/prompts/qa-story.md", {}, workflow_dir)
    assert "THE CONTRACT" in out
