"""Episode transcript: a read-only document sub-resource with a paginated child listing."""

import json

import httpx
import pytest
import respx

from unleashed.cli import cli
from unleashed.errors import ExitCode
from unleashed.manifest import Document, Field, KeyValueMap, Listing, ManifestError, Resource
from unleashed.resources.episodes import EPISODES

UUID = "ep-uuid-1"
TRANSCRIPT = f"https://example.test/apiv1/episodes/{UUID}/transcript"
UTTERANCES = f"{TRANSCRIPT}/utterances"


@pytest.fixture
def transcript_payload():
    return {
        "data": {
            "uuid": "tr-1",
            "episode_uuid": UUID,
            "status": "Completed",
            "provider": "assemblyai",
            "language": "en",
            "error_message": None,
            "requested_at": "2026-10-01T10:00:00Z",
            "completed_at": "2026-10-01T10:05:00Z",
            "utterance_count": 2,
            "character_count": 42,
            "text": "Welcome to the show. Thanks for having me.",
        }
    }


def utterance(i):
    return {
        "id": i,
        "speaker": "A",
        "start_ms": i * 1000,
        "end_ms": i * 1000 + 900,
        "text": f"line {i}",
    }


def page(records, current, last):
    return {"data": records, "meta": {"current_page": current, "last_page": last}}


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


# --- manifest ----------------------------------------------------------------


def test_episodes_declare_the_transcript_document():
    (document,) = EPISODES.documents
    assert document.name == "transcript"
    assert [p.name for p in document.params] == ["format"]
    assert [listing.name for listing in document.listings] == ["utterances"]


def test_a_document_cannot_share_a_name_with_a_map():
    with pytest.raises(ManifestError, match="duplicate sub-resources"):
        Resource(
            name="x",
            fields=[Field("a")],
            maps=[KeyValueMap("extra")],
            documents=[Document("extra")],
        )


def test_a_document_cannot_declare_the_same_listing_twice():
    with pytest.raises(ManifestError, match="duplicate listings"):
        Document("transcript", listings=(Listing("lines"), Listing("lines")))


def test_a_listing_cannot_shadow_the_get_command():
    with pytest.raises(ManifestError, match="get"):
        Document("transcript", listings=(Listing("get"),))


def test_the_transcript_group_is_listed_under_episodes(runner):
    result = runner.invoke(cli, ["episodes", "transcript", "--help"])
    assert result.exit_code == ExitCode.SUCCESS
    assert "get" in result.output
    assert "utterances" in result.output


# --- transcript get ----------------------------------------------------------


@respx.mock
def test_get_reads_the_latest_transcript(runner, configured, transcript_payload):
    route = respx.get(TRANSCRIPT).mock(return_value=httpx.Response(200, json=transcript_payload))
    result = invoke(runner, ["episodes", "transcript", "get", UUID, "-o", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(result.output)["status"] == "Completed"
    assert "format" not in route.calls.last.request.url.params


@respx.mock
def test_get_can_omit_the_text_for_status_polling(runner, configured, transcript_payload):
    route = respx.get(TRANSCRIPT).mock(return_value=httpx.Response(200, json=transcript_payload))
    invoke(runner, ["episodes", "transcript", "get", UUID, "--format", "none", "-o", "json"])
    assert route.calls.last.request.url.params["format"] == "none"


def test_get_rejects_an_unknown_format(runner, configured):
    result = runner.invoke(cli, ["episodes", "transcript", "get", UUID, "--format", "srt"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_an_episode_without_a_transcript_exits_not_found(runner, configured):
    respx.get(TRANSCRIPT).mock(return_value=httpx.Response(404, json={"message": "Not found."}))
    result = invoke(runner, ["episodes", "transcript", "get", UUID])
    assert result.exit_code == ExitCode.NOT_FOUND


def test_get_dry_run_prints_the_request(runner, configured):
    result = invoke(
        runner, ["episodes", "transcript", "get", UUID, "--format", "none", "--dry-run"]
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert f"GET {TRANSCRIPT}?format=none" in result.output


# --- transcript utterances list ----------------------------------------------


@respx.mock
def test_utterances_list_walks_every_page(runner, configured):
    route = respx.get(UTTERANCES).mock(
        side_effect=[
            httpx.Response(200, json=page([utterance(0), utterance(1)], 1, 2)),
            httpx.Response(200, json=page([utterance(2)], 2, 2)),
        ]
    )
    result = invoke(
        runner, ["episodes", "transcript", "utterances", "list", UUID, "--with-words", "-o", "json"]
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert [u["id"] for u in json.loads(result.output)] == [0, 1, 2]
    assert route.calls[0].request.url.params["with_words"] == "true"
    assert route.calls[1].request.url.params["page"] == "2"


@respx.mock
def test_utterances_list_honours_max_items_and_per_page(runner, configured):
    route = respx.get(UTTERANCES).mock(
        return_value=httpx.Response(200, json=page([utterance(0), utterance(1)], 1, 5))
    )
    result = invoke(
        runner,
        [
            "episodes",
            "transcript",
            "utterances",
            "list",
            UUID,
            "--max-items",
            "1",
            "--per-page",
            "250",
            "-o",
            "json",
        ],
    )
    assert len(json.loads(result.output)) == 1
    assert route.call_count == 1
    assert route.calls.last.request.url.params["per_page"] == "250"


@respx.mock
def test_utterances_list_can_stop_after_one_page(runner, configured):
    route = respx.get(UTTERANCES).mock(
        return_value=httpx.Response(200, json=page([utterance(0)], 1, 5))
    )
    invoke(runner, ["episodes", "transcript", "utterances", "list", UUID, "--no-paginate"])
    assert route.call_count == 1


def test_utterances_dry_run_prints_the_request(runner, configured):
    result = invoke(
        runner,
        ["episodes", "transcript", "utterances", "list", UUID, "--no-with-words", "--dry-run"],
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert f"GET {UTTERANCES}?with_words=false" in result.output
