# docs

The spec pass of the coder workflow. One owner agent writes a story's behaviour model and the claims it implies into the service's Python book before any code exists, and the run checks the book with `ostler book check`. A story that names a service with no book stops here, and a story that names no service skips the pass.
