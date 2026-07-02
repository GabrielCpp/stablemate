from __future__ import annotations

import json
from pathlib import Path

from ostler.cli import main


def run(tmp_path: Path, *argv: str) -> int:
    return main(["-C", str(tmp_path), *argv])


def test_full_template_and_instance_lifecycle(tmp_path: Path, capsys):
    assert run(tmp_path, "template", "new", "research", "program", "gate") == 0
    assert run(tmp_path, "template", "edit", "research",
              "--set", "program.doc_root=research",
              "--set", "program.default_path=specs",
              "--set", "program.path_template={name}/program.md",
              "--set", "program.required=[type, title, status]",
              "--set", "program.fields.status.enum=[proposed, active, complete]",
              "--set", "gate.doc_root=research",
              "--set", "gate.default_path=specs",
              "--set", "gate.parent=program",
              "--set", "gate.path_template={parent}/gates/{name}/gate.md",
              "--set", "gate.required=[type, gate, status]") == 0
    assert run(tmp_path, "template", "apply", "research") == 0
    assert (tmp_path / "specs").is_dir()
    assert "<!-- ostler:template:research:start -->" in (tmp_path / "CLAUDE.md").read_text()

    assert run(tmp_path, "new", "program", "SMCNv3", "title=SMCNv3", "status=active") == 0
    assert (tmp_path / "specs/SMCNv3/program.md").exists()

    assert run(tmp_path, "new", "gate", "G0", "program=SMCNv3", "gate=G0", "status=pending") == 0
    assert (tmp_path / "specs/SMCNv3/gates/G0/gate.md").exists()

    capsys.readouterr()
    assert run(tmp_path, "find", "program", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["name"] == "SMCNv3" and out[0]["status"] == "active"

    assert run(tmp_path, "set", "program", "SMCNv3", "status=complete") == 0
    capsys.readouterr()
    run(tmp_path, "find", "program", "SMCNv3", "--json")
    out = json.loads(capsys.readouterr().out)
    assert out[0]["status"] == "complete"

    assert run(tmp_path, "remove", "gate", "G0") == 0
    assert not (tmp_path / "specs/SMCNv3/gates/G0").exists()
    assert (tmp_path / "specs/SMCNv3/program.md").exists()

    assert run(tmp_path, "remove", "program", "SMCNv3") == 0
    assert not (tmp_path / "specs/SMCNv3").exists()


def test_list_type_accepts_template_kind(tmp_path: Path, capsys):
    run(tmp_path, "template", "new", "research", "program")
    run(tmp_path, "template", "edit", "research", "--set", "program.default_path=specs")
    run(tmp_path, "new", "program", "SMCNv3", "title=SMCNv3")
    capsys.readouterr()
    assert run(tmp_path, "list", "--type", "program", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["name"] == "SMCNv3"


def test_list_type_rejects_unknown_type(tmp_path: Path):
    assert run(tmp_path, "list", "--type", "bogus") == 2


def test_new_rejects_malformed_field(tmp_path: Path):
    run(tmp_path, "template", "new", "research", "program")
    run(tmp_path, "template", "edit", "research", "--set", "program.default_path=specs")
    assert run(tmp_path, "new", "program", "SMCNv3", "not-a-kv-pair") == 2
