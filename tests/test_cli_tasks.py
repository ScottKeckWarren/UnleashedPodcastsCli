"""Tasks: the caller's to-do list, five standard actions from a manifest."""

import json

import httpx
import pytest
import respx

from unleashed import auth
from unleashed.cli import cli
from unleashed.errors import ExitCode
from unleashed.resources.tasks import TASKS

BASE = "https://example.test/apiv1/tasks"
UUID = "task-uuid-1"


@pytest.fixture
def task_payload():
    return {
        "data": {
            "uuid": UUID,
            "title": "Book the guest",
            "description": None,
            "status": "todo",
            "due_date": "2026-11-10",
            "episode_uuid": "ep-1",
            "created_at": "2026-11-01T10:00:00Z",
            "updated_at": "2026-11-01T10:00:00Z",
        }
    }


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


def sent(route):
    return json.loads(route.calls.last.request.content)


# --- manifest ----------------------------------------------------------------


def test_only_title_is_required_on_create():
    assert [f.name for f in TASKS.required_create_fields] == ["title"]


def test_status_can_be_set_on_create():
    assert "status" in [f.name for f in TASKS.create_fields]


def test_login_asks_for_the_task_abilities():
    assert "tasks:read" in auth.ABILITIES
    assert "tasks:write" in auth.ABILITIES


def test_tasks_help_uses_the_singular(runner):
    result = runner.invoke(cli, ["tasks", "--help"])
    assert result.exit_code == ExitCode.SUCCESS
    assert "Create one task." in result.output


# --- the five actions --------------------------------------------------------


@respx.mock
def test_create_sends_a_date_and_an_episode(runner, configured, task_payload):
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json=task_payload))
    result = invoke(
        runner,
        [
            "tasks",
            "create",
            "--title",
            "Book the guest",
            "--due-date",
            "2026-11-10",
            "--episode-uuid",
            "ep-1",
            "--status",
            "in_progress",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {
        "title": "Book the guest",
        "due_date": "2026-11-10",
        "episode_uuid": "ep-1",
        "status": "in_progress",
    }


def test_create_rejects_a_malformed_date(runner, configured):
    result = runner.invoke(cli, ["tasks", "create", "--title", "x", "--due-date", "11/10/2026"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_list_passes_filters_and_sort(runner, configured, task_payload):
    route = respx.get(BASE).mock(
        return_value=httpx.Response(
            200, json={"data": [task_payload["data"]], "meta": {"last_page": 1}}
        )
    )
    result = invoke(
        runner,
        ["tasks", "list", "--status", "todo", "--episode-uuid", "ep-1", "--sort", "due_date"],
    )
    assert result.exit_code == ExitCode.SUCCESS
    params = route.calls.last.request.url.params
    assert params["status"] == "todo"
    assert params["episode_uuid"] == "ep-1"
    assert params["sort"] == "due_date"


@respx.mock
def test_get_reads_one_task(runner, configured, task_payload):
    respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=task_payload))
    result = invoke(runner, ["tasks", "get", UUID, "-o", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(result.output)["due_date"] == "2026-11-10"


@respx.mock
def test_update_completes_a_task_and_clears_the_due_date(runner, configured, task_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=task_payload))
    result = invoke(runner, ["tasks", "update", UUID, "--status", "completed", "--clear-due-date"])
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {"status": "completed", "due_date": None}


@respx.mock
def test_a_token_without_the_ability_exits_forbidden(runner, configured):
    respx.get(f"{BASE}/{UUID}").mock(
        return_value=httpx.Response(403, json={"message": "Invalid ability provided."})
    )
    result = invoke(runner, ["tasks", "get", UUID])
    assert result.exit_code == ExitCode.FORBIDDEN


@respx.mock
def test_delete_removes_one_task(runner, configured):
    route = respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    result = invoke(runner, ["tasks", "delete", UUID])
    assert result.exit_code == ExitCode.SUCCESS
    assert route.called
