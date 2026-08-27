"""Entry point. Wires manifests into commands and maps errors onto exit codes."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import click

from unleashed import __version__
from unleashed.config import (
    DEFAULT_PROFILE,
    PROFILE_VAR,
    config_path_in,
    home_config_path,
    read_existing,
    write_config,
)
from unleashed.errors import ExitCode, UnleashedError, UsageError
from unleashed.generator import build_group
from unleashed.reporting import handle_errors, report
from unleashed.resources import SHIPPED


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version")
@click.option(
    "--profile",
    default=None,
    help=f"Config profile to use. Defaults to {PROFILE_VAR} or '{DEFAULT_PROFILE}'.",
)
@click.pass_context
def cli(ctx: click.Context, profile: str | None) -> None:
    """Command-line interface for the UnleashedPodcasts.com v1 API."""
    ctx.ensure_object(dict)
    ctx.obj.setdefault("env", os.environ)
    ctx.obj["profile"] = profile


@cli.command()
@click.option("--local", "local", is_flag=True, help="Write ./.unleashed/config instead of ~/.")
@click.option("--profile", "profile", default=None, help="Profile to write.")
@click.pass_context
@handle_errors
def configure(ctx: click.Context, local: bool, profile: str | None) -> None:
    """Write credentials to a config file.

    Values are stored per profile. A local config overrides the home one key by key,
    so a project directory can swap the token and inherit everything else.
    """
    profile = (
        profile or ctx.obj.get("profile") or ctx.obj["env"].get(PROFILE_VAR) or DEFAULT_PROFILE
    )
    path = config_path_in(Path.cwd()) if local else home_config_path()
    existing = read_existing(path, profile)

    url = click.prompt("API URL", default=existing.get("api_url", ""), show_default=True).strip()
    if not url:
        raise UsageError("An API URL is required.")
    token = click.prompt(
        "API token",
        default=existing.get("api_token", ""),
        show_default=False,
        hide_input=True,
    ).strip()
    if not token:
        raise UsageError("An API token is required.")

    write_config(path, profile, url, token)
    click.echo(f"Wrote profile '{profile}' to {path}")


for _resource in SHIPPED:
    cli.add_command(build_group(_resource))


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """Run the CLI and return an exit code instead of raising."""
    obj = {"env": dict(env) if env is not None else os.environ}
    try:
        # standalone_mode=False makes Click return an exit code rather than calling
        # sys.exit, so a command that exited deliberately keeps its code.
        result = cli.main(
            args=list(argv) if argv is not None else None,
            obj=obj,
            standalone_mode=False,
        )
    except UnleashedError as error:
        report(error)
        return int(error.exit_code)
    except click.ClickException as error:
        error.show()
        return int(ExitCode.USAGE)
    except click.exceptions.Abort:
        click.echo("Aborted.", err=True)
        return int(ExitCode.ERROR)
    return result if isinstance(result, int) else int(ExitCode.SUCCESS)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
