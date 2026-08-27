"""HTTP client for the v1 API.

Knows about status codes and retries. Knows nothing about any particular resource.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from unleashed.config import Config
from unleashed.errors import ApiError, RateLimitError, error_for_status

DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_BACKOFF = 30.0
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class DescribedRequest:
    """What a request would look like. Used by --dry-run, never sent."""

    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any] | None


class Client:
    def __init__(
        self,
        config: Config,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.config = config
        self.max_retries = max_retries
        self.max_backoff = max_backoff
        self._sleep = sleep
        self._timeout = timeout

    def url_for(self, path: str) -> str:
        return f"{self.config.base_url}/{path.lstrip('/')}"

    def describe(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> DescribedRequest:
        return DescribedRequest(
            method=method.upper(),
            url=self.url_for(path),
            headers=self.config.headers(redact=True),
            body=body,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        unwrap: bool = True,
    ) -> Any:
        """Send a request, retrying only on 429, and unwrap the `data` envelope."""
        response = self._send_with_retries(method, path, json=json, params=params)

        if response.status_code >= 400:
            raise error_for_status(response.status_code, _safe_json(response))

        if response.status_code == 204 or not response.content:
            return None

        payload = _safe_json(response)
        if unwrap and isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def create(self, resource: str, body: dict[str, Any]) -> Any:
        return self.request("POST", f"/{resource}", json=body)

    def index(
        self,
        resource: str,
        params: dict[str, Any],
        *,
        paginate: bool = True,
        max_items: int | None = None,
    ) -> list[Any]:
        """Walk the index, following `meta.last_page` until the caller has enough.

        Auto-pagination is the default so a caller never mistakes page one for the
        whole answer. `--no-paginate` and `--max-items` are the ways to spend less.
        """
        records: list[Any] = []
        page = 1
        while True:
            payload = self.request(
                "GET", f"/{resource}", params={**params, "page": page}, unwrap=False
            )
            batch = payload.get("data", []) if isinstance(payload, dict) else (payload or [])
            records.extend(batch)

            if max_items is not None and len(records) >= max_items:
                return records[:max_items]
            if not paginate or not batch:
                return records

            meta = payload.get("meta") or {} if isinstance(payload, dict) else {}
            last_page = meta.get("last_page")
            if last_page is None or page >= last_page:
                return records
            page += 1

    def _send_with_retries(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
        params: dict[str, Any] | None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = httpx.request(
                    method,
                    self.url_for(path),
                    headers=self.config.headers(),
                    json=json,
                    params=params,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                raise ApiError(0, message=f"Could not reach the API: {exc}") from exc

            if response.status_code != 429:
                return response

            if attempt >= self.max_retries:
                raise RateLimitError(429, _safe_json(response))

            self._sleep(self._backoff_for(response, attempt))
            attempt += 1

    def _backoff_for(self, response: httpx.Response, attempt: int) -> float:
        """Honour Retry-After, but cap it — a hostile header must not hang the CLI."""
        header = response.headers.get("Retry-After")
        try:
            wait = float(header) if header is not None else 2.0**attempt
        except ValueError:
            wait = 2.0**attempt
        return min(max(wait, 0.0), self.max_backoff)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
