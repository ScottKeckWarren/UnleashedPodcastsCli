"""Short form videos: the second shipped manifest, plus the video-file attachment."""

import json

import httpx
import pytest
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode
from unleashed.manifest import Attachment, Field, ManifestError, Resource
from unleashed.resources.short_form_videos import SHORT_FORM_VIDEOS

BASE = "https://example.test/apiv1/short-form-videos"
UUID = "sfv-uuid-1"


@pytest.fixture
def short_payload():
    return {
        "data": {
            "uuid": UUID,
            "podcast_uuid": None,
            "podcast_episode_uuid": None,
            "video_file_uuid": None,
            "title": "Three mistakes new hosts make",
            "script": "Mistake one...",
            "body": "Caption",
            "micro_body": None,
            "origin": "manual",
            "target_date": "2026-10-01",
            "published_date": None,
            "created_at": "2026-09-22T10:00:00Z",
            "updated_at": "2026-09-22T10:00:00Z",
        }
    }


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


def sent(route):
    return json.loads(route.calls.last.request.content)


# --- manifest ----------------------------------------------------------------


def test_only_title_is_required_on_create():
    assert [f.name for f in SHORT_FORM_VIDEOS.required_create_fields] == ["title"]


def test_server_assigned_fields_have_no_flag():
    writable = {f.name for f in SHORT_FORM_VIDEOS.writable_fields}
    assert not writable & {"uuid", "origin", "video_file_uuid", "created_at", "updated_at"}


def test_the_singular_reads_as_words():
    assert SHORT_FORM_VIDEOS.singular == "short form video"


def test_a_resource_rejects_duplicate_attachments():
    with pytest.raises(ManifestError, match="duplicate sub-resources"):
        Resource(
            name="x",
            fields=[Field("a")],
            attachments=[Attachment("file", "file_uuid"), Attachment("file", "file_uuid")],
        )


# --- the five actions --------------------------------------------------------


@respx.mock
def test_create_sends_only_the_given_flags(runner, configured, short_payload):
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json=short_payload))
    result = invoke(
        runner,
        [
            "short-form-videos",
            "create",
            "--title",
            "Three mistakes new hosts make",
            "--target-date",
            "2026-10-01",
            "--podcast-episode-uuid",
            "ep-1",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {
        "title": "Three mistakes new hosts make",
        "target_date": "2026-10-01",
        "podcast_episode_uuid": "ep-1",
    }
    assert json.loads(result.output)["uuid"] == UUID


def test_create_without_a_title_is_a_usage_error(runner, configured):
    result = invoke(runner, ["short-form-videos", "create", "--body", "Caption"])
    assert result.exit_code == ExitCode.USAGE
    assert "--title" in result.output


@respx.mock
def test_list_passes_filters_and_sort(runner, configured):
    route = respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"last_page": 1}})
    )
    result = invoke(
        runner,
        [
            "short-form-videos",
            "list",
            "--origin",
            "generated",
            "--standalone",
            "--title",
            "mistake",
            "--sort",
            "-target_date",
        ],
    )
    assert result.exit_code == ExitCode.SUCCESS
    params = route.calls.last.request.url.params
    assert params["origin"] == "generated"
    assert params["standalone"] == "true"
    assert params["title"] == "mistake"
    assert params["sort"] == "-target_date"


def test_list_rejects_a_sort_outside_the_allowlist(runner, configured):
    result = invoke(runner, ["short-form-videos", "list", "--sort", "script"])
    assert result.exit_code == ExitCode.USAGE
    assert "updated_at" in result.output


@respx.mock
def test_get_fetches_one(runner, configured, short_payload):
    respx.get(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=short_payload))
    result = invoke(runner, ["short-form-videos", "get", UUID, "--query", "title", "-o", "text"])
    assert result.output.strip() == "Three mistakes new hosts make"


@respx.mock
def test_update_can_detach_the_podcast(runner, configured, short_payload):
    route = respx.patch(f"{BASE}/{UUID}").mock(return_value=httpx.Response(200, json=short_payload))
    invoke(
        runner,
        ["short-form-videos", "update", UUID, "--clear-podcast-uuid", "--micro-body", "Short"],
    )
    assert sent(route) == {"micro_body": "Short", "podcast_uuid": None}


@respx.mock
def test_delete_reports_the_removed_uuid(runner, configured):
    respx.delete(f"{BASE}/{UUID}").mock(return_value=httpx.Response(204))
    result = invoke(runner, ["short-form-videos", "delete", UUID, "-o", "json"])
    assert json.loads(result.output) == {"uuid": UUID, "deleted": True}


# --- video-file --------------------------------------------------------------


@respx.mock
def test_attach_puts_the_file_uuid(runner, configured, short_payload):
    short_payload["data"]["video_file_uuid"] = "file-1"
    route = respx.put(f"{BASE}/{UUID}/video-file").mock(
        return_value=httpx.Response(200, json=short_payload)
    )
    result = invoke(
        runner,
        ["short-form-videos", "video-file", "attach", UUID, "--file-uuid", "file-1", "-o", "json"],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert sent(route) == {"file_uuid": "file-1"}
    assert json.loads(result.output)["video_file_uuid"] == "file-1"


def test_attach_requires_a_file_uuid(runner, configured):
    result = runner.invoke(cli, ["short-form-videos", "video-file", "attach", UUID])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_attach_reports_a_file_the_caller_does_not_own(runner, configured):
    respx.put(f"{BASE}/{UUID}/video-file").mock(
        return_value=httpx.Response(
            422,
            json={"message": "Invalid.", "errors": {"file_uuid": ["The file is not yours."]}},
        )
    )
    result = invoke(
        runner, ["short-form-videos", "video-file", "attach", UUID, "--file-uuid", "nope"]
    )
    assert result.exit_code == ExitCode.VALIDATION
    assert "The file is not yours." in result.output


def test_attach_dry_run_sends_nothing(runner, configured):
    with respx.mock:
        route = respx.put(f"{BASE}/{UUID}/video-file")
        result = invoke(
            runner,
            ["short-form-videos", "video-file", "attach", UUID, "--file-uuid", "f", "--dry-run"],
        )
        assert not route.called
    assert f"PUT {BASE}/{UUID}/video-file" in result.output
    assert '"file_uuid": "f"' in result.output
    assert "tok-123" not in result.output


@respx.mock
def test_detach_deletes_the_sub_resource(runner, configured, short_payload):
    route = respx.delete(f"{BASE}/{UUID}/video-file").mock(
        return_value=httpx.Response(200, json=short_payload)
    )
    result = invoke(runner, ["short-form-videos", "video-file", "detach", UUID, "-o", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert route.called
    assert json.loads(result.output)["video_file_uuid"] is None


def test_detach_dry_run_sends_nothing(runner, configured):
    with respx.mock:
        route = respx.delete(f"{BASE}/{UUID}/video-file")
        result = invoke(runner, ["short-form-videos", "video-file", "detach", UUID, "--dry-run"])
        assert not route.called
    assert f"DELETE {BASE}/{UUID}/video-file" in result.output


@respx.mock
def test_detach_on_an_unknown_short_exits_five(runner, configured):
    respx.delete(f"{BASE}/nope/video-file").mock(return_value=httpx.Response(404, json={}))
    result = invoke(runner, ["short-form-videos", "video-file", "detach", "nope"])
    assert result.exit_code == ExitCode.NOT_FOUND
