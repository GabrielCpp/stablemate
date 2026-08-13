"""The one page the service serves, rendered on the server.

No build step and no client framework, which is a property the benchmark depends on: the
app has to come up from a stock Python image so a QA sandbox can reach it without a
toolchain. What it still gives QA is a real accessibility tree — landmarks, a labelled
region, one button per seat with an accessible name — so `visible(...)`, the layout digest
and the screenshot half of the harness all have something honest to read.
"""

from __future__ import annotations

from html import escape
from typing import Any

from app.store import FREE

#: Inline, because the page must render identically with no network at all — a sandboxed
#: browser reaches the service through a forwarded port and nothing else.
STYLE = """
body { font-family: system-ui, sans-serif; margin: 0; color: #16202c; background: #f6f7f9; }
header { padding: 1.5rem 2rem; background: #16202c; color: #fff; }
h1 { font-size: 1.4rem; margin: 0; }
main { padding: 2rem; max-width: 46rem; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
.seat { padding: 1rem 0.5rem; border: 1px solid #c3cbd6; border-radius: 6px;
        background: #fff; font: inherit; cursor: pointer; text-align: center; }
.seat[data-state="held"] { background: #fdf1d6; border-color: #d8a83a; }
.seat[data-state="booked"] { background: #e6e9ee; color: #6b7686; cursor: not-allowed; }
.seat .state { display: block; font-size: 0.75rem; text-transform: uppercase; }
.summary { margin-top: 1.5rem; font-size: 0.95rem; }
"""


def render(seats: list[dict[str, Any]]) -> str:
    """The seat map as one HTML document.

    Every seat in the ledger gets a button, including the ones nobody can take: a map that
    silently drops booked seats renders a smaller theatre than the one that exists, and
    the row/number layout stops meaning anything.
    """
    buttons = "\n".join(_seat_button(seat) for seat in seats)
    free = sum(1 for seat in seats if seat["state"] != "booked")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seat map</title>
<style>{STYLE}</style>
</head>
<body>
<header role="banner"><h1>Riverside Playhouse — tonight</h1></header>
<main>
<section role="region" aria-label="Seat map">
<h2>Seat map</h2>
<div class="grid">
{buttons}
</div>
</section>
<p class="summary" role="status">{free} of {len(seats)} seats free</p>
</main>
</body>
</html>
"""


def _seat_button(seat: dict[str, Any]) -> str:
    """One seat. The accessible name is the seat id and nothing else.

    Folding the state into the name — "Seat A1, free" — would make every locator in the
    book change the moment the seat changed state, so the state travels as text inside the
    button and as `data-state`, and the name stays the stable thing to address it by.
    """
    seat_id = escape(str(seat["id"]))
    state = escape(str(seat["state"]))
    disabled = " disabled" if seat["state"] != FREE else ""
    return (
        f'<button class="seat" type="button" data-state="{state}" '
        f'aria-label="Seat {seat_id}"{disabled}>'
        f'{seat_id}<span class="state">{state}</span></button>'
    )
