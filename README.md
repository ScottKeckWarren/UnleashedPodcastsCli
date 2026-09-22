# Unleashed Podcasts CLI

A command-line interface for the [UnleashedPodcasts.com](https://unleashedpodcasts.com)
private v1 API, shaped like the AWS CLI: predictable `noun verb` commands, credentials
from the environment, JSON in and JSON out.

**Status: episodes, short form videos, and people, plus `login`, `whoami`, and `configure`.** See [PRD.md](PRD.md) for the roadmap.

## Install

Once published to PyPI:

```bash
uv tool install unleashed-podcasts-cli
```

Straight from the repository, which works today:

```bash
uv tool install git+https://github.com/ScottKeckWarren/UnleashedPodcastsCli
```

Run it once without installing anything:

```bash
uvx --from git+https://github.com/ScottKeckWarren/UnleashedPodcastsCli unleashed --help
```

`pipx` works everywhere `uv tool` does, if you prefer it. Plain `pip install` only
inside an activated virtualenv — a CLI belongs in its own environment, not alongside
your project's dependencies.

To upgrade or remove:

```bash
uv tool upgrade unleashed-podcasts-cli
uv tool uninstall unleashed-podcasts-cli
```

### Working on the CLI itself

```bash
git clone git@github.com:ScottKeckWarren/UnleashedPodcastsCli.git
cd UnleashedPodcastsCli
uv tool install --editable .    # `unleashed` on PATH, tracking your working tree
uv sync && uv run pytest        # run the suite
```

## Log in

```bash
unleashed login
```

That opens your browser on the site's approval page. Sign in if asked, press
**Approve**, and the CLI saves a personal access token to `~/.unleashed/config`.
The token never passes through the browser — the browser carries a one-use code that
only the waiting `login` process can redeem, and only for two minutes.

```bash
unleashed login --profile client-a                   # write a named profile
unleashed login --local                              # write ./.unleashed/config
unleashed login --api-url http://localhost/apiv1     # log in to another host
unleashed login --ability episodes:read              # ask for less (repeatable)
unleashed login --device-name studio-mac             # name shown in the web app
unleashed login --no-browser                         # print the URL instead
```

By default the token asks for every ability the site grants. The device name defaults
to your hostname; it is what you will see in the web app when you revoke the token.

Check which account and abilities a token carries:

```bash
unleashed whoami
```

A `401` means the token is dead — run `unleashed login` again. A `403` means the token
is alive but was not granted the ability that command needs; it exits `8`.

## Configure

To paste a token by hand instead — for CI, or the legacy static token:

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

## Short form videos

The same five actions, plus a `video-file` attachment.

```bash
unleashed short-form-videos create --title "Three mistakes new hosts make" \
    --podcast-episode-uuid 7f3a1c2e-... --target-date 2026-10-01
unleashed short-form-videos list --origin generated --standalone --sort -target_date
unleashed short-form-videos get <uuid>
unleashed short-form-videos update <uuid> --clear-podcast-uuid     # detach podcast and episode
unleashed short-form-videos delete <uuid>
```

A short stands alone, sits under a podcast, or sits under an episode. An episode brings
its own podcast, so `--podcast-uuid` is only needed without one. Moving a short to
another podcast drops its episode.

### Video file

```bash
unleashed short-form-videos video-file attach <uuid> --file-uuid <file-uuid>
unleashed short-form-videos video-file detach <uuid>
```

Attaching replaces any video already attached; detaching keeps the file itself. Upload
the video in the web app first — file uploads use the browser session, not the API
token, so the CLI does not upload.

## People

The same five actions, plus a `metadata` sub-resource.

```bash
unleashed people create --name "Ada Lovelace" --email ada@example.test \
    --metadata twitter=@ada --metadata source=cli
unleashed people list --no-has-email --last-outreach-before 2026-06-01 --sort last_outreach
unleashed people list --podcast-uuid 7f3a1c2e-...        # people who appeared on a show
unleashed people get <uuid>
unleashed people update <uuid> --last-outreach 2026-09-22 --clear-email
unleashed people delete <uuid>
```

`--last-outreach-before` includes people never contacted at all — they are the most
overdue. `last_outreach` cannot be cleared once set, so it has no `--clear-` flag.

### Metadata

Metadata is a flat map of strings, numbers, booleans, and nulls. `--metadata KEY=VALUE`
on `create` and `update` sends strings, and `update` merges into the existing keys.
To delete keys, send typed values, or replace the map, use the sub-resource:

```bash
unleashed people metadata merge <uuid> --set tier=gold --unset twitter
unleashed people metadata merge <uuid> --cli-input-json '{"episodes": 3, "vip": true}'
unleashed people metadata replace <uuid> --set only=this      # every other key is removed
unleashed people metadata replace <uuid> --cli-input-json '{}' # clear every key
```

`replace` with no `--set` and no `--cli-input-json` is refused rather than wiping the map.

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
| 4 | Auth failure (401), or `login` was denied or failed |
| 5 | Not found (404) |
| 6 | Conflict (409) |
| 7 | Rate limited after retries were exhausted (429) |
| 8 | Forbidden: the token lacks the ability (403) |

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
