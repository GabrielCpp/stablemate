# stablemate-core — build, test, and publish tasks.
#
# Publishing reads the PyPI token from ~/.pypirc (the [pypi] password entry),
# since `uv publish` does not read .pypirc itself.
#
# This package has no CLI: workhorse and farrier depend on it, so it must be published
# BEFORE either of them, or their installs resolve nothing.

.DEFAULT_GOAL := help

DIST        := dist
PYPI_TOKEN   = $(shell awk '/password/{print $$3}' $(HOME)/.pypirc)
NAME        := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)
VERSION     := $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
SCRIPTS     := $(abspath $(CURDIR)/../scripts)

# Release knobs (see scripts/release.sh) — exported so they reach the scripts
# whether passed as `make release LEVEL=minor` or `LEVEL=minor make release`.
export DRY_RUN LEVEL RELEASE_VERSION PUBLISH ALLOW_DIRTY NO_PUSH ZEROVER

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create/sync the venv from the root uv.lock
	uv sync --extra test

.PHONY: test
test: ## Run the test suite
	uv run --extra test pytest tests -q

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: publish-test
publish-test: build ## Publish to TestPyPI
	@UV_PUBLISH_TOKEN="$(PYPI_TOKEN)" uv publish --publish-url https://test.pypi.org/legacy/

.PHONY: publish
publish: build ## Publish to PyPI (token from ~/.pypirc)
	@UV_PUBLISH_TOKEN="$(PYPI_TOKEN)" uv publish

.PHONY: next-version
next-version: ## Print the next version inferred from commit history (LEVEL=… to force)
	@$(SCRIPTS)/next-version.sh $(NAME) $(CURDIR) $(VERSION)

.PHONY: bump
bump: ## Stamp the inferred next version into pyproject.toml (no commit — review, then commit)
	@$(SCRIPTS)/set-version.sh $(CURDIR) $$($(SCRIPTS)/next-version.sh $(NAME) $(CURDIR) $(VERSION))

.PHONY: release
release: ## Bump from history, build, publish, commit, tag, push (DRY_RUN=1, LEVEL=…, RELEASE_VERSION=…, PUBLISH=testpypi)
	@$(SCRIPTS)/release.sh $(NAME) $(CURDIR)

.PHONY: release-test
release-test: ## Same as release, but publish to TestPyPI
	@PUBLISH=testpypi $(SCRIPTS)/release.sh $(NAME) $(CURDIR)

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info
