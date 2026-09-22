"""The people resource, per the v1 API contract.

Metadata is a flat map of scalars. `create` and `update` take it as repeated
--metadata KEY=VALUE flags, and update merges rather than replaces; the metadata
sub-resource is the way to delete keys or replace the map wholesale.
"""

from __future__ import annotations

from unleashed.manifest import Field, FieldType, Filter, KeyValueMap, Resource

PEOPLE = Resource(
    name="people",
    fields=(
        Field("uuid", read_only=True, help="Assigned by the API."),
        Field("name", required_on_create=True, help="At most 255 characters."),
        Field("email", nullable=True),
        Field("bio", nullable=True),
        Field(
            "last_outreach",
            type=FieldType.DATE,
            help="YYYY-MM-DD. Cannot be cleared once set.",
        ),
        Field("metadata", type=FieldType.MAP, help="Merged into existing keys on update."),
        Field("is_public", read_only=True),
        Field("claimed_user_uuid", read_only=True),
        Field("created_at", read_only=True),
        Field("updated_at", read_only=True),
    ),
    filters=(
        Filter("name", help="Partial, case-insensitive match."),
        Filter("email", help="Partial, case-insensitive match."),
        Filter("has_email", type=FieldType.BOOL),
        Filter("is_public", type=FieldType.BOOL),
        Filter("is_claimed", type=FieldType.BOOL, help="Claimed their profile, or not."),
        Filter(
            "last_outreach_before",
            type=FieldType.DATE,
            help="Not contacted since this date. Never-contacted people are included.",
        ),
        Filter("podcast_uuid", help="Only people appearing on this podcast."),
    ),
    sorts=("name", "email", "last_outreach", "created_at"),
    maps=(KeyValueMap("metadata"),),
    singular_name="person",
)
