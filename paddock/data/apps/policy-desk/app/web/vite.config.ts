import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The bundle is served by the Go binary, from the same origin as the API, so `/api` is a
// relative path in production. In `npm run dev` it is proxied to the same port the
// container publishes.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:18084",
      "/healthz": "http://localhost:18084",
    },
  },
});
