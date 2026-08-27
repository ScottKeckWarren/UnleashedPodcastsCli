# Unleashed Podcasts CLI — Product Requirements

**Status:** Draft v0.6 — decisions from rounds 1-5 folded in.

## 1. Problem

UnleashedPodcasts.com exposes a private v1 REST API (`/apiv1`, static bearer token).
Any script, automation, or human who wants to write to it today has to hand-roll HTTP
calls, auth headers, pagination, and error handling. There is no shared client.

## 2. Goal

A single command-line tool — `unleashed` — that wraps the v1 API the way the AWS CLI
wraps AWS: predictable `noun verb` commands, credentials from config/env, JSON in and
JSON out. Usable interactively by a human and scriptable by CI.

First use case: **creating episodes** from an external workflow.

## 3. Roadmap

Shipped in milestones, narrowest first.

| Release | Contents | Blocked on |
|---------|----------|------------|
| **v0.1** | All five episode actions, plus full auth: layered config files, named profiles, `unleashed configure`. | — |
| **v0.2** | `unleashed login` — fetch a token by authenticating, instead of pasting one. | Sanctum token endpoint does not exist. Server work first. |
| **v0.3** | Podcasts resource — `podcasts list` / `get`. | `GET /apiv1/podcasts` does not exist. Server work first. |
| **v0.4** | Ideas resource — five standard actions. | The ideas resource does not exist in the API. Server work first. |

Later, unscheduled: the leads resource, a public library API.

Everything below describes the **end state** the milestones build toward, not v0.1.

### External dependencies

Two milestones depend on API surface that has not been built. Neither is work in this
repo, and both should start before the CLI milestone that consumes them.

**Sanctum token endpoint (blocks v0.2).** See §8.1 for the contract the CLI expects.
Switching to per-user Sanctum tokens also retires the static shared secret and gives
`/apiv1` a real user identity — which dissolves the "every episode belongs to one
configured owner" limit in the current API doc. That is a larger change than the CLI
work it unblocks.

**Podcasts (blocks v0.3).** Needs a read-only resource — `GET /apiv1/podcasts` and
`GET /apiv1/podcasts/{uuid}`, scoped to the token's configured owner like episodes are.
Index and show are enough; the CLI has no reason to write podcasts. Until it exists,
users hand-copy podcast UUIDs out of the web app, which is **accepted through v0.2**.

**Ideas (blocks v0.4).** A new resource, following the API's own "Adding a Resource"
rules: five standard actions, UUID-addressed, event-sourced, soft delete. Its field
list is not yet defined. The CLI cannot write its manifest until that field list and
the relationship between an idea and an episode are settled.

The API doc is the contract for both. When each ships, this CLI needs only a new
manifest — no generator changes.

## 4. Non-Goals

- No coverage of the session-cookie upload endpoints (`/api/files/*`) — browser-only surface.
- No local caching, sync, or offline mode.
- No interactive TUI / wizard.
- No API versions other than v1 (there is no v2).
- **No public Python library API.** The package is a CLI. Internal client classes are
  unstable and may change in any release. Public library support is revisited once the
  manifest abstraction has been tested against a second resource.

## 5. Users

| User | Need |
|------|------|
| Automation / n8n / cron | Non-interactive create + update of episodes, machine-readable output, reliable exit codes |
| Podcast operator (human) | Quick lookups and status changes from a terminal without opening the app |
| Other developers (OSS) | A tool they can `pipx install` and script against |

## 6. Command Shape

```
unleashed <resource> <action> [options]

unleashed episodes create --podcast-uuid ... --name "..." --target-published-date 2026-09-15
unleashed episodes list --status Edit --sort target_published_date
unleashed episodes get <uuid>
unleashed episodes update <uuid> --status Published --is-published
unleashed episodes update <uuid> --clear-description
unleashed episodes delete <uuid>
```

Principles, mirroring the API's own conventions:

- **Five actions per resource:** `list`, `create`, `get`, `update`, `delete`. No ad-hoc verbs.
- **One flag per writable API field**, kebab-cased. Filters and sorts are flags on `list`.
- **`--cli-input-json`** accepts a JSON object (or list, where bulk create is supported)
  as an alternative to flags.
- **UUIDs are the only addresses.** No integer ids anywhere.
- **`--podcast-uuid` is required on `episodes create`.** No profile default, no lookup.
  Users supply it explicitly until the podcasts resource lands in v0.3.

## 7. Resource Manifests

Commands are **generated from a declarative manifest**, not hand-written per resource.
Adding a resource means declaring its fields, filters, and sorts.

