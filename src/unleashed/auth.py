"""`unleashed login`: fetch a personal access token by approving the CLI in a browser.

The handshake is a loopback authorization, the same shape as OAuth's PKCE flow:

1. The CLI invents a secret verifier and a state value, and listens on 127.0.0.1.
2. It opens <site>/cli/authorize with the SHA-256 of the verifier, the state, the
   listener's address, a device name, and the abilities it wants.
3. The user signs in if needed and presses Approve. The site mints the token, parks it
   behind a one-use code, and redirects the browser to the listener with that code.
4. The CLI posts the code and the plain verifier to /apiv1/cli/token and gets the
   token back.

The token itself never passes through the browser, and a stolen code is useless
without the verifier, which never leaves this process.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from unleashed.errors import ApiError, AuthError, UnleashedError, error_for_status

DEFAULT_API_URL = "https://unleashedpodcasts.com/apiv1"

#: Every ability the site grants. The server rejects a request naming anything else.
ABILITIES = ("episodes:read", "episodes:write", "leads:read", "leads:write")

#: How long to wait for the browser. The server's code lives two minutes after approval,
#: but signing in first can take a while.
DEFAULT_WAIT_SECONDS = 300.0

CALLBACK_PATH = "/callback"
LOOPBACK_HOST = "127.0.0.1"
API_SUFFIX = "/apiv1"

_DONE_PAGE = (
    b"<!doctype html><html><head><meta charset=utf-8><title>Unleashed CLI</title></head>"
    b"<body style='font-family:system-ui;margin:4rem auto;max-width:32rem'>"
    b"<h1>You can close this tab</h1><p>Return to your terminal.</p></body></html>"
)


class LoginError(UnleashedError):
    """The browser handshake did not produce a code."""

    exit_code = AuthError.exit_code


@dataclass(frozen=True)
class Handshake:
    """The secrets for one login attempt. Neither is ever written to disk."""

    verifier: str = field(default_factory=lambda: secrets.token_urlsafe(48))
    state: str = field(default_factory=lambda: secrets.token_urlsafe(24))

    def __repr__(self) -> str:
        return "Handshake(***redacted***)"

    @property
    def verifier_hash(self) -> str:
        return hashlib.sha256(self.verifier.encode()).hexdigest()


def site_url(api_url: str) -> str:
    """The web app's root, where /cli/authorize lives, derived from the API URL."""
    url = api_url.rstrip("/")
    if url.endswith(API_SUFFIX):
        return url[: -len(API_SUFFIX)]
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def authorize_url(
    api_url: str,
    handshake: Handshake,
    redirect_uri: str,
    device_name: str,
    abilities: Sequence[str],
) -> str:
    query: list[tuple[str, str]] = [
        ("state", handshake.state),
        ("verifier_hash", handshake.verifier_hash),
        ("redirect_uri", redirect_uri),
        ("device_name", device_name),
    ]
    query.extend(("abilities[]", ability) for ability in abilities)
    return f"{site_url(api_url)}/cli/authorize?{urlencode(query)}"


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if parts.path != CALLBACK_PATH:
            self.send_error(404)
            return
        self.server.result = {key: values[0] for key, values in parse_qs(parts.query).items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_DONE_PAGE)))
        self.end_headers()
        self.wfile.write(_DONE_PAGE)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default access log: the query string carries the code."""


class _CallbackServer(HTTPServer):
    result: dict[str, str] | None = None


class LoopbackListener:
    """A one-shot HTTP listener on 127.0.0.1, on a port the OS picks.

    Bound to the loopback address only, so nothing off this machine can deliver a code.
    """

    def __init__(self) -> None:
        self._server = _CallbackServer((LOOPBACK_HOST, 0), _CallbackHandler)

    @property
    def redirect_uri(self) -> str:
        port = self._server.server_address[1]
        return f"http://{LOOPBACK_HOST}:{port}{CALLBACK_PATH}"

    def wait(self, timeout: float) -> dict[str, str]:
        """Serve requests until the callback arrives or the timeout passes."""
        deadline = time.monotonic() + timeout
        while self._server.result is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LoginError(
                    f"Gave up waiting for the browser after {int(timeout)} seconds. "
                    "Run: unleashed login"
                )
            self._server.timeout = min(remaining, 1.0)
            self._server.handle_request()
        return self._server.result

    def close(self) -> None:
        self._server.server_close()

    def __enter__(self) -> LoopbackListener:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def code_from(result: dict[str, str], handshake: Handshake) -> str:
    """Check the redirect belongs to this attempt and pull the code out of it."""
    if not secrets.compare_digest(result.get("state", ""), handshake.state):
        raise LoginError("The browser answered for a different login attempt. Nothing was saved.")
    if result.get("error") == "access_denied":
        raise LoginError("Access was denied in the browser. Nothing was saved.")
    if "error" in result:
        raise LoginError(f"The browser returned an error: {result['error']}")
    code = result.get("code", "")
    if not code:
        raise LoginError("The browser returned no authorization code.")
    return code


def exchange(api_url: str, code: str, verifier: str, *, timeout: float = 30.0) -> str:
    """Trade the one-use code and the verifier for the token."""
    try:
        response = httpx.post(
            f"{api_url.rstrip('/')}/cli/token",
            json={"code": code, "verifier": verifier},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ApiError(0, message=f"Could not reach the API: {exc}") from exc

    payload = _safe_json(response)
    if response.status_code == 400:
        raise AuthError(400, payload)
    if response.status_code >= 400:
        raise error_for_status(response.status_code, payload)

    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise ApiError(response.status_code, message="The API answered without a token.")
    return token.strip()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
