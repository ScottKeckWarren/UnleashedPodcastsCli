# Contributing

## Setup

```bash
uv sync
uv run pytest
```

## The two rules

**1. Test first.** Every behavioural change lands as a failing test before the code that
makes it pass. A pull request whose tests would have passed before the change is not
finished.

**2. Coverage stays at or above 90%.** `pytest` is configured with `--cov-fail-under=90`,
so a shortfall fails locally and in CI. Do not lower the threshold to make a build pass —
raise the coverage, or explain in the pull request why a line is genuinely untestable and
mark it `# pragma: no cover`.

## Tests never hit the network

The default suite mocks every HTTP call with `respx` against the contract in `PRD.md`.
Contributors need no credentials and no server to run everything.

An optional live suite is marked `@pytest.mark.live` and is deselected by default. It runs
against a local Sail host to catch drift between the documented contract and the real API.
It never counts toward the coverage gate and never runs in CI.

```bash
UNLEASHED_API_URL=http://localhost/apiv1 UNLEASHED_API_TOKEN=... uv run pytest -m live --no-cov
```

Every test runs with `HOME` and the working directory pointed at a temporary directory,
so a test can never read — or write — your real `~/.unleashed/config`. That isolation is
automatic; do not disable it.

## Adding a resource

Resources are declared, not hand-written. Add a manifest under `src/unleashed/resources/`
and register it. If you find yourself editing the generator to accommodate one resource,
stop — that behaviour belongs in the manifest as a new field attribute, the same rule the
API itself follows.

## Before opening a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Releasing

Releases are tag-driven. The workflow refuses to publish a tag that disagrees with the
version in `pyproject.toml`, and re-runs lint, types, and the full test suite before
building — a release must never ship code that would fail CI.

```bash
# bump version in pyproject.toml, update CHANGELOG.md, commit
git tag v0.1.0
git push origin v0.1.0
```

That builds, publishes to PyPI via Trusted Publishing, and cuts a GitHub Release with
the artifacts attached. There is no PyPI API token in repository secrets; GitHub proves
its identity to PyPI over OIDC instead.

One-time setup on PyPI, done in a browser: register this repository as a trusted
publisher for the `unleashed-podcasts-cli` project, with workflow `release.yml` and
environment `pypi`.
