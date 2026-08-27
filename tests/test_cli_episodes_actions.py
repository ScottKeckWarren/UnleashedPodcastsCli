"""list, get, update and delete, generated from the same manifest as create."""

import json

import httpx
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode

BASE = "https://example.test/apiv1/episodes"
UUID = "ep-uuid-1"


def page(records, *, current=1, last=1, total=None):
    return {
        "data": records,
        "links": {"first": "...", "last": "...", "prev": None, "next": None},
        "meta": {
            "current_page": current,
            "last_page": last,
            "per_page": 25,
            "total": total if total is not None else len(records),
        },
    }


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


# --- get ---------------------------------------------------------------------


@respx.mock
def test_get_fetches_one_record(runner, configured, episode_payload):
    respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=episode_payload))
    result = invoke(runner, ["episodes", "get", UUID, "--output", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(result.output)["uuid"] == "ep-uuid-1"


@respx.mock
def test_get_on_an_unknown_uuid_exits_five(runner, configured):
    respx.get(f"{BASE}/nope").mock(return_value=httpx.Response(404, json={"message": "Not found."}))
    assert invoke(runner, ["episodes", "get", "nope"]).exit_code == ExitCode.NOT_FOUND


def test_get_requires_a_uuid(runner, configured):
    assert runner.invoke(cli, ["episodes", "get"]).exit_code == ExitCode.USAGE


# --- delete ------------------------------------------------------------------


@respx.mock
def test_delete_reports_the_removed_uuid(runner, configured):
    respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    result = invoke(runner, ["episodes", "delete", UUID])
    assert result.exit_code == ExitCode.SUCCESS
    assert UUID in result.output


@respx.mock
def test_delete_emits_a_machine_readable_result(runner, configured):
    respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    result = invoke(runner, ["episodes", "delete", UUID, "--output", "json"])
    assert json.loads(result.output) == {"uuid": UUID, "deleted": True}


@respx.mock
def test_deleting_twice_exits_five(runner, configured):
    respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(404, json={}))
    assert invoke(runner, ["episodes", "delete", UUID]).exit_code == ExitCode.NOT_FOUND


@respx.mock
def test_delete_dry_run_sends_nothing(runner, configured):
    route = respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    result = invoke(runner, ["episodes", "delete", UUID, "--dry-run"])
    assert route.call_count == 0
    assert f"DELETE {BASE}/{UUID}" in result.output


# --- update ------------------------------------------------------------------


@respx.mock
def test_update_sends_only_the_flags_given(runner, configured, episode_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=episode_payload)
    )
    result = invoke(runner, ["episodes", "update", UUID, "--status", "Scheduled"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(route.calls.last.request.content) == {"status": "Scheduled"}


@respx.mock
def test_update_uses_patch(runner, configured, episode_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=episode_payload)
    )
    invoke(runner, ["episodes", "update", UUID, "--name", "New"])
    assert route.calls.last.request.method == "PATCH"


@respx.mock
def test_an_empty_update_is_a_successful_no_op(runner, configured, episode_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=episode_payload)
    )
    result = invoke(runner, ["episodes", "update", UUID])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(route.calls.last.request.content) == {}


@respx.mock
def test_clear_sends_an_explicit_null(runner, configured, episode_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=episode_payload)
    )
    invoke(runner, ["episodes", "update", UUID, "--clear-description"])
    assert json.loads(route.calls.last.request.content) == {"description": None}


def test_setting_and_clearing_the_same_field_is_a_usage_error(runner, configured):
    result = runner.invoke(
        cli, ["episodes", "update", UUID, "--description", "x", "--clear-description"]
    )
    assert result.exit_code == ExitCode.USAGE
    assert "clear-description" in result.output


def test_only_nullable_fields_get_a_clear_flag(runner, configured):
    help_text = runner.invoke(cli, ["episodes", "update", "--help"]).output
    assert "--clear-description" in help_text
    assert "--clear-canonical-url" in help_text
    assert "--clear-name" not in help_text
    assert "--clear-status" not in help_text


def test_immutable_fields_have_no_flag_on_update(runner, configured):
    help_text = runner.invoke(cli, ["episodes", "update", "--help"]).output
    assert "--podcast-uuid" not in help_text


def test_update_only_fields_appear_on_update(runner, configured):
    help_text = runner.invoke(cli, ["episodes", "update", "--help"]).output
    assert "--is-published" in help_text


@respx.mock
def test_a_boolean_flag_sends_a_real_boolean(runner, configured, episode_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=episode_payload)
    )
    invoke(runner, ["episodes", "update", UUID, "--is-published"])
    assert json.loads(route.calls.last.request.content) == {"is_published": True}


@respx.mock
def test_the_negative_form_of_a_boolean_flag_sends_false(runner, configured, episode_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(200, json=episode_payload)
    )
    invoke(runner, ["episodes", "update", UUID, "--no-is-published"])
    assert json.loads(route.calls.last.request.content) == {"is_published": False}


