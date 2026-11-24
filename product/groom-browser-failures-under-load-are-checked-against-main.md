date: 2026-11-24
sources: operator, 2026-11-24
status: accepted

When groom's browser tests time out in `make test` on a loaded machine and pass when run alone, run the same test files on main and on the branch at the same time, with the same worker count. If main passes them and the branch fails them, the failure is a regression on the branch. The story fixes it before the gate can pass. Machine load is not a reason to leave it.

The story `notice-a-run-that-ended` grounds this. Its Non-Functional Acceptance Criteria say: "The Runs tab behaves as it did for every run that is not ending." The commit skill, `.agents/skills/stablemate-commit/SKILL.md:41`, says: "Run the repo's gate, not just the test you were staring at".

The question rose at the `dev` stage of that story. `make test` failed 17 groom browser tests after 3 repair turns. Each failure was a 30 s wait for `#runs-list .row`. The producer had put the failures down to a machine at load 20 to 30. On 2026-11-24, at load 40 to 60, the resolver ran the 12 failing files with `-n 4` on main (339a421f9) and on the branch (bf9542110) at the same time. Main passed 229 of 229 in 474 s. The branch failed 16 in the first 91 % of the run and did not finish inside 550 s. Each failing test passes alone in about 5 s.
