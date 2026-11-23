"""Direct-to-storage file uploads.

Uploading is three requests, none of them under /apiv1:

1. POST <site>/api/files/presigned-upload-url with the filename, size, and MIME type.
   The answer is a presigned storage `url`, the `fields` to send as headers, and a `key`.
2. PUT the raw bytes to that `url` with exactly those headers. Storage checks the
   signature, not our token, so the bearer token is never sent there.
3. POST <site>/api/files/upload-complete with the key to create the file record. A
   resource_type and resource_id attach the new file to that record in the same call.

Knows nothing about any particular resource: the caller supplies resource_type.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from unleashed.auth import site_url
from unleashed.client import Client
from unleashed.errors import ApiError, UsageError

PRESIGN_PATH = "/api/files/presigned-upload-url"
COMPLETE_PATH = "/api/files/upload-complete"

#: The server's ceiling, in bytes.
MAX_SIZE = 2 * 1024**3

#: The MIME types the presign route accepts. Anything else is a 422, so it is caught here
#: before a multi-gigabyte file is read.
ALLOWED_TYPES = (
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/ogg",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/html",
    "text/markdown",
    "text/x-markdown",
    "application/pdf",
    "text/vtt",
    "application/json",
)

#: Extensions the standard library guesses wrongly or not at all on some platforms.
_EXTRA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".vtt": "text/vtt",
    ".webm": "video/webm",
    ".webp": "image/webp",
    ".m4a": "audio/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}

CHUNK_SIZE = 1024 * 1024
PUT_TIMEOUT = httpx.Timeout(60.0)


@dataclass(frozen=True)
class UploadPlan:
    """A local file, checked and ready to send."""

    path: Path
    size: int
    type: str

    @property
    def filename(self) -> str:
        return self.path.name

    def presign_body(self) -> dict[str, Any]:
        return {"filename": self.filename, "size": self.size, "type": self.type}

    def complete_body(
        self, key: str, resource_type: str | None = None, resource_id: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"key": key, "size": self.size, "type": self.type}
        if resource_type is not None:
            body["resource_type"] = resource_type
            body["resource_id"] = resource_id
        return body


def guess_type(path: Path) -> str | None:
    extra = _EXTRA_TYPES.get(path.suffix.lower())
    if extra:
        return extra
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed


def plan(path: Path, *, mime_type: str | None = None, accept: str | None = None) -> UploadPlan:
    """Check the file before any request: it exists, fits, and has a type the API takes.

    `accept` is a MIME prefix such as "video/"; a type outside it is refused locally.
    """
    if not path.is_file():
        raise UsageError(f"No such file: {path}")
    size = path.stat().st_size
    if size < 1:
        raise UsageError(f"{path} is empty.")
    if size > MAX_SIZE:
        raise UsageError(f"{path} is {size} bytes; the API accepts at most 2GB ({MAX_SIZE}).")

    chosen = mime_type or guess_type(path)
    if chosen is None:
        raise UsageError(f"Cannot tell the type of {path.name}. Pass --type.")
    if chosen not in ALLOWED_TYPES:
        raise UsageError(
            f"The API does not accept {chosen} files. Pass --type with one of: "
            + ", ".join(ALLOWED_TYPES)
        )
    if accept and not chosen.startswith(accept):
        raise UsageError(f"{path.name} is {chosen}, but only {accept}* files can go here.")
    return UploadPlan(path=path, size=size, type=chosen)


def root_url(client: Client, path: str) -> str:
    """The upload routes live beside /apiv1, at the site root."""
    return site_url(client.config.base_url) + path


def upload(
    client: Client,
    upload_plan: UploadPlan,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> Any:
    """Run all three steps and return the stored file record."""
    presigned = client.request(
        "POST", root_url(client, PRESIGN_PATH), json=upload_plan.presign_body(), unwrap=False
    )
    if not isinstance(presigned, dict) or not presigned.get("url") or not presigned.get("key"):
        raise ApiError(200, message="The API answered the presign request without a url and key.")

    fields = presigned.get("fields") or {}
    put_to_storage(str(presigned["url"]), {str(k): str(v) for k, v in fields.items()}, upload_plan)

    return client.request(
        "POST",
        root_url(client, COMPLETE_PATH),
        json=upload_plan.complete_body(str(presigned["key"]), resource_type, resource_id),
    )


def put_to_storage(url: str, fields: dict[str, str], upload_plan: UploadPlan) -> None:
    """Stream the bytes to the presigned URL. No Authorization header: storage would
    reject it, and the token has no business leaving for a third-party host."""
    headers = {**fields, "Content-Length": str(upload_plan.size)}
    try:
        response = httpx.put(
            url, content=_chunks(upload_plan.path), headers=headers, timeout=PUT_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise ApiError(0, message=f"Could not reach file storage: {exc}") from exc
    if response.status_code >= 400:
        raise ApiError(
            response.status_code,
            message=(
                "File storage refused the upload. The presigned URL may have expired; "
                "run the command again."
            ),
        )


def _chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            yield chunk
