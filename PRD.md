# Unleashed Podcasts CLI — Product Requirements

**Status:** Draft v0.7 — login, short form videos, and people folded in.

## 1. Problem

UnleashedPodcasts.com exposes a private v1 REST API (`/apiv1`, bearer token — per-user
Sanctum tokens, with the legacy static token still accepted).
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
| **v0.2** | `unleashed login` and `whoami`; a distinct exit code for 403. **Short form videos** — five actions plus `video-file attach`/`detach`. **People** — five actions plus `metadata merge`/`replace`. | — (done, unreleased) |
| **v0.3** | Podcasts resource — `podcasts list` / `get`. | `GET /apiv1/podcasts` does not exist. Server work first. |
| **v0.4** | Ideas resource — five standard actions. | Nothing — `/apiv1/ideas` now exists. Needs a manifest. |

Later, unscheduled:

- **Leads commands.** The manifest exists as a fixture and the API exists; shipping is a
  one-line change to the shipped list plus tests.
- **Episode transcript.** A read-only sub-resource (`/episodes/{uuid}/transcript` and
  `/transcript/utterances`) is in the API.
- **Person social media.** Needs server work first — see below.
- A public library API.

Everything below describes the **end state** the milestones build toward, not v0.1.

### External dependencies

Some CLI work depends on API surface outside this repo. Server work should start before
the CLI milestone that consumes it.

**Sanctum token endpoint — shipped.** Built as a browser loopback handshake rather than
the password exchange first proposed; §8.1 has the contract. Per-user tokens gave
`/apiv1` a real user identity, so listings are now scoped to the caller rather than to
one configured owner.

**Podcasts (blocks v0.3).** Needs a read-only resource — `GET /apiv1/podcasts` and
`GET /apiv1/podcasts/{uuid}`, scoped to the caller like every other listing. Index and
show are enough; the CLI has no reason to write podcasts. Until it exists, users
hand-copy podcast UUIDs out of the web app, which is **accepted through v0.2**.

**Ideas — shipped in the API.** `/apiv1/ideas` has its five standard actions. v0.4 is
now CLI-only work: a manifest and tests.

**Person social media (unscheduled).** The web app stores a person's social accounts
(`person_social_media`: platform, URL, username), but only web controllers use them —
the API's `PersonResource` omits them and there is no endpoint to write them. The CLI
needs three things before it can cover this: the accounts on the person read, a
child-collection endpoint (e.g. `GET`/`POST /people/{uuid}/social-media`, `DELETE
/people/{uuid}/social-media/{uuid}`), and a platform list or enum to validate against.
Until then, handles can go in person metadata, but they do not appear in the web app's
social section or on the public profile.

The API doc (`/apiv1/docs.json`) is the contract. When an endpoint ships, this CLI needs
a new manifest and no generator changes — unless the resource introduces a shape the
generator has never seen. That happened twice in v0.2 (attachments and key-value maps,
§7); each was a one-time, resource-agnostic addition.

### Endpoint coverage

Every operation in `/apiv1/docs.json` as of 2026-09-22, and whether the CLI covers it.
The API accepts both `PUT` and `PATCH` on a record, with identical behavior. The CLI's
`update` always sends `PATCH`, so the `PUT` rows are covered by that command.

