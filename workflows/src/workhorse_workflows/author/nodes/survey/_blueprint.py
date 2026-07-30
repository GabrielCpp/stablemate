"""The surveyor sub-flow's own `Blueprint`.

Separate from the main author blueprint because the two graphs are separate machines
that happen to ship in one package: a reader looking at `flows/surveyor.py` should be
able to see which nodes belong to it. `Registry.add_blueprints` merges both into one
index, so node **names** are still globally unique across the pair — which is why the
surveyor's start node is `load_survey_config` and not `load_config`.
"""
from __future__ import annotations

from workhorse.pyflow import Blueprint

blueprint = Blueprint("surveyor")

__all__ = ["blueprint"]
