# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `unleashed login` — approve the CLI in a browser and save the personal access token
  it is issued. Loopback redirect to 127.0.0.1 plus a code-and-verifier exchange, so
  the token never passes through the browser. `--ability`, `--device-name`,
  `--api-url`, `--no-browser`, `--profile`, and `--local`.
- `unleashed whoami` — the user, device name, and abilities behind the current token.
- Exit code 8 for a 403: the token is valid but lacks the ability the route needs.
  401 and 403 errors now say to run `unleashed login`.
- `short-form-videos` — all five standard actions, generated from a manifest.
- `short-form-videos video-file attach|detach`, from a new manifest `Attachment`
  declaration that any resource can reuse.
- `people` — all five standard actions, with repeatable `--metadata KEY=VALUE` on
  create and update.
- `people metadata merge|replace`, from a new manifest `KeyValueMap` declaration.
  `merge` takes `--set` and `--unset`; both take `--cli-input-json` for typed values.
- A manifest `singular_name`, so help reads "Create one person."
- All five standard actions for episodes — `list`, `create`, `get`, `update`, `delete` —
  generated from a declarative resource manifest.
- `list` auto-paginates, with `--no-paginate` and `--max-items` to spend less.
- `list` filters and `--sort` are generated from the manifest; a sort outside the
  allowlist is rejected before the request is sent.
- `update` distinguishes an omitted flag from `--clear-<field>`, which sends null.
- Layered configuration: a local `.unleashed/config` overrides `~/.unleashed/config`
  key by key, with `UNLEASHED_API_URL` / `UNLEASHED_API_TOKEN` as the lowest fallback.
- The local config is found by walking up from the working directory.
- Named profiles via `--profile` and `UNLEASHED_PROFILE`.
- `unleashed configure`, writing one profile at mode 0600 and leaving others intact.
- A warning when a config file holding a token is readable by other users.
- `--dry-run`, which prints the request with the token redacted and sends nothing.
- `--output json|text|table` and `--query` (JMESPath).
- `--cli-input-json` as an alternative to field flags.
- Distinct exit codes per API failure mode.
- Bounded retry on 429 that honours `Retry-After`.
