"""People: map-typed metadata flags and the metadata merge/replace sub-resource."""

import json

import httpx
import pytest
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode
from unleashed.manifest import Field, KeyValueMap, ManifestError, Resource
from unleashed.resources.people import PEOPLE

BASE = "https://example.test/apiv1/people"
UUID = "person-uuid-1"


@pytest.fixture
def person_payload():
    return {
        "data": {
            "uuid": UUID,
            "name": "Ada Lovelace",
            "email": "ada@example.test",
            "bio": None,
            "is_public": False,
            "claimed_user_uuid": None,
            "last_outreach": None,
            "metadata": {"twitter": "@ada"},
            "created_at": "2026-09-22T10:00:00Z",
            "updated_at": "2026-09-22T10:00:00Z",
        }
    }


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


def sent(route):
    return json.loads(route.calls.last.request.content)


# --- manifest ----------------------------------------------------------------


def test_only_name_is_required_on_create():
    assert [f.name for f in PEOPLE.required_create_fields] == ["name"]


def test_last_outreach_cannot_be_cleared():
    assert "last_outreach" not in [f.name for f in PEOPLE.nullable_update_fields]


def test_people_read_as_a_person():
    assert PEOPLE.singular == "person"


def test_a_map_cannot_share_a_name_with_an_attachment():
    from unleashed.manifest import Attachment

    with pytest.raises(ManifestError, match="duplicate sub-resources"):
        Resource(
            name="x",
            fields=[Field("a")],
            attachments=[Attachment("extra", "id")],
            maps=[KeyValueMap("extra")],
        )


def test_people_help_uses_the_singular(runner):
    result = runner.invoke(cli, ["people", "--help"])
    assert "Create one person." in result.output


# --- the five actions --------------------------------------------------------


@respx.mock
def test_create_builds_metadata_from_pairs(runner, configured, person_payload):
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json=person_payload))
    result = invoke(
        runner,
        [
            "people",
            "create",
            "--name",
            "Ada Lovelace",
            "--metadata",
            "twitter=@ada",
            "--metadata",
            "note=a=b",
            "--last-outreach",
            "2026-09-01",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {
        "name": "Ada Lovelace",
        "metadata": {"twitter": "@ada", "note": "a=b"},
        "last_outreach": "2026-09-01",
    }


@respx.mock
def test_create_without_metadata_sends_no_metadata_key(runner, configured, person_payload):
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json=person_payload))
    invoke(runner, ["people", "create", "--name", "Ada"])
    assert sent(route) == {"name": "Ada"}


@pytest.mark.parametrize("pair", ["no-equals", "=value", "  =value"])
def test_a_malformed_pair_is_a_usage_error(runner, configured, pair):
    result = invoke(runner, ["people", "create", "--name", "Ada", "--metadata", pair])
    assert result.exit_code == ExitCode.USAGE
    assert "KEY=VALUE" in result.output


@respx.mock
def test_update_sends_metadata_and_clears_email(runner, configured, person_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=person_payload)
    )
    invoke(runner, ["people", "update", UUID, "--clear-email", "--metadata", "tier=gold"])
    assert sent(route) == {"metadata": {"tier": "gold"}, "email": None}


@respx.mock
def test_list_passes_filters(runner, configured):
    route = respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"last_page": 1}})
    )
    invoke(
        runner,
        [
            "people",
            "list",
            "--no-has-email",
            "--is-claimed",
            "--last-outreach-before",
            "2026-06-01",
            "--sort",
            "last_outreach",
        ],
    )
    params = route.calls.last.request.url.params
    assert params["has_email"] == "false"
    assert params["is_claimed"] == "true"
    assert params["last_outreach_before"] == "2026-06-01"
    assert params["sort"] == "last_outreach"


@respx.mock
def test_get_renders_metadata_in_a_table(runner, configured, person_payload):
    respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=person_payload))
    result = invoke(runner, ["people", "get", UUID, "-o", "table"])
    assert '{"twitter": "@ada"}' in result.output


