"""The process entry point: exit codes, not exceptions."""

import httpx
import respx

from unleashed.cli import main
from unleashed.errors import ExitCode

URL = "https://example.test/apiv1/episodes"
ARGS = [
    "episodes",
    "create",
    "--podcast-uuid",
    "p",
    "--name",
    "n",
    "--target-published-date",
    "2026-09-15",
]


@respx.mock
def test_main_returns_zero_on_success(env, episode_payload, capsys):
    respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    assert main(ARGS, env=env) == ExitCode.SUCCESS


@respx.mock
def test_main_returns_the_error_exit_code(env, capsys):
    respx.post(URL).mock(return_value=httpx.Response(401, json={"message": "Unauthenticated."}))
    assert main(ARGS, env=env) == ExitCode.AUTH


def test_main_returns_usage_for_an_unknown_command(env, capsys):
    assert main(["nonsense"], env=env) == ExitCode.USAGE


def test_main_prints_field_errors_for_a_validation_failure(env, capsys):
    with respx.mock:
        respx.post(URL).mock(
            return_value=httpx.Response(
                422,
                json={
                    "message": "The given data was invalid.",
                    "errors": {"name": ["The name field is required."]},
                },
            )
        )
        assert main(ARGS, env=env) == ExitCode.VALIDATION
    assert "The name field is required." in capsys.readouterr().err


def test_main_reports_missing_configuration_as_usage(env, capsys):
    del env["UNLEASHED_API_TOKEN"]
    assert main(ARGS, env=env) == ExitCode.USAGE
    assert "UNLEASHED_API_TOKEN" in capsys.readouterr().err


def test_main_falls_back_to_the_process_environment(monkeypatch, capsys):
    monkeypatch.delenv("UNLEASHED_API_TOKEN", raising=False)
    monkeypatch.setenv("UNLEASHED_API_URL", "https://example.test/apiv1")
    assert main(ARGS) == ExitCode.USAGE


def test_main_reports_an_abort_as_a_generic_error(env, monkeypatch, capsys):
    import click

    from unleashed import cli as cli_module

    def boom(*_args, **_kwargs):
        raise click.exceptions.Abort()

    monkeypatch.setattr(cli_module.cli, "main", boom)
    assert main(ARGS, env=env) == ExitCode.ERROR
    assert "Aborted." in capsys.readouterr().err


def test_the_version_option_reports_the_package_version(env, capsys):
    assert main(["--version"], env=env) == ExitCode.SUCCESS
    assert "0.1.0" in capsys.readouterr().out
