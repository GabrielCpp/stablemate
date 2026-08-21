# stablemate workspace — delegates build/test/publish to each member package.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# The one command a fresh clone runs. `hooks` is here rather than left to the reader
# because git carries no hook configuration: a clone starts with nothing installed, so
# every guard is silently off until someone runs it — and the commit that needed
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
hooks: ## Install the git hooks (private names, Conventional Commits, generated files)
	# `pre-commit`, not `core.hooksPath`: they are mutually exclusive — pre-commit
	# refuses outright while that config is set — and only one of them can carry a
	# third guard farrier installs on its own schedule. The two scripts under
	# .githooks/ did not move; .pre-commit-config.yaml is now what runs them.
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
	@echo "hooks installed:"
	@echo "  private-names         blocks private overlay names. They come from"
	@echo "                        \$$STABLEMATE_PRIVATE_NAMES or \$$GIT_DIR/private-names"
	@echo "                        (both untracked); with neither configured, a no-op."
	@echo "  conventional-commit   rejects a subject that is not a Conventional Commit,"
	@echo "                        since release-please reads the type to decide what"
	@echo "                        gets released."
	@echo "  farrier-hooks         blocks a hand-edit to a farrier-generated file, and"
	@echo "                        names the library source the edit belongs in."

.PHONY: lint
lint: ## Lint every subproject in one pass: ruff (style, imports) + ty (types)
	# Both run from this root over the whole workspace, against the one ruleset in
	# pyproject.toml — a member package that lints itself lints a different tree than
	# CI does. They answer different questions and neither subsumes the other: ruff
	# reads one file at a time, so the argument that does not match the parameter is
	# invisible to it; ty follows the call across modules and never has an opinion
	# about import order.
	#
	# `--all-packages` for the same reason `check-public` needs it: a bare `uv run`
	# syncs this root and its dev group, so every workspace member's own dependencies
	# — jinja2, GitPython, opentelemetry — are absent unless someone has already run
	# `make install`. ruff never notices, but ty resolves imports, so in a fresh
	# checkout it reports hundreds of unresolved-import errors that say nothing about
	# the code. The lint gate has to mean the same thing on a clean machine as on a
	# set-up one.
	uv run --all-packages ruff check .
	uv run --all-packages ty check

.PHONY: test
test: ## Run the packages' test suites, the workflow suites, and the public/private guard
	$(MAKE) lint
	$(MAKE) -C core test
	$(MAKE) -C workhorse test
	$(MAKE) -C workflows test
	$(MAKE) -C ostler test
	$(MAKE) -C farrier test
	$(MAKE) -C groom test
	$(MAKE) -C saddlebag test
	$(MAKE) -C paddock test
	$(MAKE) test-scripts
	$(MAKE) check-public
	$(MAKE) check-no-env
	$(MAKE) check-no-giveup
	$(MAKE) check-prompt-agnostic
	$(MAKE) check-parsers
	$(MAKE) check-portability
	$(MAKE) check-library
	$(MAKE) check-agent-outputs
	$(MAKE) check-skills
	$(MAKE) check-vendor

.PHONY: bench-doctor
bench-doctor: ## Measure `ostler doctor` against a book: make bench-doctor DOCS=<path> [JSON=1]
	# The baseline the parse-cache increments are checked against. Every timing steering
	# that work came from ad-hoc profiling nobody else can reproduce; this target is that
	# profiling, committed, so a before/after is a diff rather than a paragraph.
	#
	# DOCS is required and has no default. The measured book lives outside this repo, so a
	# baked-in path would measure whatever happened to be underfoot and report a number
	# nobody can place — stopping is the cheaper failure.
	@test -n "$(DOCS)" || { \
	  echo "make bench-doctor: DOCS=<path to the repo holding the book> is required;" >&2; \
	  echo "  there is no default — the measured book lives outside this repo." >&2; \
	  exit 2; }
	uv run python scripts/bench_ostler_doctor.py $(DOCS) $(if $(JSON),--json,)

.PHONY: okf-verify
okf-verify: ## Verify every OKF book's coverage against its source (non-zero = incomplete)
	# The predicate a stop condition can be held to. A goal phrased as prose ("the books
	# are complete") is judged by the self-assessment the coverage instrument exists to
	# remove; `make okf-verify exits 0` is something a run can be refused by.
	uv run python scripts/okf_verify.py

.PHONY: test-scripts
test-scripts: ## Run the repo-level guard scripts' own tests
	# The guards in `scripts/` are the only code here with no package to be tested by, and
	# they are exactly the code whose failure mode is silence: a hook check that looks in
	# the wrong place reports every guard missing on a clone where they all run.
	uv run pytest scripts/tests -q