```python
EPISODES = Resource(
    name="episodes",
    fields=[
        Field("podcast_uuid", required_on_create=True, immutable=True),
        Field("name", required_on_create=True),
        Field("target_published_date", type=DATE, required_on_create=True),
        Field("status", enum=EPISODE_STATUSES),
        Field("is_published", type=BOOL),
        Field("description", nullable=True),
        Field("canonical_url", nullable=True),
        Field("podcast_name", read_only=True),
        Field("actual_published_date", type=DATE, read_only=True),
        Field("cover_art_file_id", read_only=True),
        Field("transcript_status", read_only=True),
    ],
    filters=[...],
    sorts=["target_published_date", "actual_published_date", "created_at", "name", "status"],
)
```

The manifest drives flag generation, request-body assembly, validation, and `--help` text.

Field attributes carry real consequences:

- `read_only=True` — no flag is generated at all. The field cannot be sent.
- `immutable=True` — flag exists on `create`, absent from `update`.
- `nullable=True` — generates a paired `--clear-<field>` flag (see §9).
- `required_on_create=True` — enforced locally before the request is sent.

**Nothing in the generator may reference a specific resource.** Anything resource-specific
belongs in that resource's manifest. This mirrors the API's own "Adding a Resource" rule.

A **leads manifest is written in v0.1 as a test fixture**, with no shipped commands. Two
manifests exercise the abstraction while the release surface stays narrow.

## 8. Configuration and Auth

Credentials live in INI config files, AWS-style. Three layers, lowest precedence first:

| Layer | Location |
|-------|----------|
| Environment | `UNLEASHED_API_URL`, `UNLEASHED_API_TOKEN` |
| Home config | `~/.unleashed/config` |
| Local config | the nearest `.unleashed/config` at or above the working directory |

```ini
[default]
api_url = https://unleashedpodcasts.com/apiv1
api_token = tok-personal

[client-a]
api_url = https://unleashedpodcasts.com/apiv1
api_token = tok-client-a
```

**Layers merge per key.** A local file holding only `api_token` inherits `api_url` from
home. That is what makes several accounts on one machine practical — one home config
with the URL and a personal token, and a per-project file that swaps only the token.

**The local file is found by walking up** from the working directory, so a script in a
subdirectory still resolves to the account its project declared. The walk stops before
the home directory, so the home config is never counted twice.

**Environment variables sit at the bottom, not the top.** A stale export in a shell must
not quietly hijack a project directory that has already said which account it belongs to.
They remain the path for CI and containers, which set variables and never write files.

**Profiles are sections.** `--profile` selects one, falling back to `UNLEASHED_PROFILE`
and then `default`. A profile does not inherit from `[default]` within a file — an
account half-described across two sections is worse than a clear error. An unknown
profile names the profiles that do exist.

**Failure names every path it looked in**, and points at `unleashed configure`.

### 8.1 Fetching a token (v0.2)

Today a token is minted by hand and pasted into `configure`. v0.2 adds `unleashed login`,
which authenticates and stores the token itself.

The server side follows Laravel Sanctum's **mobile application authentication** flow.
The CLI is, for this purpose, a mobile app: it holds a long-lived personal access token
and sends it as a bearer token.

```
POST <token endpoint>
{ "email": "...", "password": "...", "device_name": "scott-macbook" }

200
7|Abc123...
```

- **The response body is the token, as a bare string** — Laravel's documented example.
  The CLI reads the whole body. Because a bare string cannot be distinguished from an
  error page, the CLI validates the body against Sanctum's `{id}|{40 chars}` shape
  before writing it anywhere. A body that does not match is an error, never a stored
  token.
- **`device_name`** defaults to the machine's hostname and is overridable with
  `--device-name`. It is what the user sees in the web app's revoke list, so it must be
  recognisable.
- **The token is stored in the ordinary config file**, as `api_token` in the selected
  profile — the same file, permissions, profile selection, and local-override rules
  that already exist. `login` is `configure` with the token filled in automatically.
- **There is no `--password` flag.** The prompt hides input. A password in argv reaches
  shell history and the process table.
- **Static tokens keep working.** The CLI sends whatever `api_token` holds and never
  inspects it at request time. A hand-minted shared secret and a Sanctum personal access
  token are indistinguishable to the client, so existing v0.1 automation keeps running
  while the server supports both.
- **Expiry.** Sanctum tokens do not expire by default. If the application configures an
  expiration, there is no refresh token — the CLI's answer to a 401 is to tell the user
  to run `unleashed login` again. Exit code 4 already covers it.
- **Revocation** is a web-app concern. The CLI does not list or delete tokens in v0.2.

### Token handling

- The token is never echoed, never logged, and is redacted from `--dry-run` output.
- `configure` writes with mode `0600` and creates `.unleashed/` as `0700`.
- A config file readable by other users produces a warning on stderr naming the file
  and the `chmod` that fixes it. It is a warning, not a refusal — the command still runs.
- There is no `--token` flag. A token on the command line lands in shell history and in
  the process table of every other user on the machine.

## 9. Update Semantics

The API treats an omitted key and a `null` key differently. The CLI must make that
distinction impossible to trip over.

