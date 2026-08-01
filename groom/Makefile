# groom — build and test tasks.
#
# groom is versioned by release-please but has no publish step in
# .github/workflows/release.yml: the name `groom` on PyPI belongs to an unrelated
# project. Install it from this checkout (`pipx install ./groom`) until that is settled.

.DEFAULT_GOAL := help

DIST        := dist
NAME        := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)
VERSION     := $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create/sync the workspace venv from the root uv.lock
	uv sync

# Serve knobs — override on the command line, e.g. `make run PORT=9000`.
# Default 0.0.0.0 so the in-container sidecars reach groom over the docker bridge
# (HOST=127.0.0.1 to bind loopback only). groom has no auth — trusted networks only.
HOST ?= 0.0.0.0
PORT ?= 8787

# Generous because one file in the suite boots a real groom and drives Chromium
# through five panes; the rest finish in seconds.
TEST_TIMEOUT ?= 300

.PHONY: run
run: ## Start the groom web dashboard (HOST=… PORT=… to override; binds 0.0.0.0:8787)
	uv run groom serve --host $(HOST) --port $(PORT)

.PHONY: lint
lint: ## Lint: ruff
	uv run ruff check .

.PHONY: test
test: ## Run the standalone test suite
	@for t in tests/test_*.py; do echo ">> $$t"; timeout $(TEST_TIMEOUT) uv run python $$t || exit 1; done

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

# There is deliberately no `verify-install` here. The sibling packages' version of it
# (`uv run --with groom --refresh-package groom`) would install the unrelated PyPI
# project of the same name and report on it — a smoke test that passes on someone
# else's code is worse than none.

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"
