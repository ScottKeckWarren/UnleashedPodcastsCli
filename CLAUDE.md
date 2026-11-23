# Working in this repo

## Before any code change

Read CONTRIBUTING.md. Its rules apply to you: write the failing test first, then the code
that makes it pass, and keep coverage at or above 90%. `make pre-commit` runs what CI
runs, and the git hook runs it on every commit.

## The API contract

PRD.md can lag the server. Before saying the API can or can't do something, fetch
`https://unleashedpodcasts.com/apiv1/docs.json` and check it. To list every operation
the server documents but PRD.md's endpoint table doesn't:

```bash
UNLEASHED_API_URL=https://unleashedpodcasts.com/apiv1 UNLEASHED_API_TOKEN=unused \
    uv run pytest -m live --no-cov tests/test_live.py -k prd
```

docs.json needs no token, so any value works for that one test.

## Releasing

1. Open a PR with two commits: `feat: ...` with the code, tests, README, and PRD, then
   `chore: release X.Y.Z` with the CHANGELOG section and the version bump in
   `pyproject.toml`, `src/unleashed/__init__.py`, and `uv.lock` (`uv lock`).
2. PRs are rebase-merged, so the commit SHAs change. After the merge, `git pull` on
   `main` and tag the merged release commit with a lightweight tag: `git tag vX.Y.Z <sha>`.
3. `git push origin vX.Y.Z`. `release.yml` then checks the tag against `pyproject.toml`,
   reruns CI, publishes to PyPI, and creates the GitHub Release with the CHANGELOG
   section as its body. Don't create the release by hand.