@respx.mock
def test_update_cli_input_json_rejects_an_immutable_field(runner, configured):
    payload = json.dumps({"podcast_uuid": "other"})
    result = runner.invoke(cli, ["episodes", "update", UUID, "--cli-input-json", payload])
    assert result.exit_code == ExitCode.USAGE
    assert "podcast_uuid" in result.output


# --- list --------------------------------------------------------------------


@respx.mock
def test_list_returns_the_records(runner, configured):
    respx.get(BASE).mock(return_value=httpx.Response(200, json=page([{"uuid": "a"}])))
    result = invoke(runner, ["episodes", "list", "--output", "json"])
    assert json.loads(result.output) == [{"uuid": "a"}]


@respx.mock
def test_list_walks_every_page_by_default(runner, configured):
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json=page([{"uuid": "a"}], current=1, last=3, total=3)),
            httpx.Response(200, json=page([{"uuid": "b"}], current=2, last=3, total=3)),
            httpx.Response(200, json=page([{"uuid": "c"}], current=3, last=3, total=3)),
        ]
    )
    result = invoke(runner, ["episodes", "list", "--output", "json"])
    assert [r["uuid"] for r in json.loads(result.output)] == ["a", "b", "c"]


@respx.mock
def test_no_paginate_returns_one_page(runner, configured):
    route = respx.get(BASE).mock(
        return_value=httpx.Response(200, json=page([{"uuid": "a"}], current=1, last=3))
    )
    result = invoke(runner, ["episodes", "list", "--no-paginate", "--output", "json"])
    assert route.call_count == 1
    assert len(json.loads(result.output)) == 1


@respx.mock
def test_max_items_stops_the_walk_early(runner, configured):
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json=page([{"uuid": "a"}, {"uuid": "b"}], current=1, last=5)),
            httpx.Response(200, json=page([{"uuid": "c"}], current=2, last=5)),
        ]
    )
    result = invoke(runner, ["episodes", "list", "--max-items", "3", "--output", "json"])
    assert [r["uuid"] for r in json.loads(result.output)] == ["a", "b", "c"]


@respx.mock
def test_an_empty_result_is_not_an_error(runner, configured):
    respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(runner, ["episodes", "list", "--output", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(result.output) == []


@respx.mock
def test_filters_become_query_parameters(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--status", "Edit", "--podcast-uuid", "pod-1"])
    query = route.calls.last.request.url.params
    assert query["status"] == "Edit"
    assert query["podcast_uuid"] == "pod-1"


@respx.mock
def test_an_omitted_filter_is_not_sent_at_all(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list"])
    assert "status" not in route.calls.last.request.url.params


@respx.mock
def test_a_boolean_filter_serialises_as_a_lowercase_word(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--no-is-published"])
    assert route.calls.last.request.url.params["is_published"] == "false"


@respx.mock
def test_a_date_filter_serialises_as_an_iso_date(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--target-published-since", "2026-09-15"])
    assert route.calls.last.request.url.params["target_published_since"] == "2026-09-15"


@respx.mock
def test_the_transcript_status_filter_accepts_the_literal_none(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--transcript-status", "none"])
    assert route.calls.last.request.url.params["transcript_status"] == "none"


def test_an_unknown_filter_value_is_rejected_locally(runner, configured):
    result = runner.invoke(cli, ["episodes", "list", "--status", "Nonsense"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_sort_is_passed_through(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--sort", "target_published_date"])
    assert route.calls.last.request.url.params["sort"] == "target_published_date"


@respx.mock
def test_a_descending_sort_keeps_its_minus_prefix(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--sort", "-created_at"])
    assert route.calls.last.request.url.params["sort"] == "-created_at"


def test_a_sort_outside_the_allowlist_is_caught_before_the_request(runner, configured):
    result = runner.invoke(cli, ["episodes", "list", "--sort", "nonsense"])
    assert result.exit_code == ExitCode.USAGE
    assert "target_published_date" in result.output


@respx.mock
def test_per_page_is_passed_through(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    invoke(runner, ["episodes", "list", "--per-page", "50"])
    assert route.calls.last.request.url.params["per_page"] == "50"


@respx.mock
def test_list_dry_run_sends_nothing(runner, configured):
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(runner, ["episodes", "list", "--dry-run", "--status", "Edit"])
    assert route.call_count == 0
    assert "GET" in result.output
    assert "status" in result.output


@respx.mock
def test_update_dry_run_shows_the_patch_body_and_sends_nothing(runner, configured):
    route = respx.patch(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json={}))
    result = invoke(runner, ["episodes", "update", UUID, "--dry-run", "--status", "Scheduled"])
    assert route.call_count == 0
    assert f"PATCH {BASE}/{UUID}" in result.output
    assert "Scheduled" in result.output


@respx.mock
def test_get_dry_run_sends_nothing(runner, configured):
    route = respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json={}))
    result = invoke(runner, ["episodes", "get", UUID, "--dry-run"])
    assert route.call_count == 0
    assert f"GET {BASE}/{UUID}" in result.output