.PHONY: check-public
check-public: ## Guard the public/private split (no private names; the base stands alone)
	# Two silent failure modes, both invisible on a machine where the private overlay
	# is configured and shadows everything: a private name reaching this public repo,
	# and a base skill/workflow quietly depending on the overlay.
	#
	# `--all-packages` because the base-stands-alone half imports farrier and
	# stablemate_core. A bare `uv run` syncs this root and its dev group only, so the
	# check resolves those two purely by accident: it works in a clone that has run
	# `make install` (`uv sync --all-packages`) and dies with ModuleNotFoundError in a
	# fresh checkout that has not. A gate that passes only on a machine already set up
	# is the one thing this particular gate must not be.
	uv run --all-packages python scripts/check_public.py

.PHONY: check-no-env
check-no-env: ## Guard the no-environment rule (a workflow's inputs are parameters)
	# A value read from os.environ is in no checkpoint and no telemetry, so a resume
	# silently takes a different one and nobody can tell what the run worked on.
	uv run python base-library/library/skills/stablemate/workhorse-scripting/scripts/check_no_env.py

.PHONY: check-no-giveup
check-no-giveup: ## Guard the "a workflow never gives up" rule (blocked, not failed)
	# A budget exhaustion must escalate to the operator gate, never end the run outright.
	# This can only catch the vocabulary of the deleted pattern reappearing, not every
	# way the rule could be broken again — see the script's docstring for what it misses.
	uv run python scripts/check_no_giveup.py

.PHONY: check-prompt-agnostic
check-prompt-agnostic: ## Guard invariant 1 (the coder workflow names no stack of its own)
	# A stack name in a coder prompt is a deployment assumption the workflow charges every
	# repo for: a Go command sent to a Python service, a `package.json` marker offered to a
	# repo that has none. What runs comes out of the repo's own `agents.yml`; this is what
	# stops the guessed list from growing back, one helpful example at a time.
	uv run python scripts/check_prompt_agnostic.py

.PHONY: check-parsers
check-parsers: ## Guard the parse-don't-match rule (a format with a grammar gets its parser)
	# A regex over a structured document is that format's parser rewritten without its
	# cases, and it fails silently in both directions — a `//` inside a JSON string read
	# as a comment, a link matched inside a fenced code block.
	uv run python base-library/library/skills/stablemate/structured-parsing/scripts/check_parsers.py

.PHONY: check-portability
check-portability: ## Guard the portability tiers (a shipped package runs on the user's OS, not ours)
	# The container is Ubuntu and CI is ubuntu-latest, so a POSIX-only call in a package
	# someone pip-installs fails for the first person on a Mac or Windows and for nobody
	# here. Process supervision genuinely needs those calls and declares itself.
	uv run python base-library/library/skills/stablemate/portability/scripts/check_portability.py

.PHONY: check-library
check-library: ## Guard the base library's front matter (a broken fence loses tags in silence)
	# `_front_matter` answers malformed YAML with `{}`, so a skill whose fence does not
	# parse still installs — minus its description, its applyTo and its tags. Nothing
	# errors; `find_by_tags` just stops returning it, which looks like a repo that
	# installs nothing matching. Both paths are pinned at this repo's own base-library so
	# the gate checks the same files here and in CI, whatever overlay is configured.
	STABLEMATE_BASE_DIR=$(CURDIR)/base-library \
	  uv run farrier library --check --strict --library $(CURDIR)/base-library

.PHONY: check-agent-outputs
check-agent-outputs: ## Guard the generated agent adapters (a hand-edit to one is lost on the next render)
	# AGENTS.md, CLAUDE.md and every .claude/skills/** file are rendered from the
	# library; an edit made in the copy is silently overwritten by the next
	# `make agent-install`, and the agent that wrote it is long gone. The commit hook
	# catches this on a machine that has the overlay — this catches --no-verify, a
	# clone with no hooks installed, and CI.
	#
	# The base half is pinned in-tree, for the same reason check-library pins it: the
	# gate must read the same files here and in CI whatever base is configured. The
	# overlay half deliberately is not — this repo's `packs:` live there, so a render
	# that could not see it would not be a stricter check, it would be no check at all.
	# `--skip-unresolvable` is what that costs: on a public clone the overlay is absent,
	# the render cannot be done, and the guard says so and passes rather than blocking
	# every commit a contributor makes.
	STABLEMATE_BASE_DIR=$(CURDIR)/base-library \
	  uv run farrier install --repo $(CURDIR) --check --skip-unresolvable

.PHONY: check-skills
check-skills: ## Guard the base library's writing doctrine (sprawl, dead disclosure, direction)
	# Three failures that leave a skill installing cleanly and reading fine to a human: a
	# SKILL.md long enough that the agent attends to all of it only on some runs, a
	# bundled reference nothing links to (installed everywhere, read nowhere), and a skill
	# firing a prompt — inverting a human entry point into an autonomous one.
	uv run python base-library/library/skills/stablemate/agent-writing/scripts/check_skills.py

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