- **Omitted flag** → key absent from the body → field untouched.
- **`--clear-<field>`** → key present with `null` → field cleared.
- Passing both `--description X` and `--clear-description` is a usage error (exit 2).
- `--clear-<field>` is generated only for fields the manifest marks `nullable=True`.

No sentinel values. `--description null` sends the literal string `"null"`.

## 10. Output

- Default: pretty, human-readable table or key/value block.
- `--output json` emits the raw API envelope unmodified (`data` / `links` / `meta`).
- `--output text` emits tab-separated values for `awk`/`cut`.
- `--query` (JMESPath) to pluck fields, AWS-CLI style.
- Non-TTY defaults to JSON so pipes behave.
- `--dry-run` prints method, URL, headers (token redacted), and body — and sends nothing.
  Exit 0. Available on every write action.

## 11. Behavior the API Forces on Us

- **Pagination:** `list` auto-paginates by default and returns all results.
  `--no-paginate` returns one page. `--max-items N` stops after N records.
  No default cap — nothing truncates silently. `per_page` caps at 100, clamped server-side.
- **207 Multi-Status** on bulk create: surface per-item outcomes, exit non-zero if any
  item was `invalid`. (Reachable only via leads, but the client layer handles it.)
- **409 Conflict** on duplicate create: report as a distinct outcome carrying the
  existing UUID.
- **429:** honor `Retry-After`, retry with bounded backoff.
- **Read-only fields** are absent from the flag surface entirely — the manifest guarantees it.
- **Unknown response keys are ignored**, never an error. Responses are additive by contract.

## 12. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Unexpected / client error |
| 2 | Usage error (bad flags, conflicting flags) |
| 3 | Validation rejected by API (422) |
| 4 | Auth failure (401) |
| 5 | Not found (404) |
| 6 | Conflict (409) |
| 7 | Rate limited after retries exhausted (429) |

## 13. Technology

**Python 3.11+.** Chosen over Go/Node because the surrounding workflow tooling is
Python-friendly and the CLI ecosystem is mature. Tradeoff accepted: distribution needs
`pipx`/`uv` rather than a single static binary.

- CLI framework: **Click** — decorators stack programmatically, which the manifest-driven
  generator requires. Typer's static type-hint signatures do not fit generated commands.
- HTTP: `httpx`
- Models/validation: `pydantic`
- Test: `pytest`, `pytest-cov`, `respx` (HTTP mocking)
- Lint/format: `ruff`; types: `mypy` strict
- Packaging: `uv` + `pyproject.toml`, published to PyPI

## 14. Quality Bar

- **Test-driven.** Every behavior lands as a failing test first.
- **90% line coverage minimum, enforced in CI** (`--cov-fail-under=90`). Build fails below it.
- **Default suite hits no network.** All HTTP mocked via `respx` against the documented
  contract. Contributors can run everything with no credentials.
- **Optional live suite** against a local Sail host, marked `@pytest.mark.live` and
  deselected by default. Run manually to catch drift between this doc and the real API.
  It never counts toward the coverage gate and never runs in CI.
- A recorded-contract test suite documents each endpoint's request and response shape.
- CI runs on every PR: lint, types, mocked tests, coverage gate.

## 15. Open Source

- MIT license, public GitHub repo.
- README with install, configure, and first-episode walkthrough.
- README states plainly that the Python client is internal and unstable.
- CONTRIBUTING.md describing the TDD expectation and the coverage gate.
- Semantic versioning; release via tagged GitHub Actions workflow to PyPI.
- CHANGELOG maintained.

## 16. Open Questions

1. **The token endpoint's path.** Laravel's example uses `/sanctum/token`, outside
   `/apiv1`. Putting it at `/apiv1/tokens` keeps one base URL in the config file;
   anywhere else means the CLI must derive a second URL from the first.
2. **Token abilities.** Sanctum supports scopes. Does a CLI token get `*`, or a
   narrower set? If narrower, the CLI needs to report a 403 distinctly from a 401.
3. **Does per-user identity change episode scoping?** The current doc scopes every
   episode to one configured owner because the token has no user. Once it does, that
   paragraph needs rewriting — and `podcast_uuid` validation changes with it.
4. **Ideas field list.** Confirmed as a new API resource, but its fields, its enum
   values, and its relationship to an episode are undefined. Needed before the v0.4
   manifest can be written.
5. **Who builds the token, podcasts, and ideas endpoints, and when?** All three are
   outside this repo (see §3). v0.2, v0.3, and v0.4 each wait on one of them.
6. Does `episodes create` want a friendlier error when `--podcast-uuid` is wrong?
   The API returns 422 on the podcast field; the CLI could add "run `unleashed podcasts
   list`" to that message — but only once v0.3 exists.

## 17. Success Criteria

1. An external workflow can create an episode with one non-interactive command. *(v0.1)*
2. Adding a new API resource takes a manifest declaration and no generator changes.
3. Coverage stays above 90% on `main` continuously.
4. A stranger can install and make their first successful call from the README alone.
