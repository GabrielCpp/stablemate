# The SvelteKit fixture

A small SvelteKit 2 app on adapter-node that reads the todo API at the address in `TODO_API`. Its home page renders a list from data its server loaded, and its assign page fetches a list through the app's own gateway. The build is committed under `build/` so tests run it with `node build/index.js` and need no install. `PUBLIC_KIT_BUG` plants a defect at runtime.

To rebuild, copy `package.json`, `svelte.config.js`, `vite.config.js` and `src` to a scratch folder, install the dev dependencies there with the exact versions of `package.json`, and run `npx vite build`. Copy the resulting `build/` back here and delete its `.map`, `.gz` and `.br` files.
