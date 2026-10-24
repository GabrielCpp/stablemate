"""bookmarks — the cross-surface task: a Go api and a React Router web app, four journeys, an hour."""

from __future__ import annotations

import _greenfield as gf
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="bookmarks",
    seed="bookmarks",
    config="configs/opencode.toml",
)

FIXTURE = gf.Fixture(
    milestone="apps/bookmarks/docs/milestones/keep-saved-pages",
    packs="product-planning,stablemate,infra",
    docs_scaffold="shared-docs:docs",
    surfaces=(
        gf.Surface(
            service="api",
            service_root="api",
            packs="go",
            scaffolds="go-service:api",
            init_cmd="go mod init example.com/bookmarks/api",
            marker="go.mod",
        ),
        gf.Surface(
            service="web",
            service_root="web",
            packs="react-router,general",
            scaffolds="react-router-web:web",
            init_cmd="npx --yes create-react-router@latest . --yes --no-install --no-git-init",
            marker="package.json",
        ),
    ),
    checks=(
        gf.Check(name="api-build", cmd="cd api && go build ./...", timeout_s=300.0),
        gf.Check(name="api-test", cmd="cd api && go test ./...", timeout_s=600.0),
        gf.Check(name="web-typecheck",
                 cmd="cd web && npm install --no-audit --no-fund && npm run typecheck",
                 timeout_s=900.0),
        gf.Check(name="web-build", cmd="cd web && npm run build", timeout_s=600.0),
    ),
    judge_cli="opencode",
    judge_model="openai/gpt-5.6-sol",
    judge_effort="medium",
    budget_s={"genesis": 3600.0, "author": 3600.0, "coder": 22000.0},
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def build(run: Run) -> None:
    gf.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return gf.score_round(run, FIXTURE)
