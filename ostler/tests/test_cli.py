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
