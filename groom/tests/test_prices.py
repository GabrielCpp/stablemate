"""The rate card, and the estimate it puts beside a turn's reported cost.

What is asserted here is the separation more than the arithmetic: an estimate lands in
its own column, an unknown model yields nothing rather than a guess, and the turns that
could not be priced stay countable. A number that quietly becomes a subset of the turns
is the failure this module exists to prevent.

Run: uv run pytest tests/test_prices.py
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from groom import prices, store, turns


@contextlib.contextmanager
def _env(overrides: str = "") -> Iterator[Path]:
    """A throwaway groom.db and price-override file, both discarded afterwards."""
    prev_db, prev_prices = os.environ.get("GROOM_DB"), os.environ.get(prices.PRICES_FILE_ENV)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prices.toml"
        if overrides:
            path.write_text(overrides, encoding="utf-8")
        os.environ["GROOM_DB"] = str(Path(tmp) / "groom.db")
        os.environ[prices.PRICES_FILE_ENV] = str(path)
        store.reset()
        prices.reset()
        try:
            yield path
        finally:
            store.reset()
            prices.reset()
            for key, value in (("GROOM_DB", prev_db), (prices.PRICES_FILE_ENV, prev_prices)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _turn(
    span_id: str,
    model: str,
    tokens: dict[str, int],
    cost: float | None = None,
    session: str = "",
) -> dict:
    attrs: dict[str, object] = {"model": model, "workhorse.node": "plan-qa"}
    if session:
        attrs["session.id"] = session
        attrs["backend"] = "acme-cli"
    attrs.update({f"usage.{key}": value for key, value in tokens.items()})
    if cost is not None:
        attrs["total_cost_usd"] = cost
    return {
        "span_id": span_id, "trace_id": "tr", "run_id": "R1", "workflow": "coder",
        "node": "plan-qa", "name": "agent_turn", "start_ts": 1.0, "end_ts": 2.0,
        "attrs": attrs,
    }


_TOKENS = {
    "input_tokens": 1_000_000,
    "output_tokens": 1_000_000,
    "cache_read_input_tokens": 1_000_000,
    "cache_creation_input_tokens": 1_000_000,
}


def _est(span_id: str) -> float | None:
    row = store._connection().execute(
        "SELECT est_cost_usd FROM spans WHERE span_id = ?", (span_id,)
    ).fetchone()
    return row["est_cost_usd"]


def _priced_model(span_id: str) -> str | None:
    row = store._connection().execute(
        "SELECT priced_model FROM spans WHERE span_id = ?", (span_id,)
    ).fetchone()
    return row["priced_model"]


# ------------------------------------------------------------------------ the table
def test_a_model_the_table_does_not_name_is_not_priced():
    with _env():
        assert prices.price_for("claude-sonnet-5") is not None
        # No family guessing and no averaging of neighbours: an estimate whose
        # provenance is a resemblance is worse than no estimate.
        assert prices.price_for("some-model-4") is None
        assert prices.estimate("some-model-4", 1000, 1000) is None


def test_a_dated_or_routed_id_prices_as_the_model_it_names():
    with _env():
        dated = prices.price_for("claude-sonnet-4-5-20250929")
        assert dated is not None and dated.input == 3.00
        # The tail of a route is the model the provider ran, so dropping the route is
        # a narrowing of the same name rather than a guess at a different one.
        assert prices.price_for("openrouter/anthropic/claude-haiku-4-5") is not None


def test_the_override_file_extends_and_corrects_the_built_in_table():
    with _env('[models."acme/fast-1"]\ninput = 2.0\noutput = 8.0\n'):
        added = prices.price_for("acme/fast-1")
        assert added is not None
        assert (added.input, added.output) == (2.0, 8.0)
        # Cache rates default to the published multipliers off the input rate.
        assert added.cache_read == 0.2 and added.cache_write == 4.0

    with _env('[models."claude-haiku-4-5"]\ninput = 9.0\noutput = 9.0\n'):
        corrected = prices.price_for("claude-haiku-4-5")
        assert corrected is not None and corrected.input == 9.0


def test_a_malformed_override_file_is_ignored_rather_than_fatal():
    with _env("this is not toml {{{"):
        # Pricing is a convenience over telemetry; a typo in a rate card must not take
        # down the dashboard that reads it.
        assert prices.price_for("claude-sonnet-5") is not None

    with _env('[models."acme/fast-1"]\ninput = 2.0\n'):  # no output rate
        assert prices.price_for("acme/fast-1") is None
        assert prices.price_for("claude-sonnet-5") is not None


def test_a_turn_reporting_no_tokens_at_all_gets_no_estimate():
    with _env():
        # 0.0 over an unknown number of tokens is the exact false zero the estimate
        # exists to distinguish from a real one.
        assert prices.estimate("claude-sonnet-5", None, None, None, None) is None
        # Some classes reported and not others prices the ones that were.
        assert prices.estimate("claude-sonnet-5", 1_000_000, None) == 3.0


# ------------------------------------------------------------------------- the column
def test_an_estimate_is_stamped_at_ingest_beside_the_reported_cost():
    with _env():
        store.insert_spans([_turn("a" * 16, "claude-sonnet-5", _TOKENS, cost=12.34)])
        # 3.00 in + 15.00 out + 0.30 cache-read + 6.00 cache-write, one million each.
        assert _est("a" * 16) == 24.30
        row = store._connection().execute(
            "SELECT total_cost_usd, est_cost_usd FROM spans"
        ).fetchone()
        # Two different claims about the same turn — what a vendor billed, and what a
        # rate card says the tokens are worth. Neither replaces the other.
        assert row["total_cost_usd"] == 12.34 and row["est_cost_usd"] == 24.30


def test_reprice_fills_in_turns_that_predate_the_column():
    with _env():
        store.insert_spans([_turn("b" * 16, "claude-sonnet-5", _TOKENS)])
        # A span from before the column shipped: derived, so unlike the promoted
        # columns there is no attribute to fall back to.
        store._connection().execute("UPDATE spans SET est_cost_usd = NULL")
        store._connection().commit()

        result = store.reprice()
        assert result["priced"] == 1 and result["considered"] == 1
        assert _est("b" * 16) == 24.30
        # And it is idempotent: a second pass finds nothing left missing.
        assert store.reprice()["considered"] == 0


def test_reprice_all_redoes_turns_after_a_rate_changes():
    with _env() as path:
        store.insert_spans([_turn("c" * 16, "claude-haiku-4-5", _TOKENS)])
        first = _est("c" * 16)
        assert first is not None

        path.write_text('[models."claude-haiku-4-5"]\ninput = 2.0\noutput = 10.0\n')
        prices.reset()
        # Correcting a rate leaves every row priced at the old one wrong, which the
        # missing-only default would never revisit.
        assert store.reprice()["considered"] == 0
        assert store.reprice(missing_only=False)["priced"] == 1
        assert _est("c" * 16) != first


def test_the_turns_no_rate_covers_stay_countable():
    with _env():
        store.insert_spans([
            _turn("d" * 16, "claude-sonnet-5", _TOKENS),
            _turn("e" * 16, "openai/gpt-9-imaginary", _TOKENS),
            _turn("f" * 16, "", _TOKENS),
        ])
        # The point of the list: coverage of the estimate is a number, not an
        # impression, and each line in it is a model to add to prices.toml.
        assert store.unpriced_models() == {
            "openai/gpt-9-imaginary": 1, "(no model recorded)": 1
        }
        assert _est("e" * 16) is None and _est("f" * 16) is None

        result = store.reprice(missing_only=False)
        assert result["priced"] == 1
        assert result["unpriced"] == {"openai/gpt-9-imaginary": 1, "(no model recorded)": 1}


def test_node_costs_reports_the_estimate_beside_the_bill_and_never_folded_in():
    with _env():
        store.insert_spans([
            _turn("g" * 16, "claude-sonnet-5", _TOKENS, cost=12.34),
            _turn("h" * 16, "openai/gpt-9-imaginary", _TOKENS, cost=0.0),
        ])
        row = store.node_costs(run="R1")[0]
        assert row["cost_usd"] == 12.34
        assert row["est_cost_usd"] == 24.30
        # One of the two turns had a model the card names, and saying so is what keeps
        # est$ from reading as a total.
        assert row["est_turns"] == 1
        assert row["turns"] == 2


# ------------------------------------------------------- resolving an alias to a model
@contextlib.contextmanager
def _cli_store(sessions: dict[str, list[str]]) -> Iterator[None]:
    """A fake CLI whose store answers a session id with a transcript naming models."""
    from workhorse.runner import transcript as capture

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for session, models in sessions.items():
            lines = [json.dumps({"message": {"model": model}}) for model in models]
            (root / f"{session}.jsonl").write_text("\n".join(lines), encoding="utf-8")
        previous = capture._STORES.get("acme-cli")
        capture._STORES["acme-cli"] = lambda session: [
            path for path in [root / f"{session}.jsonl"] if path.is_file()
        ]
        try:
            yield
        finally:
            if previous is None:
                capture._STORES.pop("acme-cli", None)
            else:
                capture._STORES["acme-cli"] = previous


def test_an_alias_is_priced_by_the_model_its_session_store_names():
    with _env(), _cli_store({"s1": ["claude-sonnet-5"]}):
        store.insert_spans([_turn("i" * 16, "sonnet", _TOKENS, session="s1")])
        # The span records what the CLI was invoked with, which no rate card can name.
        assert _est("i" * 16) is None

        result = turns.resolve_models()
        assert result["priced"] == 1 and result["sessions_read"] == 1
        assert result["resolved"] == {"sonnet -> claude-sonnet-5": 1}
        assert _est("i" * 16) == 24.30
        # And the estimate says which rate produced it, so it can be checked later.
        assert _priced_model("i" * 16) == "claude-sonnet-5"
        assert store.unpriced_models() == {}


def test_an_alias_a_session_leaves_ambiguous_is_not_priced():
    with _env(), _cli_store({"s1": ["claude-opus-5", "claude-sonnet-5"]}):
        store.insert_spans([
            _turn("j" * 16, "opus", _TOKENS, session="s1"),
            _turn("k" * 16, "claude", _TOKENS, session="s1"),
        ])
        result = turns.resolve_models()
        # A session may run more than one model, so the alias has to name the candidate:
        # `opus` resolves, `claude` matches both and a coin flip between two rates is a
        # number that reads as evidence and is not.
        assert result["resolved"] == {"opus -> claude-opus-5": 1}
        assert _est("j" * 16) == 40.50
        assert _est("k" * 16) is None
        assert result["unresolved"] == {"claude": 1}


def test_a_session_naming_only_models_with_no_rate_stays_unresolved():
    with _env(), _cli_store({"s1": ["acme/fast-1"]}):
        store.insert_spans([_turn("l1" + "m" * 14, "fast", _TOKENS, session="s1")])
        result = turns.resolve_models()
        # Resolution recovers a *name*; it never invents a rate for one. This turn still
        # needs a line in prices.toml, and saying so is the whole output.
        assert result["priced"] == 0 and result["unresolved"] == {"fast": 1}
        assert _est("l1" + "m" * 14) is None


def test_resolution_reads_no_session_for_a_turn_that_records_none():
    with _env(), _cli_store({"s1": ["claude-sonnet-5"]}):
        store.insert_spans([_turn("n" * 16, "sonnet", _TOKENS)])
        result = turns.resolve_models()
        assert result["sessions_read"] == 0 and result["unresolved"] == {"sonnet": 1}


def test_a_dry_run_resolution_writes_nothing():
    with _env(), _cli_store({"s1": ["claude-sonnet-5"]}):
        store.insert_spans([_turn("o" * 16, "sonnet", _TOKENS, session="s1")])
        assert turns.resolve_models(dry_run=True)["priced"] == 1
        assert _est("o" * 16) is None


def test_repricing_a_resolved_turn_uses_the_model_not_the_alias():
    with _env() as path, _cli_store({"s1": ["claude-haiku-4-5"]}):
        store.insert_spans([_turn("p" * 16, "haiku", _TOKENS, session="s1")])
        turns.resolve_models()
        first = _est("p" * 16)
        assert first is not None

        path.write_text('[models."claude-haiku-4-5"]\ninput = 2.0\noutput = 10.0\n')
        prices.reset()
        result = store.reprice(missing_only=False)
        # Falling back to the alias here would drop the estimate the resolution earned
        # and report the turn as unpriceable all over again.
        assert result["priced"] == 1 and result["unpriced"] == {}
        assert _est("p" * 16) != first


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
