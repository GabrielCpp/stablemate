Judge whether each story names the services it changes.

- The story's `services:` list is bounded by the union of the services of the seeds it covers. It must name the books the story truly changes, no more and no fewer.
- A seed split into one story per platform gives each story only its own platform's books. A story that lists fewer books than its seeds is correct when it changes fewer.
- A story that changes a web or mobile app lists that app's book, because the mockup requirement follows from it. Name a story that changes a screen but lists no UI book.
- A story that needs a book none of its seeds lists is a finding against the seed, naming the book it should list. The derivation replaces a list that leaves the seeds' union.
- A book name must be a directory under `docs/services/`. The deterministic gate checks the spelling. You check the meaning.
