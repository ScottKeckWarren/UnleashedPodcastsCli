import json

import httpx
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode

URL = "https://example.test/apiv1/episodes"
REQUIRED = [
    "--podcast-uuid",
    "pod-uuid-1",
    "--name",
    "Episode 101",
    "--target-published-date",
    "2026-09-15",
]


def invoke(runner, env, args):
    return runner.invoke(cli, args, env=env, catch_exceptions=False)


@respx.mock
def test_create_sends_only_the_flags_that_were_given(runner, env, episode_payload):
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    result = invoke(runner, env, ["episodes", "create", *REQUIRED])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(route.calls.last.request.content) == {
        "podcast_uuid": "pod-uuid-1",
        "name": "Episode 101",
        "target_published_date": "2026-09-15",
    }


@respx.mock
def test_optional_flags_are_included_when_given(runner, env, episode_payload):
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    invoke(
        runner,
        env,
        ["episodes", "create", *REQUIRED, "--status", "Draft", "--description", "Show notes here."],
    )
    body = json.loads(route.calls.last.request.content)
    assert body["status"] == "Draft"
    assert body["description"] == "Show notes here."


def test_a_missing_required_flag_is_a_usage_error(runner, env):
    result = runner.invoke(cli, ["episodes", "create", "--name", "x"], env=env)
    assert result.exit_code == ExitCode.USAGE
    assert "--podcast-uuid" in result.output


def test_read_only_fields_have_no_flag_at_all(runner, env):
    help_text = runner.invoke(cli, ["episodes", "create", "--help"], env=env).output
    assert "--transcript-status" not in help_text
    assert "--podcast-name" not in help_text
    assert "--uuid" not in help_text


def test_update_only_fields_have_no_flag_on_create(runner, env):
    help_text = runner.invoke(cli, ["episodes", "create", "--help"], env=env).output
    assert "--is-published" not in help_text


def test_an_unknown_status_is_rejected_locally_before_any_request(runner, env):
    result = runner.invoke(cli, ["episodes", "create", *REQUIRED, "--status", "Nonsense"], env=env)
    assert result.exit_code == ExitCode.USAGE
    assert "Nonsense" in result.output


def test_a_malformed_date_is_rejected_locally(runner, env):
    result = runner.invoke(cli, ["episodes", "create", *REQUIRED[:-1], "15-09-2026"], env=env)
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_dry_run_prints_the_request_and_sends_nothing(runner, env):
    route = respx.post(URL).mock(return_value=httpx.Response(201, json={}))
    result = invoke(runner, env, ["episodes", "create", "--dry-run", *REQUIRED])
    assert result.exit_code == ExitCode.SUCCESS
    assert route.call_count == 0
    assert "POST https://example.test/apiv1/episodes" in result.output
    assert "Episode 101" in result.output


@respx.mock
def test_dry_run_redacts_the_token(runner, env):
    result = invoke(runner, env, ["episodes", "create", "--dry-run", *REQUIRED])
    assert "tok-123" not in result.output
    assert "***redacted***" in result.output


@respx.mock
def test_json_output_emits_the_created_record(runner, env, episode_payload):
    respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    result = invoke(runner, env, ["episodes", "create", "--output", "json", *REQUIRED])
    assert json.loads(result.output)["uuid"] == "ep-uuid-1"


@respx.mock
def test_a_query_plucks_a_field_from_the_created_record(runner, env, episode_payload):
    respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    result = invoke(
        runner, env, ["episodes", "create", "--query", "uuid", "--output", "text", *REQUIRED]
    )
    assert result.output.strip() == "ep-uuid-1"


@respx.mock
def test_cli_input_json_is_an_alternative_to_flags(runner, env, episode_payload):
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    payload = json.dumps(
        {"podcast_uuid": "pod-uuid-1", "name": "Episode 101", "target_published_date": "2026-09-15"}
    )
    result = invoke(runner, env, ["episodes", "create", "--cli-input-json", payload])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(route.calls.last.request.content)["name"] == "Episode 101"


def test_cli_input_json_cannot_be_combined_with_field_flags(runner, env):
    result = runner.invoke(
        cli, ["episodes", "create", "--cli-input-json", "{}", "--name", "x"], env=env
    )
    assert result.exit_code == ExitCode.USAGE
    assert "cli-input-json" in result.output


def test_malformed_cli_input_json_is_a_usage_error(runner, env):
    result = runner.invoke(cli, ["episodes", "create", "--cli-input-json", "{oops"], env=env)
    assert result.exit_code == ExitCode.USAGE


def test_cli_input_json_must_be_an_object(runner, env):
    result = runner.invoke(cli, ["episodes", "create", "--cli-input-json", "[]"], env=env)
    assert result.exit_code == ExitCode.USAGE


def test_cli_input_json_rejects_a_read_only_field(runner, env):
    payload = json.dumps(
        {
            "podcast_uuid": "p",
            "name": "n",
            "target_published_date": "2026-09-15",
            "transcript_status": "Completed",
        }
    )
    result = runner.invoke(cli, ["episodes", "create", "--cli-input-json", payload], env=env)
    assert result.exit_code == ExitCode.USAGE
    assert "transcript_status" in result.output


