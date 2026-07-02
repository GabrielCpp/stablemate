from __future__ import annotations

from ostler.cli import _build_parser


def parse(argv):
    return _build_parser().parse_args(argv)


def test_write_flag_accepted_after_subcommand():
    args = parse(["edit", "rename", "a", "b", "--write"])
    assert args.op == "rename" and getattr(args, "write", False) is True


def test_write_flag_accepted_before_subcommand():
    args = parse(["edit", "--write", "rename", "a", "b"])
    assert args.op == "rename" and getattr(args, "write", False) is True


def test_dry_run_is_default():
    args = parse(["edit", "set-owner", "g", "s"])
    assert getattr(args, "write", False) is False


def test_each_edit_op_takes_write():
    for argv in (["edit", "set-owner", "g", "s", "--write"],
                 ["edit", "relink", "old", "new", "--write"],
                 ["edit", "rename", "old", "new", "--write"]):
        assert getattr(parse(argv), "write", False) is True


def test_new_parses_kind_name_and_fields():
    args = parse(["new", "program", "SMCNv3", "title=SMCNv3", "status=active"])
    assert args.kind == "program" and args.name == "SMCNv3"
    assert args.fields == ["title=SMCNv3", "status=active"]


def test_find_parses_with_and_without_name():
    args = parse(["find", "program"])
    assert args.kind == "program" and args.name is None
    args = parse(["find", "program", "SMCNv3"])
    assert args.name == "SMCNv3"


def test_set_requires_at_least_one_field():
    args = parse(["set", "program", "SMCNv3", "status=complete"])
    assert args.fields == ["status=complete"]


def test_remove_parses_kind_and_name():
    args = parse(["remove", "program", "SMCNv3"])
    assert args.kind == "program" and args.name == "SMCNv3"


def test_template_new_parses_optional_kinds():
    args = parse(["template", "new", "research"])
    assert args.op == "new" and args.name == "research" and args.kinds == []
    args = parse(["template", "new", "research", "program", "gate"])
    assert args.kinds == ["program", "gate"]


def test_template_edit_parses_repeated_set():
    args = parse(["template", "edit", "research",
                  "--set", "program.default_path=specs",
                  "--set", "program.doc_root=research"])
    assert args.op == "edit"
    assert args.assignments == ["program.default_path=specs", "program.doc_root=research"]


def test_template_find_parses_optional_name():
    args = parse(["template", "find"])
    assert args.op == "find" and args.name is None
    args = parse(["template", "find", "research"])
    assert args.name == "research"


def test_template_delete_parses_name():
    args = parse(["template", "delete", "research"])
    assert args.op == "delete" and args.name == "research"


def test_template_apply_parses_name():
    args = parse(["template", "apply", "research"])
    assert args.op == "apply" and args.name == "research"
