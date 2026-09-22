"""Entry point. Wires manifests into commands and maps errors onto exit codes."""

from __future__ import annotations

import os
import socket
import sys
import webbrowser
from collections.abc import Mapping, Sequence
from pathlib import Path

import click

from unleashed import __version__, auth
from unleashed.client import Client
from unleashed.config import (
    DEFAULT_PROFILE,
    PROFILE_VAR,
    URL_VAR,
    config_path_in,
    home_config_path,
    load_config,
    read_existing,
    write_config,
)
from unleashed.errors import ExitCode, UnleashedError, UsageError
from unleashed.generator import build_group
from unleashed.output import OutputFormat, default_output, render
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
    profile = _profile_for(ctx, profile)
    path = _config_path(local)
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


@cli.command()
@click.option("--local", "local", is_flag=True, help="Write ./.unleashed/config instead of ~/.")
@click.option("--profile", "profile", default=None, help="Profile to write.")
@click.option(
    "--api-url",
    default=None,
    help=f"API to log in to. Defaults to the profile's, then {URL_VAR}, then production.",
)
@click.option(
    "--device-name",
    default=None,
    help="Name shown in the web app's token list. Defaults to this machine's hostname.",
)
@click.option(
    "--ability",
    "abilities",
    multiple=True,
    type=click.Choice(auth.ABILITIES),
    help="Ability to request. Repeat for several. Defaults to all of them.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Print the approval URL instead of opening a browser.",
)
@click.pass_context
@handle_errors
def login(
    ctx: click.Context,
    local: bool,
    profile: str | None,
    api_url: str | None,
    device_name: str | None,
    abilities: tuple[str, ...],
    no_browser: bool,
) -> None:
    """Approve this machine in a browser and save the token it is issued.

    The token is written to the selected profile exactly as `configure` would write it.
    It never passes through the browser: the browser carries a one-use code that only
    this process can redeem.
    """
    profile = _profile_for(ctx, profile)
    path = _config_path(local)
    existing = read_existing(path, profile)
    url = (
        api_url
        or existing.get("api_url")
        or ctx.obj["env"].get(URL_VAR, "").strip()
        or auth.DEFAULT_API_URL
    ).rstrip("/")
    device = (device_name or socket.gethostname()).strip()
    if not device:
        raise UsageError("A device name is required. Pass --device-name.")

    handshake = auth.Handshake()
    with auth.LoopbackListener() as listener:
        approve_url = auth.authorize_url(
            url, handshake, listener.redirect_uri, device, abilities or auth.ABILITIES
        )
        opened = False if no_browser else webbrowser.open(approve_url)
        if opened:
            click.echo("Opened a browser to approve this login. If it did not, visit:", err=True)
        else:
            click.echo("Open this URL in a browser to approve this login:", err=True)
        click.echo(f"\n    {approve_url}\n", err=True)
        click.echo("Waiting for approval...", err=True)
        result = listener.wait(auth.DEFAULT_WAIT_SECONDS)

    token = auth.exchange(url, auth.code_from(result, handshake), handshake.verifier)
    write_config(path, profile, url, token)
    click.echo(f"Logged in. Wrote profile '{profile}' to {path}")


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Choice([f.value for f in OutputFormat]),
    default=None,
    help="Output format. Defaults to table on a terminal, json when piped.",
)
@click.option("--query", default=None, help="JMESPath expression applied to the result.")
@click.pass_context
@handle_errors
def whoami(ctx: click.Context, output: str | None, query: str | None) -> None:
    """Show the user and abilities behind the configured token."""
    config = load_config(ctx.obj["env"], profile=ctx.obj.get("profile"))
    for warning in config.warnings:
        click.echo(f"Warning: {warning}", err=True)
    chosen = OutputFormat(output) if output else default_output(sys.stdout.isatty())
    click.echo(render(Client(config).request("GET", "/whoami"), chosen, query))


def _profile_for(ctx: click.Context, profile: str | None) -> str:
    """A subcommand's --profile, then the global one, then the environment."""
    return profile or ctx.obj.get("profile") or ctx.obj["env"].get(PROFILE_VAR) or DEFAULT_PROFILE


def _config_path(local: bool) -> Path:
    return config_path_in(Path.cwd()) if local else home_config_path()


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
