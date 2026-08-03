# stablemate workspace — delegates build/test/publish to each member package.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# The one command a fresh clone runs. `hooks` is here rather than left to the reader
# because git carries no hook configuration: a clone starts with core.hooksPath unset,
# so both guards are silently off until someone sets it — and the commit that needed
# stopping is usually the first one, made before anyone has read this file.
.PHONY: install
install: sync browsers hooks ## Set up a fresh clone: sync the venv, fetch Chromium, install the hooks

.PHONY: sync
sync: ## Sync the workspace venv (all members) from the root uv.lock
	uv sync --all-packages

.PHONY: browsers
browsers: ## Download the Chromium `playwright` drives (separate from the pip package)
	# `uv sync` installs the playwright *package*; the browser binary it launches is a
	# separate download, and nothing in the lockfile fetches it. Without this step
	# ostler's live CDP scan and groom's dynamic a11y suite both import fine, get past
	# their `importorskip`, and fail at launch — which reads as a broken test rather
	# than a missing binary. CI does the same thing (release.yml), one step later.
	# chromium only: it is the one browser any test here drives. No `--with-deps`,
	# unlike CI — that installs system libraries with sudo, which a developer's
	# `make install` has no business doing on their own machine.
	uv run playwright install chromium

.PHONY: hooks
hooks: ## Install the git hooks (private-name guard + Conventional Commits check)
	git config core.hooksPath .githooks
	@echo "hooks installed:"
	@echo "  pre-commit  blocks private overlay names. They come from"
	@echo "              \$$STABLEMATE_PRIVATE_NAMES or \$$GIT_DIR/private-names (both"
	@echo "              untracked); with neither configured, this hook is a no-op."
	@echo "  commit-msg  rejects a subject that is not a Conventional Commit, since"
	@echo "              release-please reads the type to decide what gets released."

.PHONY: lint
lint: ## Lint every subproject in one pass: ruff (style, imports) + ty (types)
	# Both run from this root over the whole workspace, against the one ruleset in
	# pyproject.toml — a member package that lints itself lints a different tree than
	# CI does. They answer different questions and neither subsumes the other: ruff
	# reads one file at a time, so the argument that does not match the parameter is
	# invisible to it; ty follows the call across modules and never has an opinion
	# about import order.
	uv run ruff check .
	uv run ty check

.PHONY: test
test: ## Run the packages' test suites, the workflow suites, and the public/private guard
	$(MAKE) lint
	$(MAKE) -C core test
	$(MAKE) -C workhorse test
	$(MAKE) -C workflows test
	$(MAKE) -C ostler test
	$(MAKE) -C farrier test
	$(MAKE) -C groom test
	$(MAKE) test-bench
	$(MAKE) check-public
	$(MAKE) check-no-env
	$(MAKE) check-parsers
	$(MAKE) check-library
	$(MAKE) check-vendor

.PHONY: test-bench
test-bench: ## Run the benchmark harness's own tests (its scoring must be trustworthy)
	# A benchmark whose scoring is wrong is worse than no benchmark: it reports a number
	# that nobody re-derives. These cover the properties that number rests on.
	uv run pytest benchmarks/tests -q

.PHONY: okf-verify
okf-verify: ## Verify every OKF book's coverage against its source (non-zero = incomplete)
	# The predicate a stop condition can be held to. A goal phrased as prose ("the books
	# are complete") is judged by the self-assessment the coverage instrument exists to
	# remove; `make okf-verify exits 0` is something a run can be refused by.
	uv run python scripts/okf_verify.py

.PHONY: check-public
check-public: ## Guard the public/private split (no private names; the base stands alone)
	# Two silent failure modes, both invisible on a machine where the private overlay
	# is configured and shadows everything: a private name reaching this public repo,
	# and a base skill/workflow quietly depending on the overlay.
	uv run python scripts/check_public.py

.PHONY: check-no-env
check-no-env: ## Guard the no-environment rule (a workflow's inputs are parameters)
	# A value read from os.environ is in no checkpoint and no telemetry, so a resume
	# silently takes a different one and nobody can tell what the run worked on.
	uv run python scripts/check_no_env.py

.PHONY: check-parsers
check-parsers: ## Guard the parse-don't-match rule (a format with a grammar gets its parser)
	# A regex over a structured document is that format's parser rewritten without its
	# cases, and it fails silently in both directions — a `//` inside a JSON string read
	# as a comment, a link matched inside a fenced code block.
	uv run python scripts/check_parsers.py

.PHONY: check-library
check-library: ## Guard the base library's front matter (a broken fence loses tags in silence)
	# `_front_matter` answers malformed YAML with `{}`, so a skill whose fence does not
	# parse still installs — minus its description, its applyTo and its tags. Nothing
	# errors; `find_by_tags` just stops returning it, which looks like a repo that
	# installs nothing matching. Both paths are pinned at this repo's own base-library so
	# the gate checks the same files here and in CI, whatever overlay is configured.
	STABLEMATE_BASE_DIR=$(CURDIR)/base-library \
	  uv run farrier library --check --strict --library $(CURDIR)/base-library

.PHONY: vendor
vendor: ## Copy core/stablemate_core into workhorse and farrier (run it with any core change)
	# stablemate-core is not published; each tool carries a copy. The copy is committed
	# rather than synthesized at build time because release-please decides what to ship
	# from the paths a commit touched — a fix committed only under core/ touches no
	# released package and would reach nobody.
	uv run python scripts/vendor_core.py

.PHONY: check-vendor
check-vendor: ## Guard the vendored copies (they must match core/stablemate_core byte for byte)
	# Two copies of a config *writer* is the failure this repo already had once. They are
	# safe only while they are identical, and identical is not something anyone notices
	# by reading a diff of the package they happened to open.
	uv run python scripts/vendor_core.py --check

.PHONY: build
build: ## Build sdists + wheels for the published distributions (into each package's dist/)
	# The same order the release workflow publishes in, and for the same reason: an
	# install of a release has to resolve — workflows trails because it declares
	# workhorse-agent and ostler. core is not here: it is vendored, not published.
	$(MAKE) -C ostler build
	$(MAKE) -C workhorse build
	$(MAKE) -C farrier build
	$(MAKE) -C workflows build

.PHONY: version
version: ## Print every published package's declared version
	@$(MAKE) -s -C ostler version
	@$(MAKE) -s -C workhorse version
	@$(MAKE) -s -C farrier version
	@$(MAKE) -s -C workflows version

.PHONY: release
release: ## Open (or refresh) the release-please PR — merging it is what publishes
	# Nothing is built, versioned or uploaded here. This dispatches
	# .github/workflows/release.yml, which reads the Conventional Commits since each
	# package's last tag and opens ONE pull request carrying the version bumps and
	# changelogs. Merging that PR tags, releases, and uploads to PyPI over OIDC —
	# there is no token on this machine to leak.
	gh workflow run release.yml --ref main
	@echo "dispatched. The release PR appears in ~30s; find it with:"
	@echo "  gh pr list --label 'autorelease: pending'"

# >>> farrier: agent launcher include (generated) >>>
# Surfaces agent-install / agent-check from the generated
# launcher. Re-created by `farrier install`; remove this block to opt out.
include .agents/agents.mk
# <<< farrier: agent launcher include <<<
