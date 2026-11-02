"""Ideas: the episode-idea backlog, five standard actions from a manifest."""

import json

import httpx
import pytest
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode
from unleashed.resources.ideas import IDEAS

BASE = "https://example.test/apiv1/ideas"
UUID = "idea-uuid-1"


@pytest.fixture
def idea_payload():
    return {
        "data": {
            "uuid": UUID,
            "podcast_uuid": None,
            "title": "Interview a sound engineer",
            "description": None,
            "status": "open",
            "position": 3,
            "converted_episode_uuid": None,
            "created_at": "2026-10-01T10:00:00Z",
            "updated_at": "2026-10-01T10:00:00Z",
        }
    }


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


def sent(route):
    return json.loads(route.calls.last.request.content)


# --- manifest ----------------------------------------------------------------


def test_only_title_is_required_on_create():
    assert [f.name for f in IDEAS.required_create_fields] == ["title"]


def test_status_and_conversion_are_set_only_on_update():
    create = [f.name for f in IDEAS.create_fields]
    update = [f.name for f in IDEAS.update_fields]
    assert "status" not in create
    assert "converted_episode_uuid" not in create
    assert "status" in update
    assert "converted_episode_uuid" in update


def test_ideas_help_uses_the_singular(runner):
    result = runner.invoke(cli, ["ideas", "--help"])
    assert result.exit_code == ExitCode.SUCCESS
    assert "Create one idea." in result.output


# --- the five actions --------------------------------------------------------


@respx.mock
def test_create_sends_only_the_flags_given(runner, configured, idea_payload):
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json=idea_payload))
    result = invoke(
        runner,
        [
            "ideas",
            "create",
            "--title",
            "Interview a sound engineer",
            "--position",
            "3",
            "--podcast-uuid",
            "pod-1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {
        "title": "Interview a sound engineer",
        "position": 3,
        "podcast_uuid": "pod-1",
    }
    assert json.loads(result.output)["uuid"] == UUID


def test_create_without_a_title_is_a_usage_error(runner, configured):
    result = invoke(runner, ["ideas", "create", "--position", "1"])
    assert result.exit_code == ExitCode.USAGE
    assert "--title" in result.output


@respx.mock
def test_list_passes_filters_and_sort(runner, configured, idea_payload):
    route = respx.get(BASE).mock(
        return_value=httpx.Response(
            200, json={"data": [idea_payload["data"]], "meta": {"last_page": 1}}
        )
    )
    result = invoke(
        runner,
        ["ideas", "list", "--status", "open", "--unassigned", "--sort", "-position", "-o", "json"],
    )
    assert result.exit_code == ExitCode.SUCCESS
    params = route.calls.last.request.url.params
    assert params["status"] == "open"
    assert params["unassigned"] == "true"
    assert params["sort"] == "-position"


def test_list_rejects_an_unknown_sort(runner, configured):
    result = invoke(runner, ["ideas", "list", "--sort", "due_date"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_get_reads_one_idea(runner, configured, idea_payload):
    respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=idea_payload))
    result = invoke(runner, ["ideas", "get", UUID, "-o", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(result.output)["title"] == "Interview a sound engineer"


@respx.mock
def test_update_converts_an_idea_and_clears_the_podcast(runner, configured, idea_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=idea_payload))
    result = invoke(
        runner,
        [
            "ideas",
            "update",
            UUID,
            "--status",
            "converted",
            "--converted-episode-uuid",
            "ep-1",
            "--clear-podcast-uuid",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {
        "status": "converted",
        "converted_episode_uuid": "ep-1",
        "podcast_uuid": None,
    }


def test_update_rejects_an_unknown_status(runner, configured):
    result = runner.invoke(cli, ["ideas", "update", UUID, "--status", "done"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_delete_removes_one_idea(runner, configured):
    route = respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    result = invoke(runner, ["ideas", "delete", UUID, "-o", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert route.called
    assert json.loads(result.output) == {"uuid": UUID, "deleted": True}
