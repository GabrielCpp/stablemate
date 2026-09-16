// The one address this bundle is configured with: where api-service answers, from the
// browser's own network — not from inside the compose network, since the fetches below
// are made by the page, not by web-app's static server.
window.API_BASE = "http://localhost:18101";
