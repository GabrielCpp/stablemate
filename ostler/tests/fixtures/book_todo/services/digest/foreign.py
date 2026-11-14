"""The todo as the digest knows it: a record the todo API owns, and the one way the digest reads its answer."""

from __future__ import annotations

from typing import Any

from ostler.book import Foreign

from ..api.model.todo import TodoRecord

TODO = Foreign(TodoRecord, owner="services.api", reads=("id", "title", "status"))


def late_only(listed: Any) -> dict[str, Any]:
    """the overdue todos the owner lists, each under its id and its title as a label"""
    late = [t for t in listed if t["status"] == "overdue"]
    return {"late": [{"id": t["id"], "label": t["title"]} for t in late], "count": len(late)}


def one_entry(read: Any) -> dict[str, Any]:
    """the todo the owner reads, under its id and its title as a label, late when it is overdue"""
    return {"id": read["id"], "label": read["title"], "late": read["status"] == "overdue"}
