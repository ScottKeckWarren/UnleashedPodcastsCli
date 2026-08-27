# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

## Planned

### v0.2

- `unleashed login` — exchange email and password for a Sanctum personal access token
  and write it to the selected profile. Requires a token endpoint on the server.
