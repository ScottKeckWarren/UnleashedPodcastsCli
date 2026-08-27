"""Credential resolution: local file > home file > environment."""

import pytest

from unleashed.config import Config, load_config
from unleashed.errors import ConfigError, ExitCode

HOME_CONFIG = "[default]\napi_url = https://home.test/apiv1\napi_token = tok-home\n"


def test_reads_the_home_config(home_config):
    home_config(HOME_CONFIG)
    config = load_config({})
    assert config.base_url == "https://home.test/apiv1"
    assert config.token == "tok-home"


def test_a_local_config_overrides_the_home_config(home_config, local_config):
    home_config(HOME_CONFIG)
    local_config("[default]\napi_url = https://local.test/apiv1\napi_token = tok-local\n")
    config = load_config({})
    assert config.base_url == "https://local.test/apiv1"
    assert config.token == "tok-local"


def test_the_local_config_overrides_only_the_keys_it_sets(home_config, local_config):
    home_config(HOME_CONFIG)
    local_config("[default]\napi_token = tok-local\n")
    config = load_config({})
    assert config.base_url == "https://home.test/apiv1"
    assert config.token == "tok-local"


def test_a_local_config_is_found_from_a_subdirectory(home_config, local_config, work, monkeypatch):
    home_config(HOME_CONFIG)
    local_config("[default]\napi_token = tok-local\n")
    deep = work / "scripts" / "nested"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert load_config({}).token == "tok-local"


def test_the_nearest_local_config_wins_over_a_further_one(
    home_config, local_config, work, monkeypatch
):
    home_config(HOME_CONFIG)
    local_config("[default]\napi_token = tok-outer\n")
    inner = work / "inner"
    inner.mkdir()
    local_config("[default]\napi_token = tok-inner\n", directory=inner)
    monkeypatch.chdir(inner)
    assert load_config({}).token == "tok-inner"


def test_the_walk_up_stops_at_the_home_directory(home_config, home, monkeypatch):
    """A config in the home directory is the home config, not a local one found twice."""
    home_config(HOME_CONFIG)
    nested = home / "projects"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert load_config({}).token == "tok-home"


def test_environment_variables_are_the_lowest_precedence(home_config, env):
    home_config(HOME_CONFIG)
    assert load_config(env).token == "tok-home"


def test_environment_variables_are_used_when_no_config_file_exists(env):
    config = load_config(env)
    assert config.base_url == "https://example.test/apiv1"
    assert config.token == "tok-123"


def test_environment_variables_fill_a_gap_the_files_leave(home_config, env):
    home_config("[default]\napi_url = https://home.test/apiv1\n")
    config = load_config(env)
    assert config.base_url == "https://home.test/apiv1"
    assert config.token == "tok-123"


def test_a_named_profile_selects_its_own_section(home_config):
    home_config(HOME_CONFIG + "\n[client-a]\napi_url = https://a.test/apiv1\napi_token = tok-a\n")
    assert load_config({}, profile="client-a").token == "tok-a"


def test_a_profile_does_not_inherit_from_the_default_section(home_config):
    home_config(HOME_CONFIG + "\n[client-a]\napi_token = tok-a\n")
    with pytest.raises(ConfigError, match="api_url"):
        load_config({}, profile="client-a")


def test_a_local_profile_overrides_the_same_profile_at_home(home_config, local_config):
    home_config(HOME_CONFIG + "\n[client-a]\napi_url = https://a.test/apiv1\napi_token = tok-a\n")
    local_config("[client-a]\napi_token = tok-a-local\n")
    config = load_config({}, profile="client-a")
    assert config.base_url == "https://a.test/apiv1"
    assert config.token == "tok-a-local"


def test_the_profile_environment_variable_selects_a_profile(home_config):
    home_config(HOME_CONFIG + "\n[client-a]\napi_url = https://a.test/apiv1\napi_token = tok-a\n")
    assert load_config({"UNLEASHED_PROFILE": "client-a"}).token == "tok-a"


def test_an_explicit_profile_beats_the_environment_variable(home_config):
    home_config(HOME_CONFIG + "\n[client-a]\napi_url = https://a.test/apiv1\napi_token = tok-a\n")
    assert load_config({"UNLEASHED_PROFILE": "client-a"}, profile="default").token == "tok-home"


def test_an_unknown_profile_names_the_profiles_that_do_exist(home_config):
    home_config(HOME_CONFIG + "\n[client-a]\napi_url = x\napi_token = y\n")
    with pytest.raises(ConfigError) as exc:
        load_config({}, profile="nope")
    assert "nope" in str(exc.value)
    assert "client-a" in str(exc.value)


def test_a_missing_value_says_where_it_looked(home_config):
    home_config("[default]\napi_url = https://home.test/apiv1\n")
    with pytest.raises(ConfigError) as exc:
        load_config({})
    assert "api_token" in str(exc.value)
    assert ".unleashed/config" in str(exc.value)


def test_no_configuration_at_all_is_a_helpful_error():
    with pytest.raises(ConfigError) as exc:
        load_config({})
    assert "unleashed configure" in str(exc.value)


def test_a_blank_value_is_treated_as_absent(home_config, env):
    home_config("[default]\napi_url = https://home.test/apiv1\napi_token =   \n")
    assert load_config(env).token == "tok-123"


def test_a_trailing_slash_on_the_url_is_stripped(home_config):
    home_config("[default]\napi_url = https://home.test/apiv1/\napi_token = t\n")
    assert load_config({}).base_url == "https://home.test/apiv1"


def test_a_malformed_config_file_is_reported_with_its_path(home_config):
    home_config("this is not ini\n")
    with pytest.raises(ConfigError) as exc:
        load_config({})
    assert "config" in str(exc.value)


def test_a_config_error_exits_as_a_usage_error():
    assert ConfigError("x").exit_code is ExitCode.USAGE


def test_a_world_readable_config_is_reported(home_config):
    path = home_config(HOME_CONFIG)
    path.chmod(0o644)
    config = load_config({})
    assert config.warnings
    assert str(path) in config.warnings[0]


def test_a_private_config_produces_no_warning(home_config):
    home_config(HOME_CONFIG)
    assert load_config({}).warnings == ()


def test_the_config_records_which_profile_it_resolved(home_config):
    home_config(HOME_CONFIG)
    assert load_config({}).profile == "default"


def test_the_config_records_the_files_that_contributed(home_config, local_config):
    home_config(HOME_CONFIG)
    path = local_config("[default]\napi_token = tok-local\n")
    assert str(path) in load_config({}).sources[-1]


def test_the_token_never_appears_in_the_repr():
    assert "tok-123" not in repr(Config(base_url="https://x.test", token="tok-123"))


def test_auth_headers_carry_the_bearer_token(config):
    assert config.headers()["Authorization"] == "Bearer tok-123"
    assert config.headers()["Accept"] == "application/json"


def test_redacted_headers_hide_the_token(config):
    assert config.headers(redact=True)["Authorization"] == "Bearer ***redacted***"


def test_a_token_containing_a_percent_sign_survives_a_round_trip(home_config, home):
    """configparser interpolates % by default. A token is opaque and must not be touched."""
    from unleashed.config import home_config_path, write_config

    token = "abc%2Fdef%%ghi+/="
    write_config(home_config_path(home), "default", "https://home.test/apiv1", token)
    assert load_config({}).token == token
