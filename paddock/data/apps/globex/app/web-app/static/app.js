// The widget register: reads the directory from api-service and renders it as a table, or
// the empty notice when there are none, or the alert when the read itself fails — the same
// three-state shape policy-desk's register uses, and for the same reason: a stale table
// that looks current is the one failure mode a register must not have.

async function loadWidgets() {
  const table = document.querySelector("table");
  const empty = document.querySelector("p.empty-notice");
  const alert = document.querySelector('p[role="alert"]');
  try {
    const res = await fetch(`${window.API_BASE}/api/widgets`);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const body = await res.json();
    renderWidgetTable(body.widgets, table, empty);
    alert.hidden = true;
  } catch (err) {
    alert.hidden = false;
    alert.textContent = "Could not read the widget directory.";
  }
}

function renderWidgetTable(widgets, table, empty) {
  const rows = document.getElementById("widget-rows");
  rows.innerHTML = "";
  if (!widgets || widgets.length === 0) {
    table.hidden = true;
    empty.hidden = false;
    return;
  }
  table.hidden = false;
  empty.hidden = true;
  for (const w of widgets) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${w.name}</td><td>${w.quantity}</td>`;
    rows.appendChild(tr);
  }
}

loadWidgets();
