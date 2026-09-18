import type { CreateWidgetResult, FieldErrors, Widget } from "./types";

// Same api-service web-app's config.js points at, reached the same way: straight from the
// client's own network, not proxied through mobile-app's bundler or any device-side relay.
export const API_BASE = "http://localhost:18101";

// Mirrors app.js's loadWidgets fetch, minus the DOM: read the directory, or throw so the
// caller can fall back to the error state.
export async function fetchWidgets(): Promise<Widget[]> {
  const res = await fetch(`${API_BASE}/api/widgets`);
  if (!res.ok) throw new Error(`status ${res.status}`);
  const body = (await res.json()) as { widgets: Widget[] };
  return body.widgets;
}

// Mirrors new.js's submitNewWidget: POST the two fields api-service accepts and return
// either the 201 widget or the 422 field errors, without ever throwing on a 422 — that
// response is not a failure, it is data the form renders.
export async function createWidget(name: string, quantity: number): Promise<CreateWidgetResult> {
  const res = await fetch(`${API_BASE}/api/widgets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, quantity }),
  });
  const body = await res.json();
  if (res.status === 201) {
    return { ok: true, widget: body.widget as Widget };
  }
  return { ok: false, errors: (body.errors ?? {}) as FieldErrors };
}

// Ping used the same way app.js's healthcheck would be, if it had one — kept separate
// from fetchWidgets so a screen can distinguish "api-service is down" from "the directory
// is genuinely empty" without reading response bodies to do it.
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/healthz`);
    return res.ok;
  } catch {
    return false;
  }
}
