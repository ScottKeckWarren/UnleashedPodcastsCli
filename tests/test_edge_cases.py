"""Branches the happy path does not reach."""

import httpx
import pytest
import respx

from unleashed.client import Client
from unleashed.errors import ManifestError, RateLimitError
from unleashed.manifest import Field, Resource
from unleashed.output import OutputFormat, default_output, render
from unleashed.resources.episodes import EPISODES

URL = "https://example.test/apiv1/episodes"


def test_asking_for_a_field_the_resource_does_not_have_is_a_manifest_error():
    with pytest.raises(ManifestError, match="no field named"):
        EPISODES.field("nope")


def test_created_at_is_a_valid_sort_even_though_it_is_not_an_exposed_field():
    assert Resource(name="x", fields=[Field("a")], sorts=["created_at"]).sorts == ["created_at"]


@respx.mock
def test_a_204_returns_nothing(config):
    respx.delete(f"{URL}/gone").mock(return_value=httpx.Response(204))
    assert Client(config).request("DELETE", "/episodes/gone") is None


@respx.mock
def test_an_unwrapped_response_body_is_returned_as_is(config):
    respx.post(URL).mock(return_value=httpx.Response(201, json={"uuid": "bare"}))
    assert Client(config).create("episodes", {})["uuid"] == "bare"


@respx.mock
def test_a_garbage_retry_after_header_falls_back_to_backoff(config):
    slept = []
    client = Client(config, max_retries=1, sleep=slept.append)
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "soon"}))
    with pytest.raises(RateLimitError):
        client.create("episodes", {})
    assert slept == [1.0]


@respx.mock
def test_a_negative_retry_after_never_sleeps_backwards(config):
    slept = []
    client = Client(config, max_retries=1, sleep=slept.append)
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "-5"}))
    with pytest.raises(RateLimitError):
        client.create("episodes", {})
    assert slept == [0.0]


def test_a_terminal_gets_a_table_and_a_pipe_gets_json():
    assert default_output(is_tty=True) is OutputFormat.TABLE
    assert default_output(is_tty=False) is OutputFormat.JSON


def test_booleans_render_as_lowercase_words_not_python_repr():
    assert render({"is_published": True}, OutputFormat.TEXT) == "true"
    assert render({"is_published": False}, OutputFormat.TEXT) == "false"


def test_a_nested_value_renders_as_json_inside_its_cell():
    assert render({"errors": {"name": ["bad"]}}, OutputFormat.TEXT) == '{"name": ["bad"]}'


def test_a_list_renders_as_one_table_block_per_item():
    blocks = render([{"uuid": "a"}, {"uuid": "b"}], OutputFormat.TABLE)
    assert blocks == "uuid  a\n\nuuid  b"


def test_a_scalar_renders_without_a_table():
    assert render("plain", OutputFormat.TABLE) == "plain"
