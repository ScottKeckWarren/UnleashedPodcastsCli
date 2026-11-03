"""Leads: prospective shows, five standard actions plus batch create."""

import json

import httpx
import pytest
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode

BASE = "https://example.test/apiv1/leads"
UUID = "lead-uuid-1"


@pytest.fixture
def lead_payload():
    return {
        "data": {
            "uuid": UUID,
            "show_name": "The Example Show",
            "name": "Sam Host",
            "email": "sam@example.test",
            "feed_url": "https://example.test/feed.xml",
            "status": "Identified",
            "llm_estimate": 72,
            "has_guests": True,
        }
    }


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


def sent(route):
    return json.loads(route.calls.last.request.content)


def test_leads_commands_are_exposed(runner):
    result = runner.invoke(cli, ["leads", "--help"])
    assert result.exit_code == ExitCode.SUCCESS
    for action in ("create", "list", "get", "update", "delete"):
        assert action in result.output


@respx.mock
def test_create_sends_one_lead(runner, configured, lead_payload):
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json=lead_payload))
    result = invoke(
        runner,
        [
            "leads",
            "create",
            "--show-name",
            "The Example Show",
            "--feed-url",
            "https://example.test/feed.xml",
            "--llm-estimate",
            "72",
            "--has-guests",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {
        "show_name": "The Example Show",
        "feed_url": "https://example.test/feed.xml",
        "llm_estimate": 72,
        "has_guests": True,
    }


@respx.mock
def test_a_duplicate_single_lead_exits_conflict(runner, configured):
    respx.post(BASE).mock(
        return_value=httpx.Response(409, json={"message": "Duplicate lead.", "uuid": UUID})
    )
    result = invoke(runner, ["leads", "create", "--show-name", "x", "--feed-url", "y"])
    assert result.exit_code == ExitCode.CONFLICT


@respx.mock
def test_list_filters_by_minimum_estimate(runner, configured, lead_payload):
    route = respx.get(BASE).mock(
        return_value=httpx.Response(
            200, json={"data": [lead_payload["data"]], "meta": {"last_page": 1}}
        )
    )
    result = invoke(runner, ["leads", "list", "--min-llm-estimate", "50", "--sort", "-found_at"])
    assert result.exit_code == ExitCode.SUCCESS
    params = route.calls.last.request.url.params
    assert params["min_llm_estimate"] == "50"
    assert params["sort"] == "-found_at"


@respx.mock
def test_update_moves_a_lead_along_the_pipeline(runner, configured, lead_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=lead_payload))
    result = invoke(runner, ["leads", "update", UUID, "--status", "Contacted", "--clear-notes"])
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {"status": "Contacted", "notes": None}


@respx.mock
def test_get_and_delete_one_lead(runner, configured, lead_payload):
    respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=lead_payload))
    deleted = respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    assert invoke(runner, ["leads", "get", UUID]).exit_code == ExitCode.SUCCESS
    assert invoke(runner, ["leads", "delete", UUID]).exit_code == ExitCode.SUCCESS
    assert deleted.called


# --- batch create ------------------------------------------------------------


def batch_result(*outcomes):
    results = [
        {"index": i, "outcome": o, "uuid": None if o == "invalid" else f"lead-{i}"}
        | (
            {"errors": {"show_name": ["The show name field is required."]}}
            if o == "invalid"
            else {}
        )
        for i, o in enumerate(outcomes)
    ]
    counts = {k: list(outcomes).count(k) for k in ("created", "duplicate", "invalid")}
    return {"counts": counts, "results": results}


def items(n):
    return [
        {"show_name": f"Show {i}", "feed_url": f"https://example.test/{i}.xml"} for i in range(n)
    ]


def test_leads_accept_batches_of_up_to_25():
    from unleashed.resources.leads import LEADS

    assert LEADS.batch_create_max == 25


def test_a_batch_limit_must_be_positive():
    from unleashed.manifest import Field, ManifestError, Resource

    with pytest.raises(ManifestError, match="batch"):
        Resource(name="x", fields=[Field("a")], batch_create_max=0)


@respx.mock
def test_a_json_list_is_sent_as_a_batch(runner, configured):
    payload = batch_result("created", "duplicate")
    route = respx.post(BASE).mock(return_value=httpx.Response(207, json=payload))
    result = invoke(
        runner, ["leads", "create", "--cli-input-json", json.dumps(items(2)), "-o", "json"]
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == items(2)
    assert json.loads(result.stdout) == payload


@respx.mock
def test_an_invalid_item_prints_the_outcomes_and_exits_validation(runner, configured):
    payload = batch_result("created", "invalid")
    respx.post(BASE).mock(return_value=httpx.Response(207, json=payload))
    result = invoke(
        runner, ["leads", "create", "--cli-input-json", json.dumps(items(2)), "-o", "json"]
    )
    assert result.exit_code == ExitCode.VALIDATION
    assert json.loads(result.stdout) == payload
    assert "1 of 2" in result.stderr
    assert "item 1" in result.stderr
    assert "show_name" in result.stderr


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ([], "at least one"),
        (items(26), "at most 25"),
        (["not an object"], "item 0"),
        ([{"show_name": "x", "uuid": "nope"}], "item 0"),
        ([{"show_name": "x"}, {"feed_url": "y"}], "item 1"),
    ],
)
def test_a_bad_batch_is_refused_before_sending(runner, configured, body, message):
    result = invoke(runner, ["leads", "create", "--cli-input-json", json.dumps(body)])
    assert result.exit_code == ExitCode.USAGE
    assert message in result.output


def test_a_batch_dry_run_prints_the_list(runner, configured):
    result = invoke(
        runner, ["leads", "create", "--cli-input-json", json.dumps(items(2)), "--dry-run"]
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert '"show_name": "Show 1"' in result.output


def test_a_resource_without_batches_still_rejects_a_list(runner, configured):
    result = invoke(runner, ["ideas", "create", "--cli-input-json", '[{"title": "x"}]'])
    assert result.exit_code == ExitCode.USAGE
    assert "JSON object" in result.output


def test_a_list_is_never_accepted_on_update(runner, configured):
    result = invoke(runner, ["leads", "update", UUID, "--cli-input-json", '[{"notes": "x"}]'])
    assert result.exit_code == ExitCode.USAGE
    assert "JSON object" in result.output
