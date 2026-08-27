import httpx
import pytest
import respx

from unleashed.client import Client
from unleashed.errors import (
    ApiError,
    AuthError,
    ConflictError,
    ExitCode,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

URL = "https://example.test/apiv1/episodes"


@pytest.fixture
def client(config):
    return Client(config, sleep=lambda _seconds: None)


@respx.mock
def test_create_posts_the_body_and_returns_the_unwrapped_record(client, episode_payload):
    route = respx.post(URL).mock(return_value=httpx.Response(201, json=episode_payload))
    result = client.create("episodes", {"name": "Episode 101"})
    assert result == episode_payload["data"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-123"
    assert route.calls.last.request.headers["Accept"] == "application/json"


@respx.mock
def test_unknown_response_keys_are_passed_through_not_rejected(client):
    respx.post(URL).mock(
        return_value=httpx.Response(201, json={"data": {"uuid": "u", "brand_new_key": 1}})
    )
    assert client.create("episodes", {})["brand_new_key"] == 1


@respx.mock
def test_a_401_raises_an_auth_error(client):
    respx.post(URL).mock(return_value=httpx.Response(401, json={"message": "Unauthenticated."}))
    with pytest.raises(AuthError) as exc:
        client.create("episodes", {})
    assert exc.value.exit_code is ExitCode.AUTH


@respx.mock
def test_a_422_raises_a_validation_error_carrying_the_field_errors(client):
    body = {
        "message": "The given data was invalid.",
        "errors": {"name": ["The name field is required."]},
    }
    respx.post(URL).mock(return_value=httpx.Response(422, json=body))
    with pytest.raises(ValidationError) as exc:
        client.create("episodes", {})
    assert exc.value.exit_code is ExitCode.VALIDATION
    assert exc.value.errors == {"name": ["The name field is required."]}


@respx.mock
def test_a_404_raises_a_not_found_error(client):
    respx.get(f"{URL}/nope").mock(return_value=httpx.Response(404, json={"message": "Not found."}))
    with pytest.raises(NotFoundError) as exc:
        client.request("GET", "/episodes/nope")
    assert exc.value.exit_code is ExitCode.NOT_FOUND


@respx.mock
def test_a_409_raises_a_conflict_error_carrying_the_existing_uuid(client):
    respx.post(URL).mock(
        return_value=httpx.Response(409, json={"message": "Lead already exists.", "uuid": "dupe"})
    )
    with pytest.raises(ConflictError) as exc:
        client.create("episodes", {})
    assert exc.value.exit_code is ExitCode.CONFLICT
    assert exc.value.uuid == "dupe"


@respx.mock
def test_a_429_is_retried_after_honouring_retry_after(client, episode_payload):
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(201, json=episode_payload),
        ]
    )
    assert client.create("episodes", {})["uuid"] == "ep-uuid-1"
    assert route.call_count == 2


@respx.mock
def test_retries_are_bounded_and_then_raise(config):
    client = Client(config, max_retries=2, sleep=lambda _seconds: None)
    route = respx.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "1"}))
    with pytest.raises(RateLimitError) as exc:
        client.create("episodes", {})
    assert exc.value.exit_code is ExitCode.RATE_LIMITED
    assert route.call_count == 3


@respx.mock
def test_retry_after_is_capped_so_a_hostile_header_cannot_hang_the_cli(config):
    slept = []
    client = Client(config, max_retries=1, sleep=slept.append, max_backoff=5.0)
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "3600"}))
    with pytest.raises(RateLimitError):
        client.create("episodes", {})
    assert slept == [5.0]


@respx.mock
def test_a_missing_retry_after_falls_back_to_backoff(config):
    slept = []
    client = Client(config, max_retries=1, sleep=slept.append)
    respx.post(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(RateLimitError):
        client.create("episodes", {})
    assert slept and slept[0] > 0


@respx.mock
def test_an_unmapped_status_raises_a_generic_api_error(client):
    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(ApiError) as exc:
        client.create("episodes", {})
    assert exc.value.exit_code is ExitCode.ERROR
    assert exc.value.status == 500


@respx.mock
def test_a_non_json_error_body_still_produces_a_usable_message(client):
    respx.post(URL).mock(return_value=httpx.Response(500, text="<html>nope</html>"))
    with pytest.raises(ApiError) as exc:
        client.create("episodes", {})
    assert "500" in str(exc.value)


@respx.mock
def test_a_transport_failure_is_wrapped_not_leaked(client):
    respx.post(URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ApiError) as exc:
        client.create("episodes", {})
    assert exc.value.exit_code is ExitCode.ERROR


def test_build_request_describes_the_call_without_sending_it(client):
    described = client.describe("POST", "/episodes", {"name": "Episode 101"})
    assert described.method == "POST"
    assert described.url == "https://example.test/apiv1/episodes"
    assert described.headers["Authorization"] == "Bearer ***redacted***"
    assert described.body == {"name": "Episode 101"}
