"""`unleashed configure` writes the file that everything else reads."""

import stat

from unleashed.cli import cli
from unleashed.config import load_config
from unleashed.errors import ExitCode


def run(runner, args, input_text=""):
    return runner.invoke(cli, args, input=input_text)


def test_configure_writes_the_home_config(runner, home):
    result = run(runner, ["configure"], "https://example.test/apiv1\ntok-abc\n")
    assert result.exit_code == ExitCode.SUCCESS
    assert load_config({}).token == "tok-abc"
    assert (home / ".unleashed" / "config").exists()


def test_configure_writes_a_private_file(runner, home):
    run(runner, ["configure"], "https://example.test/apiv1\ntok-abc\n")
    mode = (home / ".unleashed" / "config").stat().st_mode
    assert not mode & (stat.S_IRGRP | stat.S_IROTH)


def test_configure_local_writes_into_the_working_directory(runner, work):
    result = run(runner, ["configure", "--local"], "https://local.test/apiv1\ntok-local\n")
    assert result.exit_code == ExitCode.SUCCESS
    assert (work / ".unleashed" / "config").exists()


def test_configure_writes_a_named_profile(runner):
    run(runner, ["configure", "--profile", "client-a"], "https://a.test/apiv1\ntok-a\n")
    assert load_config({}, profile="client-a").token == "tok-a"


def test_configure_keeps_other_profiles_intact(runner):
    run(runner, ["configure"], "https://example.test/apiv1\ntok-default\n")
    run(runner, ["configure", "--profile", "client-a"], "https://a.test/apiv1\ntok-a\n")
    assert load_config({}).token == "tok-default"
    assert load_config({}, profile="client-a").token == "tok-a"


def test_configure_offers_the_existing_values_as_defaults(runner):
    run(runner, ["configure"], "https://example.test/apiv1\ntok-abc\n")
    result = run(runner, ["configure"], "\n\n")
    assert "https://example.test/apiv1" in result.output
    assert load_config({}).token == "tok-abc"


def test_configure_never_echoes_the_existing_token(runner):
    run(runner, ["configure"], "https://example.test/apiv1\ntok-secret\n")
    result = run(runner, ["configure"], "\n\n")
    assert "tok-secret" not in result.output


def test_configure_reports_where_it_wrote(runner, home):
    result = run(runner, ["configure"], "https://example.test/apiv1\ntok-abc\n")
    assert str(home / ".unleashed" / "config") in result.output


def test_configure_rejects_a_blank_url(runner):
    result = run(runner, ["configure"], "\n\n")
    assert result.exit_code == ExitCode.USAGE


def test_configure_rejects_a_blank_token(runner):
    result = run(runner, ["configure"], "https://example.test/apiv1\n\n")
    assert result.exit_code == ExitCode.USAGE
    assert "token" in result.output