| Method | Path | Supported | CLI command / reason |
|--------|------|-----------|----------------------|
| POST | `/apiv1/cli/token` | ✅ Yes | `login` (code exchange step) |
| GET | `/apiv1/whoami` | ✅ Yes | `whoami` |
| GET | `/apiv1/episodes` | ✅ Yes | `episodes list` |
| POST | `/apiv1/episodes` | ✅ Yes | `episodes create` |
| GET | `/apiv1/episodes/{uuid}` | ✅ Yes | `episodes get` |
| PUT | `/apiv1/episodes/{uuid}` | ✅ Yes | `episodes update` (sends PATCH) |
| PATCH | `/apiv1/episodes/{uuid}` | ✅ Yes | `episodes update` |
| DELETE | `/apiv1/episodes/{uuid}` | ✅ Yes | `episodes delete` |
| GET | `/apiv1/episodes/{uuid}/transcript` | ❌ No | Unscheduled. Read-only sub-resource; needs a new manifest shape |
| GET | `/apiv1/episodes/{uuid}/transcript/utterances` | ❌ No | Unscheduled. Paginated child listing of the transcript |
| GET | `/apiv1/short-form-videos` | ✅ Yes | `short-form-videos list` |
| POST | `/apiv1/short-form-videos` | ✅ Yes | `short-form-videos create` |
| GET | `/apiv1/short-form-videos/{uuid}` | ✅ Yes | `short-form-videos get` |
| PUT | `/apiv1/short-form-videos/{uuid}` | ✅ Yes | `short-form-videos update` (sends PATCH) |
| PATCH | `/apiv1/short-form-videos/{uuid}` | ✅ Yes | `short-form-videos update` |
| DELETE | `/apiv1/short-form-videos/{uuid}` | ✅ Yes | `short-form-videos delete` |
| PUT | `/apiv1/short-form-videos/{uuid}/video-file` | ✅ Yes | `short-form-videos video-file attach` |
| DELETE | `/apiv1/short-form-videos/{uuid}/video-file` | ✅ Yes | `short-form-videos video-file detach` |
| GET | `/apiv1/people` | ✅ Yes | `people list` |
| POST | `/apiv1/people` | ✅ Yes | `people create` |
| GET | `/apiv1/people/{uuid}` | ✅ Yes | `people get` |
| PUT | `/apiv1/people/{uuid}` | ✅ Yes | `people update` (sends PATCH) |
| PATCH | `/apiv1/people/{uuid}` | ✅ Yes | `people update` |
| DELETE | `/apiv1/people/{uuid}` | ✅ Yes | `people delete` |
| PATCH | `/apiv1/people/{uuid}/metadata` | ✅ Yes | `people metadata merge` |
| PUT | `/apiv1/people/{uuid}/metadata` | ✅ Yes | `people metadata replace` |
| GET | `/apiv1/ideas` | ❌ No | v0.4. API exists; needs a manifest |
| POST | `/apiv1/ideas` | ❌ No | v0.4 |
| GET | `/apiv1/ideas/{uuid}` | ❌ No | v0.4 |
| PUT | `/apiv1/ideas/{uuid}` | ❌ No | v0.4 |
| PATCH | `/apiv1/ideas/{uuid}` | ❌ No | v0.4 |
| DELETE | `/apiv1/ideas/{uuid}` | ❌ No | v0.4 |
| GET | `/apiv1/leads` | ❌ No | Unscheduled. Manifest exists as a test fixture; not shipped |
| POST | `/apiv1/leads` | ❌ No | Unscheduled. Also takes a batch, answered with 207 Multi-Status |
| GET | `/apiv1/leads/{uuid}` | ❌ No | Unscheduled |
| PUT | `/apiv1/leads/{uuid}` | ❌ No | Unscheduled |
| PATCH | `/apiv1/leads/{uuid}` | ❌ No | Unscheduled |
| DELETE | `/apiv1/leads/{uuid}` | ❌ No | Unscheduled |
| POST | `/api/files/presigned-upload-url` | ❌ No | Non-goal (§4). Uses the browser session cookie, not a bearer token |
| POST | `/api/files/upload-complete` | ❌ No | Non-goal (§4). Uses the browser session cookie |

**Totals:** 24 of 40 operations supported. Of the 16 that aren't: 6 ideas (v0.4),
6 leads (unscheduled), 2 transcript (unscheduled), and 2 file uploads (non-goal).

The CLI also needs endpoints that `docs.json` doesn't list yet:

