"""Files: a read-only resource, the direct-to-storage upload flow, and video-file upload."""

import json

import httpx
import pytest
import respx

from unleashed import uploads
from unleashed.auth import ABILITIES
from unleashed.cli import cli
from unleashed.errors import ExitCode
from unleashed.manifest import Attachment, Field, ManifestError, Resource
from unleashed.resources.files import FILES

API = "https://example.test/apiv1"
PRESIGN = "https://example.test/api/files/presigned-upload-url"
COMPLETE = "https://example.test/api/files/upload-complete"
STORAGE = "https://bucket.storage.test/uploads/abc/clip.mp4?X-Amz-Signature=sig"
SHORT = "sfv-uuid-1"

STORED = {
    "id": "file-uuid-1",
    "url": "https://cdn.test/uploads/abc/clip.mp4",
    "key": "uploads/abc/clip.mp4",
    "size": 11,
    "type": "video/mp4",
}


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


def sent(route):
    return json.loads(route.calls.last.request.content)


@pytest.fixture
def clip(work):
    path = work / "clip.mp4"
    path.write_bytes(b"hello video")
    return path


@pytest.fixture
def storage_flow():
    """Mock all three upload steps and hand back the routes."""
    presign = respx.post(PRESIGN).mock(
        return_value=httpx.Response(
            200,
            json={
                "url": STORAGE,
                "key": "uploads/abc/clip.mp4",
                "fields": {"Content-Type": "video/mp4", "x-amz-acl": "public-read"},
                "expires_at": "2026-11-22T12:00:00Z",
            },
        )
    )
    put = respx.put(STORAGE).mock(return_value=httpx.Response(200))
    complete = respx.post(COMPLETE).mock(return_value=httpx.Response(200, json=STORED))
    return presign, put, complete


# --- manifest ----------------------------------------------------------------


def test_files_offers_only_list_and_get_plus_upload(runner):
    result = invoke(runner, ["files", "--help"])
    assert "list" in result.output
    assert "get" in result.output
    assert "upload" in result.output
    for missing in ("create", "update", "delete"):
        assert f"  {missing} " not in result.output


def test_files_has_nothing_writable():
    assert FILES.writable_fields == ()


def test_a_resource_rejects_unknown_actions():
    with pytest.raises(ManifestError, match="unknown actions"):
        Resource(name="x", fields=[Field("a")], actions=("list", "archive"))


def test_batch_create_needs_a_create_action():
    with pytest.raises(ManifestError, match="no create action"):
        Resource(name="x", fields=[Field("a")], actions=("list",), batch_create_max=5)


def test_accept_without_upload_as_is_a_manifest_error():
    with pytest.raises(ManifestError, match="accept without upload_as"):
        Attachment("file", "file_uuid", accept="video/")


def test_an_attachment_without_upload_as_gets_no_upload(runner):
    result = invoke(runner, ["people", "--help"])
    assert result.exit_code == 0
    # people has a map but no attachment; short form videos is the only uploader.
    sfv = invoke(runner, ["short-form-videos", "video-file", "--help"])
    assert "upload" in sfv.output


def test_login_asks_for_the_file_abilities_by_default():
    assert {"files:read", "files:write"} <= set(ABILITIES)


# --- read --------------------------------------------------------------------


@respx.mock
def test_list_sends_filters_and_sort(runner, configured):
    route = respx.get(f"{API}/files").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"last_page": 1}})
    )
    result = invoke(
        runner, ["files", "list", "--type", "video/mp4", "--sort", "-size", "-o", "json"]
    )
    assert result.exit_code == 0
    params = route.calls.last.request.url.params
    assert params["type"] == "video/mp4"
    assert params["sort"] == "-size"


def test_list_rejects_an_unknown_sort(runner, configured):
    result = runner.invoke(cli, ["files", "list", "--sort", "url"])
    assert result.exit_code == ExitCode.USAGE


@respx.mock
def test_get_reads_one_file(runner, configured):
    respx.get(f"{API}/files/file-uuid-1").mock(
        return_value=httpx.Response(200, json={"data": {"uuid": "file-uuid-1"}})
    )
    result = invoke(runner, ["files", "get", "file-uuid-1", "-o", "json"])
    assert json.loads(result.output) == {"uuid": "file-uuid-1"}


# --- files upload ------------------------------------------------------------


@respx.mock
def test_upload_runs_all_three_steps(runner, configured, clip, storage_flow):
    presign, put, complete = storage_flow
    result = invoke(runner, ["files", "upload", str(clip), "-o", "json"])

    assert result.exit_code == 0, result.output
    assert sent(presign) == {"filename": "clip.mp4", "size": 11, "type": "video/mp4"}
    assert presign.calls.last.request.headers["Authorization"] == "Bearer tok-123"
    assert put.calls.last.request.content == b"hello video"
    assert sent(complete) == {"key": "uploads/abc/clip.mp4", "size": 11, "type": "video/mp4"}
    assert json.loads(result.stdout) == STORED


@respx.mock
def test_the_storage_put_never_carries_the_token(runner, configured, clip, storage_flow):
    _, put, _ = storage_flow
    invoke(runner, ["files", "upload", str(clip), "-o", "json"])
    headers = put.calls.last.request.headers
    assert "Authorization" not in headers
    assert headers["x-amz-acl"] == "public-read"
    assert headers["Content-Type"] == "video/mp4"
    assert headers["Content-Length"] == "11"