# --- metadata merge ----------------------------------------------------------


@respx.mock
def test_merge_sets_and_unsets_keys(runner, configured, person_payload):
    route = respx.patch(f"{BASE}/{UUID}/metadata").mock(
        return_value=httpx.Response(200, json=person_payload)
    )
    result = invoke(
        runner,
        ["people", "metadata", "merge", UUID, "--set", "tier=gold", "--unset", "twitter"],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {"tier": "gold", "twitter": None}


@respx.mock
def test_merge_takes_typed_values_from_json(runner, configured, person_payload):
    route = respx.patch(f"{BASE}/{UUID}/metadata").mock(
        return_value=httpx.Response(200, json=person_payload)
    )
    payload = '{"episodes": 3, "vip": true, "old": null, "score": 9.5}'
    invoke(runner, ["people", "metadata", "merge", UUID, "--cli-input-json", payload])
    assert sent(route) == {"episodes": 3, "vip": True, "old": None, "score": 9.5}


def test_merge_rejects_nested_json(runner, configured):
    result = invoke(
        runner,
        ["people", "metadata", "merge", UUID, "--cli-input-json", '{"a": {"b": 1}, "c": [1]}'],
    )
    assert result.exit_code == ExitCode.USAGE
    assert "a, c" in result.output


@pytest.mark.parametrize("payload", ["not json", "[1, 2]"])
def test_merge_rejects_json_that_is_not_an_object(runner, configured, payload):
    result = invoke(runner, ["people", "metadata", "merge", UUID, "--cli-input-json", payload])
    assert result.exit_code == ExitCode.USAGE


def test_merge_rejects_json_with_flags(runner, configured):
    result = invoke(
        runner,
        ["people", "metadata", "merge", UUID, "--set", "a=b", "--cli-input-json", "{}"],
    )
    assert result.exit_code == ExitCode.USAGE
    assert "cannot be combined" in result.output


def test_merge_dry_run_sends_nothing(runner, configured):
    with respx.mock:
        route = respx.patch(f"{BASE}/{UUID}/metadata")
        result = invoke(
            runner, ["people", "metadata", "merge", UUID, "--unset", "twitter", "--dry-run"]
        )
        assert not route.called
    assert f"PATCH {BASE}/{UUID}/metadata" in result.output
    assert '"twitter": null' in result.output


# --- metadata replace --------------------------------------------------------


@respx.mock
def test_replace_puts_the_whole_map(runner, configured, person_payload):
    route = respx.put(f"{BASE}/{UUID}/metadata").mock(
        return_value=httpx.Response(200, json=person_payload)
    )
    invoke(runner, ["people", "metadata", "replace", UUID, "--set", "only=this"])
    assert sent(route) == {"only": "this"}


def test_replace_with_nothing_refuses_to_clear_by_accident(runner, configured):
    with respx.mock:
        route = respx.put(f"{BASE}/{UUID}/metadata")
        result = invoke(runner, ["people", "metadata", "replace", UUID])
        assert not route.called
    assert result.exit_code == ExitCode.USAGE
    assert "--cli-input-json '{}'" in result.output


@respx.mock
def test_replace_with_an_empty_object_clears_every_key(runner, configured, person_payload):
    route = respx.put(f"{BASE}/{UUID}/metadata").mock(
        return_value=httpx.Response(200, json=person_payload)
    )
    invoke(runner, ["people", "metadata", "replace", UUID, "--cli-input-json", "{}"])
    assert sent(route) == {}


def test_replace_has_no_unset_flag(runner, configured):
    result = runner.invoke(cli, ["people", "metadata", "replace", UUID, "--unset", "a"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_metadata_on_an_unknown_person_exits_five(runner, configured):
    respx.patch(f"{BASE}/nope/metadata").mock(return_value=httpx.Response(404, json={}))
    result = invoke(runner, ["people", "metadata", "merge", "nope", "--set", "a=b"])
    assert result.exit_code == ExitCode.NOT_FOUND
