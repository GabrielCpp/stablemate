"""link-shortener — the smoke task: one Go surface, three bullets, half an hour."""

from __future__ import annotations

import _greenfield as gf
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener",
    seed="link-shortener",
    config="configs/opencode.toml",
)

FIXTURE = gf.Fixture(
    backlog="apps/link-shortener/docs/backlog.md",
    decision_records="apps/link-shortener/docs/decisions",
    grill_capture="apps/link-shortener/grill",
    packs="product-planning,stablemate,infra",
    docs_scaffold="shared-docs:docs",
    surfaces=(
        gf.Surface(
            service="api",
            service_root="api",
            packs="go",
            scaffolds="go-service:api",
            init_cmd="go mod init example.com/link-shortener/api",
            marker="go.mod",
            markers="go.mod,main.go",
        ),
    ),
    checks=(
        gf.Check(name="build", cmd="cd api && go build ./...", timeout_s=300.0),
        gf.Check(name="test", cmd="cd api && go test ./...", timeout_s=600.0),
    ),
    judge_cli="opencode",
    judge_model="openai/gpt-5.6-sol",
    judge_effort="medium",
    budget_s={"genesis": 3600.0, "author": 3600.0, "coder": 11000.0},
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def build(run: Run) -> None:
    gf.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return gf.score_round(run, FIXTURE)
