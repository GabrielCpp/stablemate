// Submits a new widget straight to api-service, cross-origin, from the browser — the page
// makes this request itself; nothing server-side on web-app's side relays it.

async function submitNewWidget(event) {
  event.preventDefault();
  const name = document.getElementById("name").value;
  const quantity = Number(document.getElementById("quantity").value);
  clearFieldErrors();

  const res = await fetch(`${window.API_BASE}/api/widgets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, quantity }),
  });

  if (res.status === 201) {
    window.location.href = "index.html";
    return;
  }
  const body = await res.json();
  showFieldErrors(body.errors || {});
}

function clearFieldErrors() {
  document.getElementById("name-error").textContent = "";
  document.getElementById("quantity-error").textContent = "";
}

function showFieldErrors(errors) {
  if (errors.name) document.getElementById("name-error").textContent = errors.name;
  if (errors.quantity) document.getElementById("quantity-error").textContent = errors.quantity;
}

document.getElementById("new-widget-form").addEventListener("submit", submitNewWidget);