@respx.mock
def test_upload_warns_that_the_file_is_public(runner, configured, clip, storage_flow):
    result = invoke(runner, ["files", "upload", str(clip), "-o", "json"])
    assert "publicly readable" in result.stderr


@respx.mock
def test_type_overrides_the_guess(runner, configured, work, storage_flow):
    presign, _, _ = storage_flow
    path = work / "notes.weird"
    path.write_text("hi")
    invoke(runner, ["files", "upload", str(path), "--type", "text/plain", "-o", "json"])
    assert sent(presign)["type"] == "text/plain"


def test_upload_dry_run_sends_nothing_and_redacts(runner, configured, clip):
    with respx.mock(assert_all_called=False) as mock:
        result = invoke(runner, ["files", "upload", str(clip), "--dry-run"])
        assert not mock.calls
    assert f"POST {PRESIGN}" in result.output
    assert "PUT <url from step 1>" in result.output
    assert f"POST {COMPLETE}" in result.output
    assert "<key from step 1>" in result.output
    assert "tok-123" not in result.output


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("empty.mp4", b"", "is empty"),
        ("mystery.zzz", b"x", "Pass --type"),
        ("archive.zip", b"x", "does not accept application/zip"),
    ],
)
def test_bad_files_are_refused_before_any_request(runner, configured, work, name, content, message):
    path = work / name
    path.write_bytes(content)
    with respx.mock(assert_all_called=False) as mock:
        result = runner.invoke(cli, ["files", "upload", str(path)])
        assert not mock.calls
    assert result.exit_code == ExitCode.USAGE
    assert message in result.output


def test_a_missing_file_is_a_usage_error(runner, configured, work):
    result = runner.invoke(cli, ["files", "upload", str(work / "nope.mp4")])
    assert result.exit_code == ExitCode.USAGE
    assert "No such file" in result.output


def test_a_file_over_the_ceiling_is_refused(runner, configured, clip, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_SIZE", 5)
    result = runner.invoke(cli, ["files", "upload", str(clip)])
    assert result.exit_code == ExitCode.USAGE
    assert "at most 2GB" in result.output


@respx.mock
def test_a_missing_ability_exits_forbidden(runner, configured, clip):
    respx.post(PRESIGN).mock(return_value=httpx.Response(403, json={"message": "Forbidden."}))
    result = runner.invoke(cli, ["files", "upload", str(clip)])
    assert result.exit_code == ExitCode.FORBIDDEN


@respx.mock
def test_a_presign_without_a_url_is_an_error(runner, configured, clip):
    respx.post(PRESIGN).mock(return_value=httpx.Response(200, json={"key": "k"}))
    result = runner.invoke(cli, ["files", "upload", str(clip)])
    assert result.exit_code == ExitCode.ERROR
    assert "without a url and key" in result.output


@respx.mock
def test_storage_refusing_the_put_is_an_error(runner, configured, clip, storage_flow):
    _, put, complete = storage_flow
    put.mock(return_value=httpx.Response(403, text="<Error>SignatureDoesNotMatch</Error>"))
    result = runner.invoke(cli, ["files", "upload", str(clip)])
    assert result.exit_code == ExitCode.ERROR
    assert "File storage refused the upload" in result.output
    assert not complete.called


@respx.mock
def test_unreachable_storage_is_an_error(runner, configured, clip, storage_flow):
    _, put, _ = storage_flow
    put.mock(side_effect=httpx.ConnectError("boom"))
    result = runner.invoke(cli, ["files", "upload", str(clip)])
    assert result.exit_code == ExitCode.ERROR
    assert "Could not reach file storage" in result.output


# --- short-form-videos video-file upload -------------------------------------


@respx.mock
def test_video_file_upload_attaches_in_the_complete_call(runner, configured, clip, storage_flow):
    _, _, complete = storage_flow
    result = invoke(
        runner, ["short-form-videos", "video-file", "upload", SHORT, str(clip), "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    assert sent(complete) == {
        "key": "uploads/abc/clip.mp4",
        "size": 11,
        "type": "video/mp4",
        "resource_type": "short_form_video",
        "resource_id": SHORT,
    }


def test_video_file_upload_refuses_a_non_video(runner, configured, work):
    path = work / "cover.png"
    path.write_bytes(b"png")
    with respx.mock(assert_all_called=False) as mock:
        result = runner.invoke(cli, ["short-form-videos", "video-file", "upload", SHORT, str(path)])
        assert not mock.calls
    assert result.exit_code == ExitCode.USAGE
    assert "only video/* files" in result.output


def test_video_file_upload_dry_run_names_the_short(runner, configured, work):
    path = work / "take2.mov"
    path.write_bytes(b"mov")
    result = invoke(
        runner, ["short-form-videos", "video-file", "upload", SHORT, str(path), "--dry-run"]
    )
    assert '"type": "video/quicktime"' in result.output
    assert '"resource_type": "short_form_video"' in result.output
    assert f'"resource_id": "{SHORT}"' in result.output


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.mp4", "video/mp4"),
        ("a.MOV", "video/quicktime"),
        ("a.webm", "video/webm"),
        ("a.avi", "video/x-msvideo"),
        ("a.md", "text/markdown"),
        ("a.vtt", "text/vtt"),
        ("a.png", "image/png"),
    ],
)
def test_guess_type(tmp_path, name, expected):
    assert uploads.guess_type(tmp_path / name) == expected