- `GET /apiv1/podcasts` and `GET /apiv1/podcasts/{uuid}` — v0.3.
- Person social media — unscheduled, see above.

`login` also calls the web route `/cli/authorize`, which serves the browser approval
page. It isn't part of `/apiv1`, so it isn't in the table.

## 4. Non-Goals

- No coverage of the session-cookie upload endpoints (`/api/files/*`) — browser-only surface.
  `short-form-videos video-file attach` takes the UUID of a file already uploaded in
  the web app; the CLI never uploads.
- No local caching, sync, or offline mode.
- No interactive TUI / wizard.
- No API versions other than v1 (there is no v2).
- **No public Python library API.** The package is a CLI. Internal client classes are
  unstable and may change in any release. The manifest abstraction now carries three
  shipped resources and a fixture, so public library support is due for a revisit — but
  it stays a non-goal until that decision is made.

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

unleashed short-form-videos video-file attach <uuid> --file-uuid ...
unleashed people metadata merge <uuid> --set tier=gold --unset twitter

unleashed login
unleashed whoami
```

Principles, mirroring the API's own conventions:

- **Five actions per resource:** `list`, `create`, `get`, `update`, `delete`.
- **Sub-resources nest as their own noun:** `unleashed <resource> <sub-resource> <verb>`.
  Each kind of sub-resource has a fixed pair of verbs — `attach`/`detach` for a linked
  record, `merge`/`replace` for a key-value map. Never a one-off verb for one resource.
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
- `type=MAP` — a repeatable `--<field> KEY=VALUE` flag, assembled into an object.
  Values are sent as strings; typed values go through `--cli-input-json`.

Beyond fields, a resource can declare sub-resources and help-text wording:

- **`Attachment(name, id_field)`** — a singular linked record.
  `PUT /<resource>/<uuid>/<name>` with `{<id_field>: ...}` becomes `attach`, replacing
  whatever was attached; `DELETE` on the same path becomes `detach`.
- **`KeyValueMap(name)`** — a flat map of scalars. `PATCH` becomes `merge` (`--set
  KEY=VALUE`, `--unset KEY` sends null to delete it); `PUT` becomes `replace` (`--set`
  only). Both accept `--cli-input-json`, validated locally as a flat object of scalars.
  `replace` with nothing to send is refused rather than wiping the map; clearing it is
  an explicit `--cli-input-json '{}'`.
- **`singular_name`** — for names that do not singularise by dropping an `s`, so help
  reads "Create one person."

```python
PEOPLE = Resource(
    name="people",
    fields=[
        Field("name", required_on_create=True),
        Field("email", nullable=True),
        Field("last_outreach", type=DATE),          # cannot be cleared once set
        Field("metadata", type=MAP),
        ...
    ],
    maps=[KeyValueMap("metadata")],
    singular_name="person",
)
```

**Nothing in the generator may reference a specific resource.** Anything resource-specific
belongs in that resource's manifest. This mirrors the API's own "Adding a Resource" rule.

Shipped manifests: **episodes**, **short-form-videos**, **people**. A **leads manifest**
exists as a test fixture with no shipped commands.

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

`unleashed login` fetches a token and stores it, so nobody pastes one into `configure`.
`configure` remains for CI and for the legacy static token.

The server issues Sanctum personal access tokens through a **browser loopback
handshake**, the same shape as OAuth's PKCE flow. There is no password prompt.

```
1. CLI invents a verifier and a state, listens on http://127.0.0.1:<port>/callback
2. CLI opens <site>/cli/authorize?state=..&verifier_hash=<sha256 hex>
       &redirect_uri=..&device_name=..&abilities[]=..
3. User approves; the site redirects to redirect_uri?code=..&state=..
4. POST /apiv1/cli/token { "code": "..", "verifier": ".." }
   200 { "token": "7|Abc123...", "token_type": "Bearer" }
   400 on any failure — invalid, expired (2 min), reused, or wrong verifier