def test_cli_input_json_reports_a_missing_required_field(runner, env):
    result = runner.invoke(cli, ["episodes", "create", "--cli-input-json", "{}"], env=env)
    assert result.exit_code == ExitCode.USAGE
    assert "podcast_uuid" in result.output


@respx.mock
def test_a_validation_error_exits_three_and_prints_the_field_messages(runner, env):
    body = {
        "message": "The given data was invalid.",
        "errors": {"podcast_uuid": ["The selected podcast uuid is invalid."]},
    }
    respx.post(URL).mock(return_value=httpx.Response(422, json=body))
    result = invoke(runner, env, ["episodes", "create", *REQUIRED])
    assert result.exit_code == ExitCode.VALIDATION
    assert "podcast_uuid" in result.output
    assert "The selected podcast uuid is invalid." in result.output


@respx.mock
def test_an_auth_failure_exits_four(runner, env):
    respx.post(URL).mock(return_value=httpx.Response(401, json={"message": "Unauthenticated."}))
    result = invoke(runner, env, ["episodes", "create", *REQUIRED])
    assert result.exit_code == ExitCode.AUTH


@respx.mock
def test_a_server_error_exits_one(runner, env):
    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    result = invoke(runner, env, ["episodes", "create", *REQUIRED])
    assert result.exit_code == ExitCode.ERROR


def test_a_missing_token_fails_before_any_request_is_attempted(runner, env):
    del env["UNLEASHED_API_TOKEN"]
    result = runner.invoke(cli, ["episodes", "create", *REQUIRED], env=env)
    assert result.exit_code == ExitCode.USAGE
    assert "UNLEASHED_API_TOKEN" in result.output


def test_dry_run_still_requires_configuration(runner, env):
    del env["UNLEASHED_API_URL"]
    result = runner.invoke(cli, ["episodes", "create", "--dry-run", *REQUIRED], env=env)
    assert result.exit_code == ExitCode.USAGE


def test_the_version_flag_reports_a_version(runner, env):
    result = runner.invoke(cli, ["--version"], env=env)
    assert result.exit_code == ExitCode.SUCCESS
    assert "0.1.0" in result.output


def test_all_five_standard_actions_are_exposed(runner, env):
    help_text = runner.invoke(cli, ["episodes", "--help"], env=env).output
    for action in ("create", "list", "get", "update", "delete"):
        assert action in help_text


def test_leads_commands_are_not_exposed_in_v0_1(runner, env):
    result = runner.invoke(cli, ["leads", "--help"], env=env)
    assert result.exit_code != ExitCode.SUCCESS


@respx.mock
def test_credentials_come_from_the_config_file_when_no_env_is_set(
    runner, home_config, episode_payload
):
    home_config("[default]\napi_url = https://example.test/apiv1\napi_token = tok-file\n")
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    result = runner.invoke(cli, ["episodes", "create", *REQUIRED], catch_exceptions=False)
    assert result.exit_code == ExitCode.SUCCESS
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-file"


@respx.mock
def test_a_profile_selects_a_different_account(runner, home_config, episode_payload):
    home_config(
        "[default]\napi_url = https://example.test/apiv1\napi_token = tok-default\n"
        "\n[client-a]\napi_url = https://example.test/apiv1\napi_token = tok-a\n"
    )
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    runner.invoke(
        cli, ["--profile", "client-a", "episodes", "create", *REQUIRED], catch_exceptions=False
    )
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-a"


@respx.mock
def test_a_local_config_overrides_the_home_account(
    runner, home_config, local_config, episode_payload
):
    home_config("[default]\napi_url = https://example.test/apiv1\napi_token = tok-home\n")
    local_config("[default]\napi_token = tok-local\n")
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    runner.invoke(cli, ["episodes", "create", *REQUIRED], catch_exceptions=False)
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-local"


def test_an_unknown_profile_is_a_usage_error(runner, configured):
    result = runner.invoke(cli, ["--profile", "nope", "episodes", "create", *REQUIRED])
    assert result.exit_code == ExitCode.USAGE
    assert "nope" in result.output


@respx.mock
def test_a_world_readable_config_warns_but_still_works(runner, home_config, episode_payload):
    path = home_config("[default]\napi_url = https://example.test/apiv1\napi_token = t\n")
    path.chmod(0o644)
    respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    result = runner.invoke(cli, ["episodes", "create", *REQUIRED], catch_exceptions=False)
    assert result.exit_code == ExitCode.SUCCESS
    assert "readable" in result.output


@respx.mock
def test_dry_run_names_the_profile_and_the_config_that_supplied_it(runner, home_config):
    home_config("[default]\napi_url = https://example.test/apiv1\napi_token = t\n")
    result = runner.invoke(
        cli, ["episodes", "create", "--dry-run", *REQUIRED], catch_exceptions=False
    )
    assert "profile default" in result.output
