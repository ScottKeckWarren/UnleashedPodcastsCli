# Unleashed Podcasts CLI

A command-line interface for the [UnleashedPodcasts.com](https://unleashedpodcasts.com)
private v1 API, shaped like the AWS CLI: predictable `noun verb` commands, credentials
from the environment, JSON in and JSON out.

**Status: v0.1 — all five episode actions, plus `configure`.** See [PRD.md](PRD.md) for the roadmap.

## Install

```bash
uv tool install unleashed-podcasts-cli
# or
pipx install unleashed-podcasts-cli
```

## Configure

```bash
unleashed configure
```

That writes `~/.unleashed/config`:

```ini
[default]
api_url = https://unleashedpodcasts.com/apiv1
api_token = your-token
```

### Several accounts on one machine

A `.unleashed/config` in a project directory overrides the home one **key by key**, so a
project file can carry nothing but a token and inherit the URL from home.

```
~/.unleashed/config              api_url + api_token   (your personal account)

~/work/client-a/.unleashed/config    api_token          (client A's token)
~/work/client-b/.unleashed/config    api_token          (client B's token)
```

Run from anywhere inside `~/work/client-a` — including a subdirectory — and you are
using client A. The local file is found by walking up from the working directory.

```bash
cd ~/work/client-a
unleashed configure --local
```

### Profiles

For several accounts without separate directories, use sections:

```ini
[default]
api_url = https://unleashedpodcasts.com/apiv1
api_token = tok-personal

[client-a]
api_url = https://unleashedpodcasts.com/apiv1
api_token = tok-client-a
```

```bash
unleashed --profile client-a episodes create ...
unleashed configure --profile client-a
export UNLEASHED_PROFILE=client-a      # or set it once
```

A profile does not inherit from `[default]`. Give each one both keys.

### Precedence

Highest first:

1. `--profile` selects which section is read
2. the nearest local `.unleashed/config`
3. `~/.unleashed/config`
4. `UNLEASHED_API_URL` and `UNLEASHED_API_TOKEN`

Environment variables sit at the bottom on purpose: a stale `export` in your shell should
not override a project directory that has already declared which account it belongs to.
They stay the right tool for CI and containers, which set variables and never write files.

Not sure which account you are about to use? `--dry-run` names the profile and the file
it came from.

```bash
$ unleashed episodes create --dry-run ...
# profile default (from /Users/you/work/client-a/.unleashed/config)
POST https://unleashedpodcasts.com/apiv1/episodes
...
```

### Token safety

`configure` writes the file with mode `0600`. If a config file holding a token is
readable by other users, every command warns and tells you the `chmod` that fixes it.

There is deliberately no `--token` flag — a token on the command line lands in your shell
history and in the process table of every other user on the machine.

## Episodes

Five actions, the same five the API exposes. No ad-hoc verbs.

```bash
unleashed episodes list
unleashed episodes create --podcast-uuid ... --name ... --target-published-date ...
unleashed episodes get <uuid>
unleashed episodes update <uuid> --status Scheduled
unleashed episodes delete <uuid>
```

### Create

You need the UUID of the podcast the episode belongs to. Until the podcasts resource
ships in v0.3, copy it from the web app.

```bash
unleashed episodes create \
    --podcast-uuid 7f3a1c2e-... \
    --name "Episode 101: Something Useful" \
    --target-published-date 2026-09-15 \
    --status Draft \
    --description "Show notes here."
```

Pass a payload instead of flags:

```bash
unleashed episodes create --cli-input-json '{"podcast_uuid": "...", "name": "...", "target_published_date": "2026-09-15"}'
```

### List

Filters are flags, named for the field they match. Every page is fetched by default, so
a result is never a silent truncation.

```bash
unleashed episodes list --status Edit --transcript-status none --no-has-cover-art
unleashed episodes list --sort -target_published_date --max-items 20
unleashed episodes list --no-paginate            # first page only
```

`--sort` takes one allowlisted column; prefix it with `-` for descending. A column
outside the allowlist is caught before the request is sent:

```
$ unleashed episodes list --sort nonsense
Error: Cannot sort by 'nonsense'. Allowed columns: target_published_date,
actual_published_date, created_at, name, status (prefix - for desc)
```

### Update

An omitted flag leaves the field alone. `--clear-<field>` sends an explicit `null`.
Passing no flags at all is a successful no-op.

```bash
unleashed episodes update <uuid> --status Scheduled
unleashed episodes update <uuid> --clear-description      # sets description to null
unleashed episodes update <uuid> --is-published           # publishes it
unleashed episodes update <uuid> --no-is-published        # hides it
```

Only nullable fields get a `--clear-` flag, and `--description X --clear-description`
together is a usage error rather than a coin toss.

`--podcast-uuid` has no flag here — it is immutable after create, so the manifest keeps
it off this command entirely.

### Delete

```bash
unleashed episodes delete <uuid>
```

The API soft-deletes. There is no restore endpoint; recovery is a database task.

### Dry run

Every action takes `--dry-run`, which prints the request with the token redacted and
sends nothing:

```
$ unleashed episodes create --dry-run --podcast-uuid ... --name ... --target-published-date ...
# profile default (from /Users/you/work/client-a/.unleashed/config)
POST https://unleashedpodcasts.com/apiv1/episodes
Accept: application/json
Authorization: Bearer ***redacted***
Content-Type: application/json

{
  "podcast_uuid": "7f3a1c2e-...",
  "name": "Episode 101: Something Useful",
  "target_published_date": "2026-09-15"
}
```

## Output

| Flag | Behaviour |
|------|-----------|
| `--output table` | Human-readable key/value block. Default on a TTY. |
| `--output json` | The record as JSON. Default when piped. |
| `--output text` | Tab-separated values, for `awk` and `cut`. |
| `--query` | A [JMESPath](https://jmespath.org) expression applied before rendering. |
| `--dry-run` | Print the request with the token redacted and send nothing. |

```bash
unleashed episodes create --query uuid --output text ...   # prints just the new UUID
unleashed episodes list --query "[].[uuid,name,status]" --output text | column -t
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Unexpected or transport error |
| 2 | Usage error, including missing or unreadable configuration |
| 3 | Validation rejected by the API (422) |
| 4 | Auth failure (401) |
| 5 | Not found (404) |
| 6 | Conflict (409) |
| 7 | Rate limited after retries were exhausted (429) |

Scripts can branch on these without parsing output.

## A note on the Python package

This package is a CLI. The classes inside it are internal, unstable, and may change
in any release — do not import them. A supported library API is planned once the
resource abstraction has been tested against a second resource.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every change is test-first and the build fails
below 90% coverage.

## License

MIT. See [LICENSE](LICENSE).