```

- **The token never passes through the browser.** The browser carries only the
  one-use code, which is useless without the verifier held in the CLI process.
- **The state must match** or the redirect is rejected and nothing is written.
- **`<site>` is derived from `api_url`** by stripping `/apiv1`, so one base URL in the
  config still covers both the approval page and the API.
- **Abilities** default to every one the site grants (`episodes:read`,
  `episodes:write`, `leads:read`, `leads:write`); `--ability` narrows the request. A
  missing ability is a 403, reported with its own exit code (8).
- **`api_url`** comes from `--api-url`, then the selected profile's existing value, then
  `UNLEASHED_API_URL`, then production.
- **The CLI waits five minutes** for the browser, long enough to sign in first. The
  code itself expires two minutes after approval. `--no-browser` prints the approval
  URL instead of opening it.
- **Short form videos and people need no ability** — any valid token reaches them.
- **`unleashed whoami`** shows the user, device name, and abilities behind the current
  token, for checking which account a profile points at.
- **`device_name`** defaults to the machine's hostname and is overridable with
  `--device-name`. It is what the user sees in the web app's revoke list, so it must be
  recognisable.
- **The token is stored in the ordinary config file**, as `api_token` in the selected
  profile — the same file, permissions, profile selection, and local-override rules
  that already exist. `login` is `configure` with the token filled in automatically.
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

- A field the API will not clear (people's `last_outreach`) is not `nullable`, so it has
  no `--clear-` flag.
- A `MAP` field on `update` merges into the existing keys, because the API merges. To
  delete a key, use the map sub-resource: `<resource> <map> merge --unset KEY`.

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
| 4 | Auth failure (401); `login` denied, timed out, or its code exchange failed |
| 5 | Not found (404) |
| 6 | Conflict (409) |
| 7 | Rate limited after retries exhausted (429) |
| 8 | Forbidden: the token lacks the ability the route needs (403) |

A 401 or 403 also prints a hint to run `unleashed login`.

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

Resolved:

1. ~~The token endpoint's path.~~ `POST /apiv1/cli/token`, inside `/apiv1`. The approval
   page lives on the site; the CLI derives it from `api_url` by stripping `/apiv1`.
2. ~~Token abilities.~~ A closed list (`episodes:read|write`, `leads:read|write`), never
   a wildcard. A 403 is reported distinctly, with exit code 8.
3. ~~Does per-user identity change episode scoping?~~ Yes — every listing is now scoped
   to the caller.
4. ~~Ideas field list.~~ Defined in `/apiv1/docs.json`.

Open:

5. **Who builds the podcasts endpoint, and when?** The only server dependency still
   blocking a numbered milestone (v0.3).
6. Does `episodes create` want a friendlier error when `--podcast-uuid` is wrong?
   The API returns 422 on the podcast field; the CLI could add "run `unleashed podcasts
   list`" to that message — but only once v0.3 exists.
7. **Should short form videos and people get their own abilities?** Today any valid
   token reaches them, so `--ability` cannot narrow a token away from them.
8. **Typed metadata values from flags.** `--set count=3` sends the string `"3"`. Guessing
   types would break values like zip codes (`02134`); typed values currently need
   `--cli-input-json`. Is that good enough, or does it want an explicit typed flag?
9. **Person social media endpoint** — design and ownership (see §3).
10. **A friendlier missing-profile error.** With no `[default]` section, the error names
    the missing `api_url` but not the profiles that do exist (hit during local testing
    after `login --profile local`). It should list them, as the explicit-profile error does.

## 17. Success Criteria

1. An external workflow can create an episode with one non-interactive command. *(v0.1)*
2. Adding a new API resource takes a manifest declaration and no generator changes.
   Met for short form videos and people; the new shapes they introduced (attachments,
   key-value maps) were one-time, resource-agnostic generator additions.
3. Coverage stays above 90% on `main` continuously.
4. A stranger can install and make their first successful call from the README alone.
