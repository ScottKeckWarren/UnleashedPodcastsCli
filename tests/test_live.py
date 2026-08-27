"""Optional smoke tests against a real host.

Deselected by default and never run in CI. Point them at a local Sail host to catch
drift between PRD.md's documented contract and what the API actually does:

    UNLEASHED_API_URL=http://localhost/apiv1 UNLEASHED_API_TOKEN=... \
        uv run pytest -m live --no-cov
"""

import os

import pytest

from unleashed.client import Client
from unleashed.config import load_config
from unleashed.errors import AuthError

pytestmark = pytest.mark.live


@pytest.fixture
def live_config():
    try:
        return load_config(os.environ)
    except Exception as exc:
        pytest.skip(f"live host not configured: {exc}")


def test_the_configured_token_is_accepted(live_config):
    """A 401 here means the token is wrong, not that the endpoint is missing."""
    Client(live_config).request("GET", "/episodes", params={"per_page": 1})


def test_a_bad_token_is_rejected(live_config):
    from unleashed.config import Config

    client = Client(Config(base_url=live_config.base_url, token="definitely-wrong"))
    with pytest.raises(AuthError):
        client.request("GET", "/episodes", params={"per_page": 1})
