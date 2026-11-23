"""The files resource, per the v1 API contract.

Files are read through /apiv1 (files:read) and uploaded through the direct-to-storage
routes beside it (files:write). There is no create, update, or delete.
"""

from __future__ import annotations

from unleashed.manifest import Field, FieldType, Filter, Resource

FILES = Resource(
    name="files",
    fields=(
        Field("uuid", read_only=True, help="The file UUID other commands take."),
        Field("original_name", read_only=True),
        Field("type", read_only=True, help="MIME type."),
        Field("size", type=FieldType.INT, read_only=True, help="Bytes."),
        Field("key", read_only=True, help="Object key in storage."),
        Field("url", read_only=True, help="Public URL."),
        Field("created_at", read_only=True),
        Field("updated_at", read_only=True),
    ),
    filters=(
        Filter("type", help="Exact MIME type, such as video/mp4."),
        Filter("original_name", help="Partial match."),
    ),
    sorts=("created_at", "original_name", "size"),
    actions=("list", "get"),
    uploads=True,
)
