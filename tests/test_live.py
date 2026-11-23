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


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def test_prd_lists_every_docs_json_operation(live_config):
    """The server can grow endpoints PRD.md has never heard of. Name each one."""
    import re
    from pathlib import Path

    import httpx

    spec = httpx.get(f"{live_config.base_url}/docs.json", timeout=30).json()
    served = {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    }
    prd = (Path(__file__).parent.parent / "PRD.md").read_text()
    documented = set(re.findall(r"^\| (GET|POST|PUT|PATCH|DELETE) \| `([^`]+)`", prd, re.M))

    missing = sorted(served - documented)
    assert not missing, "docs.json operations missing from PRD.md's endpoint table:\n" + "\n".join(
        f"  {method} {path}" for method, path in missing
    )
